"""Compile raw C# responses, sandbox them, independently inspect actual PicoGK geometry."""
import argparse
from collections import Counter, deque
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('am_qualification',ROOT.parent/'qualification.py')
qualification=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)
DOTNET=Path(os.environ.get('QWEN_PICOGK_AM_DOTNET',shutil.which('dotnet') or str(ROOT.parent/'work/dotnet/dotnet'))).resolve()
PICO=Path(os.environ.get('QWEN_PICOGK_AM_PICO',str(ROOT.parent/'work/picogk-runtime'))).resolve()
NAMESPACES={'System','System.IO','System.Linq','System.Numerics','System.Globalization',
            'System.Text.Json','System.Collections.Generic','PicoGK'}
API_CARD='PicoGK 2.3 API: new Library(0.2f); new Lattice(lib); lattice.AddSphere(Vector3,float); lattice.AddBeam(Vector3,float,Vector3,float,bool); new Voxels(lattice); new Voxels(lib,IImplicit,BBox3); IImplicit.fSignedDistance(in Vector3); new Voxels(existingVoxels); voxels.Offset(float) (positive outward); voxels.BoolSubtract(other); voxels.BoolIntersect(other); voxels.Trim(BBox3); new Mesh(voxels); mesh.SaveToStlFile(path,Mesh.EStlUnit.MM); new ScalarField(voxels); scalarField.fSignedDistance(in Vector3). Real types are Voxels and Mesh; there is no VoxelMatrix or PolyMesh.'


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def static_gate(code):
    if len(code)>180000: raise ValueError('bounded C# required')
    if re.search(r'\\[uxU]|^\s*#',code,re.M): raise ValueError('escaped identifiers/preprocessor forbidden')
    tokens=r'@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*'
    text=re.sub(tokens,lambda match:'' if match.group().startswith(('/*','//')) else match.group(),code,flags=re.S)
    executable=re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'','',text)
    if not executable.isascii():raise ValueError('non-ASCII executable identifiers forbidden')
    for using in re.findall(r'\busing\s+([\w.]+)\s*;',text):
        if using not in NAMESPACES: raise ValueError('namespace outside static allowlist: '+using)
    # Strings are retained so absolute paths, hidden paths and imports are rejected.
    banned=r'\b(unsafe|dynamic|extern|DllImport|LibraryImport|Reflection|Activator|AppDomain|Assembly|Process|Environment|Registry|Marshal|GCHandle|Delegate|Thread|Task|HttpClient|WebClient|Socket|TcpClient|UdpClient|FileStream|BinaryReader|BinaryWriter|StreamReader|StreamWriter|ConsoleKey|GetType|typeof|GetMethod|GetField|GetProperty|Delete|Move|Copy|EnumerateFiles|GetFiles|GetDirectories|SetCurrentDirectory|ReadAllBytes|WriteAllBytes|OpenRead|OpenWrite|OpenText|ReadAllText|GetEnvironmentVariable|Exit|FailFast|LoadFrom|LoadFile|GetService|GetUninitializedObject)\b'
    if re.search(banned,text): raise ValueError('operation/type outside static allowlist')
    for name in re.findall(r'\bSystem\.([A-Za-z][\w.]*)',text):
        if not any(('System.'+name)==ns or ('System.'+name).startswith(ns+'.') for ns in NAMESPACES if ns!='System'):
            raise ValueError('fully qualified System type outside static allowlist')
    if re.search(r'\busing\s+\w+\s*=|\busing\s+static\b|\bglobal\s*::|@\w|\bnamespace\s+System\b',text):
        raise ValueError('aliases/global namespace escape forbidden')
    if re.search(r'"(?:/|~|[A-Za-z]:\\)|\.\./|\.\.\\',text): raise ValueError('absolute or parent-relative paths forbidden')
    if not re.search(r'\bMain\s*\(\s*string\s*\[\s*\]\s+\w+\s*\)',text):
        raise ValueError('complete Main(string[] args) required')
    return True


def extract(response):
    matches=re.findall(r'```(?:csharp|cs|C#)\s*\n(.*?)```',response,re.S)
    if len(matches)!=1: raise ValueError('exactly one complete C# code fence required')
    code=matches[0].strip()+'\n';static_gate(code);return code


