#!/usr/bin/env python3
"""Independently compile and inspect compact teaching geometry and parser refusals."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct

import numpy as np

ROOT=Path(__file__).resolve().parent
CORE_PATH=ROOT.parents[1]/'evaluation/evaluate.py'
spec=importlib.util.spec_from_file_location('compact_native_tools',CORE_PATH)
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
PROBE='''using System;using System.IO;using System.Linq;using System.Numerics;using System.Globalization;using System.Collections.Generic;using System.Text.Json;using PicoGK;
public static class Program { public static void Main(string[] args) {
using Library lib=new(.2f);using Voxels vdb=Voxels.voxFromVdbFile(lib,args[0]);
var a=new List<bool>();
foreach(string row in File.ReadLines(args[1])) {float[] v=row.Split(',').Select(x=>float.Parse(x,CultureInfo.InvariantCulture)).ToArray();Vector3 p=new(v[0],v[1],v[2]);a.Add(vdb.bIsInside(p));}
File.WriteAllText(Path.Combine(args[2],"hits.json"),JsonSerializer.Serialize(new {vdb=a}));
} }
'''

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def point(c,axis,d):p=c.copy();p[axis]+=d;return p


def stl_membership(path, points):
    """Classify directly against triangles; mesh-to-voxel import can fill nested cavities."""
    data=path.read_bytes()
    count=struct.unpack_from('<I',data,80)[0]
    if len(data)!=84+50*count:raise ValueError('Binary STL size mismatch.')
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    triangles=np.frombuffer(data,dtype=dtype,count=count,offset=84)['vertices'].astype(np.float64)
    origin=triangles[:,0];edge1=triangles[:,1]-origin;edge2=triangles[:,2]-origin
    # Three unrelated oblique rays avoid axis-aligned faces and triangulation vertices.
    directions=[np.array(d,dtype=np.float64) for d in [(1,.371,.619),(.217,1,.463),(.529,.283,1)]]
    answers=[]
    for point_value in points:
        p=np.array(point_value,dtype=np.float64);votes=[]
        for direction in directions:
            direction/=np.linalg.norm(direction)
            cross=np.cross(direction,edge2);det=np.einsum('ij,ij->i',edge1,cross)
            active=np.abs(det)>1e-11
            inverse=np.zeros_like(det);inverse[active]=1/det[active]
            delta=p-origin;u=np.einsum('ij,ij->i',delta,cross)*inverse
            q=np.cross(delta,edge1);v=q@direction*inverse
            t=np.einsum('ij,ij->i',edge2,q)*inverse
            hits=np.sort(t[active&(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)&(t>1e-8)])
            # A ray crossing the diagonal shared by two coplanar facets crosses one surface.
            unique=int(len(hits)>0)+int(np.count_nonzero(np.diff(hits)>1e-7))
            votes.append(bool(unique%2))
        if len(set(votes))!=1:raise ValueError('Ambiguous independent STL parity; inspect probe clearance.')
        answers.append(votes[0])
    return answers

def probes(oracle):
    shape=oracle['shape'];c=oracle.get('centre');values=[]
    def add(p,inside):values.append({'point':p,'inside':inside})
    if shape in ('sphere','shell'):
        r=oracle['radius']
        if shape=='sphere':add(c,True);add(point(c,0,r-.5),True)
        else:add(c,False);add(point(c,0,r-oracle['wall']/2),True);add(point(c,0,r-oracle['wall']-.5),False)
        add(point(c,0,r+.6),False)
    elif shape in ('box','closing','vent'):
        half=oracle.get('half');half=[half]*3 if isinstance(half,(float,int)) else half
        add(c,shape!='vent')
        if shape=='vent':
            w=oracle['wall'];add(point(c,0,half[0]-w/2),True);add(point(c,2,half[2]-w/2),True)
            for z in [c[2]-half[2]-.4+i*.4 for i in range(int((half[2]+.8)/.4)+1)]:add([c[0],c[1],z],False)
        else:
            add(point(c,0,half[0]-.5),True);add(point(c,1,half[1]-.5),True)
        add(point(c,0,half[0]+.6),False)
    elif shape=='cylinder':
        add(c,True);add(point(c,0,oracle['radius']-.4),True);add(point(c,0,oracle['radius']+.6),False)
        add(point(c,2,oracle['half_height']-.4),True);add(point(c,2,oracle['half_height']+.6),False)
    elif shape=='splats':
        for p in oracle['points']:add(p,True);add(point(p,2,oracle['radius']+.7),False)
    elif shape=='cone':
        o=oracle['origin'];r=oracle['radius'];z=oracle['shoulder'];rise=oracle['rise']
        add([o[0],o[1],oracle['floor']+.3],False)
        add([o[0]+r*.2,o[1],z+rise*.5],False)
        add([o[0]+r*.85,o[1],z+rise*.5],True)
        add([o[0],o[1],z+rise+.6],True)
        add([o[0]+r+.6,o[1],.6],True)
        for height in [-.4+i*.4 for i in range(int((z+.8)/.4)+1)]:add([o[0],o[1],height],False)
    elif shape=='tpms':
        add(c,True)
        for sign in (-1,1):add([x+sign*oracle['cell']/8 for x in c],False)
        cell=oracle['cell'];family=('gyroid','diamond','schwarz-p')[oracle['kind']]
        # Exact nodal identities distinguish the three Fourier families independently.
        gyroid=[x+cell/4 for x in c]
        diamond=[c[0]+cell/4,c[1]+cell/8,c[2]-cell/8]
        schwarz=[c[0]+cell/4,c[1]-cell/12,c[2]-cell/12]
        add(gyroid,family=='gyroid');add(diamond,family=='diamond')
        if family=='schwarz-p':add(schwarz,True)
        # Independently known nodal gradient is diagonal at each canonical centre.
        for step in range(-30,31):values.append({'point':[x+(step*.05)/math.sqrt(3) for x in c],'ray_t':step*.05})
    return values


def expected_volume(oracle):
    shape=oracle['shape'];r=oracle.get('radius');half=oracle.get('half')
    if shape=='sphere':return 4*math.pi*r**3/3
    if shape=='shell':return 4*math.pi*(r**3-(r-oracle['wall'])**3)/3
    if shape=='cylinder':return math.pi*r*r*2*oracle['half_height']
    if shape=='splats':return len(oracle['points'])*4*math.pi*r**3/3
    if shape=='closing':return (2*half)**3
    if shape=='box':return math.prod(2*x for x in half)
    if shape=='vent':return math.prod(2*x for x in half)-math.prod(2*(x-oracle['wall']) for x in half)-math.pi*oracle['vent_radius']**2*oracle['wall']
    if shape=='cone':return math.prod(2*x for x in half)-math.pi*r*r*(oracle['shoulder']-oracle['floor']+oracle['rise']/3)-math.pi*oracle['port']**2*oracle['floor']
    return None


def validate_geometry(output,folder,oracle,probe_binary,probe_env):
    checks={};mesh=core.mesh_properties(output/'part.stl')
    checks['closed_oriented_nondegenerate_positive_stl']=mesh['triangles']>0 and mesh['volume_mm3']>0 and all(mesh[k]==0 for k in ('degenerate','boundary','nonmanifold','inconsistent'))
    native,occupied=core.inspect(output/'part.stl',folder/'inspection')
    checks['finite_nonempty_vdb']=native['library_volume_mm3']>0 and all(math.isfinite(x) for x in native['low']+native['high'])
    checks['stl_vdb_volume_interval']=native['volume_interval_mm3'][0]<=mesh['volume_mm3']<=native['volume_interval_mm3'][1]
    checks['bounded_output']=all(-10<=x<=10 for x in native['low']+native['high'])
    volume=expected_volume(oracle)
    if volume is not None:checks['independent_analytic_volume']=abs(mesh['volume_mm3']-volume)/volume<.10
    c=oracle.get('centre');shape=oracle['shape']
    if shape in ('sphere','shell','cylinder','box','closing','vent','cone'):
        half=oracle.get('half', [oracle.get('radius',0)]*3)
        if shape=='cylinder':half=[oracle['radius'],oracle['radius'],oracle['half_height']]
        if isinstance(half,(float,int)):half=[half]*3
        checks['independent_world_bounds']=all(abs(native[label][i]-(c[i]+sign*half[i]))<=.25 for label,sign in [('low',-1),('high',1)] for i in range(3))
    desired=probes(oracle);input_file=folder/'probes.csv'
    input_file.write_text('\n'.join(','.join(str(x) for x in p['point']) for p in desired)+'\n')
    probe_output=folder/'probe-output';probe_output.mkdir()
    # This owned probe follows the trusted Inspector; only teaching candidates need the OS sandbox.
    rc=core.run([str(core.DOTNET),str(probe_binary),str(output/'part.vdb'),str(input_file),str(probe_output)],folder,90,probe_env)
    shutil.copy2(folder/'process.log',folder/'probe.log')
    if rc:raise ValueError('Trusted point probe failed.')
    actual=json.loads((probe_output/'hits.json').read_text())
    decisive=[i for i,p in enumerate(desired) if 'inside' in p]
    checks['independent_vdb_membership_probes']=all(actual['vdb'][i]==desired[i]['inside'] for i in decisive)
    stl_hits=stl_membership(output/'part.stl',[desired[i]['point'] for i in decisive])
    checks['same_solid_stl_membership_probes']=all(hit==actual['vdb'][i] for hit,i in zip(stl_hits,decisive))
    if shape in ('vent','cone'):
        checks['open_void_connectivity']=core.connectivity(occupied,native['grid'])==0
    if shape=='shell':checks['sealed_void_detected']=core.connectivity(occupied,native['grid'])>0
    if shape=='cone':checks['analytic_roof_angle_gt45']=math.degrees(math.atan(oracle['rise']/oracle['radius']))>45
    if shape=='tpms':
        ray=[(p['ray_t'],actual['vdb'][i]) for i,p in enumerate(desired) if 'ray_t' in p]
        negative=[abs(t) for t,hit in ray if t<0 and not hit];positive=[t for t,hit in ray if t>0 and not hit]
        width=min(negative)+min(positive)-.05 if negative and positive else None
        lower_bound=min(negative)+min(positive)-.10 if negative and positive else None
        # One 0.2 mm voxel projected along the diagonal bounds two-surface quantization error.
        checks['physical_mm_sheet_width']=width is not None and lower_bound>=.8-1e-9 and abs(width-oracle['wall'])<=math.sqrt(3)*.2+.05
        native['independent_nodal_ray_width_mm']=width
        native['independent_nodal_ray_width_lower_bound_mm']=lower_bound
        native['width_scope']='One independently known nodal normal, 0.05 mm sampling; not a global minimum-wall proof.'
    report=json.loads((output/'report.json').read_text())
    checks['bounded_report']=report=={'status':'geometric_candidate','qualification':'geometry_only','manufacturing_authorized':False}
    return checks,{'mesh':mesh,'native':native,'probe_source_sha256':digest(folder/'probes.csv')}


def refusal_checks(output,oracle):
    value=json.loads((output/'refused.json').read_text())
    expected={'status':'needs_measurement','manufacturing_authorized':False,'missing':oracle['missing']}
    if oracle['shape']=='unsigned-refusal':expected['input_valid']=oracle['input_valid']
    return {'strict_dynamic_refusal':value==expected,'no_geometry_exports':{p.name for p in output.iterdir()}=={'refused.json'}}


def run_case(case,all_cases,run_dir,probe_binary,probe_env):
    folder=run_dir/case['id'];folder.mkdir()
    source=ROOT/case['source'];fixture=ROOT/case['input'];oracle=case['oracle'];checks={};details={}
    result={'id':case['id'],'status':'failed','source_sha256':digest(source),'input_sha256':digest(fixture),'checks':checks}
    try:
        if result['source_sha256']!=case['source_sha256'] or result['input_sha256']!=case['input_sha256']:raise ValueError('Teaching source or fixture hash changed.')
        code=source.read_text();core.static_gate(code);checks['static_allowlist']=True
        if case['kind']=='refusal':checks['no_native_initialization']='using Library' not in code and 'new Library' not in code
        binary,env=core.build(code,folder);output=folder/'output';output.mkdir();(folder/'tmp').mkdir(exist_ok=True)
        rc=core.run([str(core.DOTNET),str(binary),str(fixture),str(output)],folder,90,env,True,output,fixture)
        shutil.copy2(folder/'process.log',folder/'run.log');result['native_exit_code']=rc;checks['native_exit_zero']=rc==0
        if rc:raise ValueError('Native candidate execution failed.')
        if case['kind']=='refusal':checks.update(refusal_checks(output,oracle))
        else:
            geometry,details=validate_geometry(output,folder,oracle,probe_binary,probe_env);checks.update(geometry)
        # Every reader must follow a different independently authored input, not cached constants.
        if case['family'] in ('scan-normals','stl-roundtrip','stl-skin-vent','xyz-occupancy','missing-interfaces','signed-range-refusal'):
            alternative=next(c for c in all_cases if c['family']==case['family'] and c['variant']==case['variant']%4+1)
            alt=folder/'alternate';alt.mkdir();alt_output=alt/'output';alt_output.mkdir();alt_input=ROOT/alternative['input']
            alt_oracle=dict(alternative['oracle'])
            if case['family']=='stl-skin-vent':alt_oracle.update(wall=oracle['wall'],vent_radius=oracle['vent_radius'])
            if case['family']=='xyz-occupancy':alt_oracle['radius']=oracle['radius']
            if case['family']=='signed-range-refusal':alt_oracle['missing']=oracle['missing']
            rc=core.run([str(core.DOTNET),str(binary),str(alt_input),str(alt_output)],folder,90,env,True,alt_output,alt_input)
            shutil.copy2(folder/'process.log',alt/'run.log');checks['alternate_native_exit_zero']=rc==0
            if rc:raise ValueError('Alternate input execution failed.')
            if case['kind']=='refusal':checks.update({'alternate_'+k:v for k,v in refusal_checks(alt_output,alt_oracle).items()})
            else:
                alt_checks,_=validate_geometry(alt_output,alt,alt_oracle,probe_binary,probe_env)
                checks.update({'alternate_'+k:v for k,v in alt_checks.items()})
        if oracle.get('parser') in ('planes','xyz') or oracle['shape'] in ('refusal','unsigned-refusal'):
            bads={}
            if oracle.get('parser')=='planes':
                lines=fixture.read_text().splitlines();header=lines[0].split(';')
                for name,column,value in [('nonfinite','x','NaN'),('zero-normal','nx','0'),('duplicate-axis','nx','0')]:
                    rows=lines.copy();fields=rows[-1].split(';')
                    if name=='nonfinite':fields[header.index(column)]=value
                    elif name=='zero-normal':
                        for axis in ('nx','ny','nz'):fields[header.index(axis)]='0'
                    else:
                        fields=rows[-2].split(';')
                    rows[-1]=';'.join(fields);bads[name]='\n'.join(rows)+'\n'
                rows=lines.copy();rows[0]=';'.join([header[0]]*6);bads['duplicate-header']='\n'.join(rows)+'\n'
            elif oracle.get('parser')=='xyz' or oracle['shape']=='unsigned-refusal':
                bads={'nonfinite':'NaN;0;0\n','column-count':'0;1\n','empty':''}
            else:
                value=json.loads(fixture.read_text());required=value['required_measurements']
                for label,measurements in [('all-missing',{}),('wrong-type',{name:'NaN' for name in required}),('all-present',{name:1.26+i*.18 for i,name in enumerate(required)})]:
                    bads[label]=json.dumps({'required_measurements':required,'measurements':measurements})
                # Valid JSON numeric overflow reaches TryGetDouble/IsFinite, unlike a NaN string.
                bads['numeric-overflow']='{"required_measurements":'+json.dumps(required)+',"measurements":{'+','.join(json.dumps(name)+':1e999' for name in required)+'}}'
            for label,text in bads.items():
                bad=folder/(label+'.dat');bad.write_text(text);bad_output=folder/(label+'-output');bad_output.mkdir()
                rc=core.run([str(core.DOTNET),str(binary),str(bad),str(bad_output)],folder,90,env,True,bad_output,bad)
                shutil.copy2(folder/'process.log',folder/(label+'.log'))
                if oracle['shape']=='unsigned-refusal':
                    check=refusal_checks(bad_output,dict(oracle,input_valid=False));checks[label+'_refusal']=rc==0 and all(check.values())
                elif oracle['shape']=='refusal':
                    data=json.loads((bad_output/'refused.json').read_text());expected={'status':'needs_engineering_review' if label=='all-present' else 'needs_measurement','manufacturing_authorized':False,'missing':[] if label=='all-present' else oracle['required']}
                    checks[label+'_dynamic_measurement_response']=rc==0 and data==expected and {p.name for p in bad_output.iterdir()}=={'refused.json'}
                else:checks['reject_'+label]=rc!=0 and not list(bad_output.iterdir())
        result['details']=details;result['status']='passed' if all(checks.values()) else 'failed'
    except (OSError,ValueError,KeyError,core.subprocess.SubprocessError) as exc:result['error']=str(exc)
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    args.run_dir=args.run_dir.resolve()
    args.run_dir.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'cases.json').read_text());cases=manifest['cases'];data=ROOT/'train.jsonl'
    if digest(data)!=manifest['train_sha256']:raise ValueError('Corpus hash changed.')
    rows=[json.loads(line) for line in data.read_text().splitlines()]
    assert len(rows)==len(cases)==64
    for row,case in zip(rows,cases):
        assert list(row)==['messages'] and [m['role'] for m in row['messages']]==['user','assistant']
        assert core.extract(row['messages'][1]['content'])==(ROOT/case['source']).read_text()
    probe_dir=args.run_dir/'trusted-probe';probe_binary,probe_env=core.build(PROBE,probe_dir);results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run_case,case,cases,args.run_dir,probe_binary,probe_env) for case in cases]
        for future in as_completed(futures):
            result=future.result();results.append(result);print(result['id'],result['status'],flush=True)
    results.sort(key=lambda r:r['id']);report={'schema':'picogk.am.compact-validation@1','train_sha256':digest(data),'cases_sha256':digest(ROOT/'cases.json'),'validator_sha256':digest(Path(__file__)),'trusted_core_sha256':digest(CORE_PATH),'checker_adjustments':['Direct STL triangle parity preserves nested cavities independently of native mesh import.','TPMS family-specific zero-set probes and conservative sampled nodal width >=0.8 mm.','Valid JSON numeric overflow exercises finite-value rejection.','Shared native builder uses trusted-runtime symlinks; candidate OS sandbox remains enabled.'],'passed':sum(r['status']=='passed' for r in results),'total':64,'tasks':results,'qualification':'software and geometry only','manufacturing_authorized':False}
    (args.run_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='tasks'},indent=2));return 0 if report['passed']==64 else 1


if __name__=='__main__':raise SystemExit(main())