def run(command,cwd,timeout,env=None,sandbox=False,output=None,input_path=None):
    if sandbox:
        quoted=lambda p: json.dumps(str(p))
        readable=[DOTNET.parent,PICO,cwd,input_path,Path('/System'),Path('/usr/lib'),Path('/usr/share'),Path('/Library/Apple'),Path('/private/var/db/dyld'),Path('/dev')]
        writable=[output,cwd/'tmp']
        profile='(version 1)(allow default)(deny process-fork)(deny network*)(deny file-read-data)(deny file-write*)'
        profile+='(allow file-read-data (literal "/") '+ ' '.join('(subpath '+quoted(p)+')' for p in readable if p is not None)+')'
        profile+='(allow file-write* '+ ' '.join('(subpath '+quoted(p)+')' for p in writable)+')'
        command=['/usr/bin/sandbox-exec','-p',profile,*command]
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(90,90))
        resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024*1024,32*1024*1024))
    with (cwd/'process.log').open('w') as log:
        result=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=log,timeout=timeout,preexec_fn=limit)
    return result.returncode


def build(code,folder,assembly='Candidate'):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'Program.cs').write_text(code)
    (folder/'global.json').write_text('{"sdk":{"version":"9.0.317","rollForward":"disable"}}')
    (folder/'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    (folder/f'{assembly}.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net9.0</TargetFramework><OutputType>Exe</OutputType><Nullable>enable</Nullable><ImplicitUsings>disable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems><AllowUnsafeBlocks>false</AllowUnsafeBlocks></PropertyGroup><ItemGroup><Compile Include="Program.cs"/><Reference Include="PicoGK"><HintPath>{PICO}/PicoGK.dll</HintPath></Reference></ItemGroup></Project>''')
    env={**os.environ,'DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_EnableDiagnostics':'0','DOTNET_CLI_HOME':str(folder/'tmp')}
    if run([str(DOTNET),'build',str(folder/f'{assembly}.csproj'),'-c','Release','--nologo','-v','q'],folder,90,env):
        shutil.copy2(folder/'process.log',folder/'compile.log')
        raise ValueError('C# compilation failed; see '+str(folder/'process.log'))
    shutil.copy2(folder/'process.log',folder/'compile.log')
    binary=folder/'bin/Release/net9.0'/f'{assembly}.dll'
    for path in PICO.glob('*.dylib'):
        destination=binary.parent/path.name
        if destination.exists():continue
        # A shared inode can make dyld resolve @loader_path through a sibling sandbox.
        try:os.symlink(path,destination)
        except OSError:shutil.copy2(path,destination)
    return binary,env


def mesh_properties(path):
    data=path.read_bytes()
    if len(data)<84 or len(data)!=84+50*struct.unpack_from('<I',data,80)[0]: raise ValueError('binary STL expected')
    edges=Counter();directions=Counter();volume=0;degenerate=0;triangles=[]
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    for off in range(84,len(data),50):
        f=struct.unpack_from('<12fH',data,off);a,b,c=f[3:6],f[6:9],f[9:12]
        if any(not math.isfinite(v) for p in (a,b,c) for v in p): raise ValueError('nonfinite mesh')
        vec=cross(tuple(b[i]-a[i] for i in range(3)),tuple(c[i]-a[i] for i in range(3)))
        if sum(v*v for v in vec)==0:degenerate+=1
        bc=cross(b,c);volume+=sum(a[i]*bc[i] for i in range(3))/6
        vertices=[tuple(v for v in p) for p in (a,b,c)]
        triangles.append(vertices)
        for left,right in zip(vertices,vertices[1:]+vertices[:1]):
            key=tuple(sorted((left,right)));edges[key]+=1;directions[key]+=1 if left<right else -1
    return dict(triangles=len(triangles),degenerate=degenerate,boundary=sum(n==1 for n in edges.values()),
                nonmanifold=sum(n!=2 for n in edges.values()),inconsistent=sum(n!=0 for n in directions.values()),volume_mm3=volume)


def inspect(mesh,folder):
    inspector_dir=ROOT/'inspector-build'
    binary=inspector_dir/'bin/Release/net9.0/Inspector.dll'
    source=(ROOT/'Inspector.cs').read_text()
    if not binary.is_file() or (inspector_dir/'Program.cs').read_text()!=source:build(source,inspector_dir,'Inspector')
    folder.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'DOTNET_ROOT':str(DOTNET.parent),'DOTNET_EnableDiagnostics':'0'}
    if run([str(DOTNET),str(binary),str(mesh),str(folder)],folder,90,env):raise ValueError('trusted native inspection failed')
    return json.loads((folder/'native.json').read_text()),(folder/'occupancy.bin').read_bytes()


def fixture(task,path,bad=None):
    if task['fixture']=='normals':
        h=task['oracle']['half'];rows=['# registered outward tangent planes','x,y,z,nx,ny,nz','']
        for axis in range(3):
            for sign in (-1,1):
                p=[0.,0.,0.];normal=[0.,0.,0.];p[axis]=h*sign;normal[axis]=2*sign
                rows.append(','.join(str(v) for v in p+normal))
        if bad=='nonfinite':rows[-1]='NaN,0,0,1,0,0'
        if bad=='zero-normal':rows[-1]='0,0,2.6,0,0,0'
        if bad=='column-count':rows[-1]='0,0,2.6,0,1'
        path.write_text('\n'.join(rows)+'\n')
    else:path.write_text('synthetic fixture; all geometry dimensions are in the task\n')


def connectivity(occupied,grid):
    n=grid['n'];seen=bytearray(len(occupied));q=deque([0]);seen[0]=1
    while q:
        i=q.popleft();x=i%n;y=(i//n)%n;z=i//(n*n)
        for j,ok in ((i-1,x>0),(i+1,x<n-1),(i-n,y>0),(i+n,y<n-1),(i-n*n,z>0),(i+n*n,z<n-1)):
            if ok and not occupied[j] and not seen[j]:seen[j]=1;q.append(j)
    return sum(not occupied[i] and not seen[i] for i in range(len(occupied)))


def check_geometry(task,native,occupancy,mesh,reference):
    checks={'closed_oriented_positive_mesh':mesh['triangles']>0 and mesh['degenerate']==0 and mesh['boundary']==0 and mesh['nonmanifold']==0 and mesh['inconsistent']==0 and mesh['volume_mm3']>0}
    rn,ro,rm=reference
    intersection=sum(bool(a and b) for a,b in zip(occupancy,ro));union=sum(bool(a or b) for a,b in zip(occupancy,ro))
    iou=intersection/union if union else 0
    checks['native_reference_occupancy_iou']=iou>=task['oracle'].get('reference_occupancy_iou_min',.95)
    checks['native_volume']=abs(native['volume_mm3']-rn['volume_mm3'])/rn['volume_mm3']<=.06
    checks['native_stl_volume_agreement']=native['volume_interval_mm3'][0]<=mesh['volume_mm3']<=native['volume_interval_mm3'][1]
    checks['native_dimensions']=all(abs(a-b)<=.25 for k in ('low','high') for a,b in zip(native[k],rn[k]))
    oracle=task['oracle'];shape=oracle['shape'];grid=native['grid'];n=grid['n'];step=grid['step'];low=grid['low']
    def inside(x,y,z):return bool(occupancy[round((x-low)/step)+n*(round((y-low)/step)+n*round((z-low)/step))])
    if shape in ('shell','vent','cone'):checks['chamber_centre_void']=not inside(0,0,2 if shape=='cone' else 0)
    if shape=='closing':checks['crack_closed']=inside(0,0,0) and inside(0,1,0) and inside(0,-1,0)
    if shape=='sphere':
        expected=4*math.pi*oracle['radius']**3/3
        checks['analytic_volume']=abs(mesh['volume_mm3']-expected)/expected<.06
    if shape=='cylinder':
        expected=math.pi*oracle['radius']**2*2*oracle['half_height']
        checks['analytic_volume']=abs(mesh['volume_mm3']-expected)/expected<.1
    if shape=='box':checks['analytic_volume']=abs(mesh['volume_mm3']-(2*oracle['half'])**3)/(2*oracle['half'])**3<.06
    if oracle.get('require_void_connectivity'):checks['no_trapped_voids_native_grid']=connectivity(occupancy,grid)==0
    if shape=='cone':checks['analytic_roof_angle']=math.degrees(math.atan(oracle['height']/oracle['radius']))>45
    if shape=='tpms':
        rays=native['wall_rays_mm'];checks['physical_wall_native_rays']=len(rays)>=20 and min(rays)>=oracle['wall_native_ray_min_mm']-.051
    return checks,dict(occupancy_iou=iou,native=native,mesh=mesh,trapped_void_cells=connectivity(occupancy,grid) if oracle.get('require_void_connectivity') else None)


def evaluate(task,code,folder,reference=None):
    folder.mkdir(parents=True,exist_ok=True)
    result={'id':task['id'],'status':'failed','checks':{},'qualification':'software and geometry only',
            'source_sha256':hashlib.sha256(code.encode()).hexdigest()}
    try:
        static_gate(code);result['checks']['static_allowlist']=True
        binary,env=build(code,folder)
        output=folder/'output';output.mkdir(exist_ok=True);(folder/'tmp').mkdir(exist_ok=True)
        source=folder/'input.csv';fixture(task,source)
        rc=run([str(DOTNET),str(binary),str(source),str(output)],folder,90,env,True,output,source)
        shutil.copy2(folder/'process.log',folder/'run.log')
        result['native_exit_code']=rc
        result['checks']['native_exit_zero']=rc==0
        if rc:raise ValueError('isolated native process failed; see '+str(folder/'process.log'))
        if task['kind']=='refusal':
            value=json.loads((output/'refused.json').read_text())
            result['checks']['strict_refusal']=value=={'status':'needs_measurement','manufacturing_authorized':False,'missing':task['oracle']['missing']} and {p.name for p in output.iterdir()}=={'refused.json'}
        else:
            mesh=mesh_properties(output/'part.stl');native,occ=inspect(output/'part.stl',folder/'inspection')
            if reference is None:reference=(native,occ,mesh)
            checks,details=check_geometry(task,native,occ,mesh,reference);result['checks'].update(checks);result['details']=details
            for bad in task['oracle'].get('negative_inputs',[]):
                invalid=folder/f'{bad}.csv';fixture(task,invalid,bad);out=folder/f'{bad}-output';out.mkdir()
                code_rc=run([str(DOTNET),str(binary),str(invalid),str(out)],folder,90,env,True,out,invalid)
                shutil.copy2(folder/'process.log',folder/f'{bad}.log')
                result['checks']['reject_'+bad]=code_rc!=0 and not (out/'part.stl').exists()
            result['_reference']=(native,occ,mesh)
        result['status']='passed' if all(result['checks'].values()) else 'failed'
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:result['error']=str(exc)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references',action='store_true')
    parser.add_argument('--split',choices=['development','final'],default='development')
    parser.add_argument('--responses',type=Path,help='directory of <task-id>.txt raw responses')
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--selection-receipt',type=Path,help='required for final model inference, frozen by root')
    args=parser.parse_args()
    args.run_dir=args.run_dir.resolve()
    if args.responses is not None:args.responses=args.responses.resolve()
    if args.split=='final' and not args.references:
        if not args.selection_receipt:parser.error('final requires a selected candidate receipt after development')
        selection=json.loads(args.selection_receipt.read_text())
        if (selection.get('schema')!='picogk.am.development-selection@1'
            or selection.get('status')!='selected_for_final_evaluation'
            or selection.get('development_passes',0)<11 or selection.get('required_safety_passed') is not True
            or not qualification.complete_checks(selection.get('checks'))):
            parser.error('development promotion gate unmet')
        if not args.responses:parser.error('final scoring requires captured model responses')
        inference=json.loads((args.responses/'protocol.json').read_text())
        if inference.get('selection_receipt_sha256')!=digest(args.selection_receipt):parser.error('final responses lack selected candidate binding')
        if any(inference.get(k)!=selection.get(k) for k in ('adapter_sha256','adapter_config_sha256','base_weights_sha256')):
            parser.error('final response model differs from selected model')
    frozen=json.loads((ROOT/'freeze.json').read_text())
    path=ROOT/f'{args.split}.json'
    if digest(path)!=frozen['files'][path.name]:parser.error('frozen tasks changed')
    tasks=json.loads(path.read_text())['tasks'];args.run_dir.mkdir(parents=True,exist_ok=False)
    results=[]
    for task in tasks:
        if args.references:code=(ROOT/task['reference']).read_text();reference=None
        else:
            reference_root=ROOT/'reference-validation'/task['id']
            ref_json=json.loads((reference_root/'result.json').read_text())
            if ref_json['status']!='passed':raise ValueError('authored reference must validate before candidate execution')
            reference=(json.loads((reference_root/'inspection/native.json').read_text()),(reference_root/'inspection/occupancy.bin').read_bytes(),ref_json['details']['mesh']) if task['kind']!='refusal' else None
            try:code=extract((args.responses/f'{task["id"]}.txt').read_text())
            except (OSError,ValueError) as exc:
                results.append(dict(id=task['id'],status='failed',error=str(exc)));continue
        result=evaluate(task,code,args.run_dir/task['id'],reference)
        result.pop('_reference',None)
        (args.run_dir/task['id']/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        results.append(result);print(task['id'],result['status'],flush=True)
    report={'split':args.split,'reference_only':args.references,'passed':sum(r['status']=='passed' for r in results),'total':len(results),'tasks':results,'physical_qualification':False,'task_sha256':digest(path)}
    (args.run_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='tasks'},indent=2))
    return 0 if report['passed']==len(results) else 1


if __name__=='__main__':raise SystemExit(main())
