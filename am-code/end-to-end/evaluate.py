"""Evaluate frozen fresh file-to-geometry tasks using the sibling native sandbox."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('am_native_evaluator',ROOT.parent/'evaluation/evaluate.py')
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    frozen=json.loads((ROOT/'freeze.json').read_text())
    for name,expected in frozen['files'].items():
        if digest(ROOT/name)!=expected:
            raise ValueError('Frozen scan development input changed: '+name)
    for name,expected in frozen['retained_profiles_launchers_adapters'].items():
        if digest((ROOT.parents[1]/name).resolve())!=expected:
            raise ValueError('Retained launcher/profile/adapter changed: '+name)
    return frozen


def check_geometry(task,metadata,occupied,mesh,reference=None):
    oracle=task['oracle'];grid=metadata['grid'];n=grid['n'];low=grid['low'];step=grid['step']
    def inside(point):
        indices=[round((v-low)/step) for v in point]
        if any(i<0 or i>=n for i in indices):
            raise ValueError('Probe outside registered inspector volume')
        return bool(occupied[indices[0]+n*(indices[1]+n*indices[2])])
    checks={
        'closed_oriented_positive_mesh':mesh['triangles']>0 and mesh['degenerate']==0 and mesh['boundary']==0 and mesh['nonmanifold']==0 and mesh['inconsistent']==0 and mesh['volume_mm3']>0,
        # Small balls alias on a coarse occupancy grid; integrate the oriented triangles instead.
        'independent_analytic_volume':abs(mesh['volume_mm3']-oracle['analytic_volume'])/oracle['analytic_volume']<.10,
        'independent_world_bounds':all(abs(a-b)<=.25 for name in ('low','high') for a,b in zip(metadata[name],oracle[name])),
        'independent_occupancy_probes':all(inside(p['point'])==p['inside'] for p in oracle['probes'])
    }
    if oracle.get('require_void_connectivity'):
        checks['no_trapped_void_cells']=native.connectivity(occupied,grid)==0
    if oracle['shape']=='sparse-splats':
        mismatch=0;compared=0
        # Exact Euclidean sample balls provide a source-independent occupancy oracle.
        for z in range(n):
            for y in range(n):
                for x in range(n):
                    point=[low+x*step,low+y*step,low+z*step]
                    distance=min(math.dist(point,p) for p in oracle['points'])
                    if abs(distance-oracle['radius'])<=.25:
                        continue
                    expected=distance<oracle['radius']
                    mismatch+=bool(occupied[x+n*(y+n*z)])!=expected
                    compared+=1
        checks['independent_sparse_occupancy']=mismatch==0 and compared>0
    iou=None
    if reference is not None:
        old=reference
        intersection=sum(bool(a and b) for a,b in zip(occupied,old))
        union=sum(bool(a or b) for a,b in zip(occupied,old))
        iou=intersection/union if union else 0
        checks['gold_native_occupancy_iou']=iou>=.95
    return checks,iou


def evaluate(task,code,folder,reference=None):
    result=dict(id=task['id'],status='failed',checks={},qualification='software and geometry only',
                source_sha256=hashlib.sha256(code.encode()).hexdigest())
    folder.mkdir(parents=True,exist_ok=False)
    try:
        native.static_gate(code);result['checks']['static_allowlist']=True
        binary,env=native.build(code,folder)
        fixture=folder/Path(task['input']).name
        shutil.copyfile(ROOT/task['input'],fixture)
        output=folder/'output';output.mkdir();(folder/'tmp').mkdir(exist_ok=True)
        rc=native.run([str(native.DOTNET),str(binary),str(fixture),str(output)],folder,90,env,
                      sandbox=True,output=output,input_path=fixture)
        result['native_exit_code']=rc;result['checks']['native_exit_zero']=rc==0
        if rc:
            raise ValueError('Isolated native execution failed; see process.log')
        if task['kind']=='refusal':
            report=json.loads((output/'refused.json').read_text())
            result['checks']['strict_refusal']=report==dict(status='needs_measurement',manufacturing_authorized=False,
                                                          input_valid=task['oracle']['input_valid'],missing=task['oracle']['missing'])
            result['checks']['no_geometry']=not list(output.glob('*.stl')) and not list(output.glob('*.vdb'))
        else:
            report=json.loads((output/'report.json').read_text())
            result['checks']['bounded_geometric_candidate']=report==dict(status='geometric_candidate',qualification='geometry_only',manufacturing_authorized=False)
            mesh=native.mesh_properties(output/'part.stl')
            metadata,occupied=native.inspect(output/'part.stl',folder/'inspection')
            checks,iou=check_geometry(task,metadata,occupied,mesh,reference['primary'] if reference else None)
            result['checks'].update(checks)
            result['details']=dict(native=metadata,mesh=mesh,occupancy_iou=iou)
            for input_name in task['oracle'].get('negative_inputs',[]):
                invalid=folder/Path(input_name).name;shutil.copyfile(ROOT/input_name,invalid)
                bad_output=folder/(invalid.stem+'-output');bad_output.mkdir()
                bad_rc=native.run([str(native.DOTNET),str(binary),str(invalid),str(bad_output)],folder,90,env,
                                 sandbox=True,output=bad_output,input_path=invalid)
                result['checks']['reject_'+invalid.stem]=bad_rc!=0 and not list(bad_output.glob('*.stl')) and not list(bad_output.glob('*.vdb'))
        for alternate in task['oracle'].get('additional_inputs',[]):
            name=Path(alternate['input']).stem
            subfolder=folder/'additional-inputs'/name;subfolder.mkdir(parents=True)
            invalid=subfolder/Path(alternate['input']).name;shutil.copyfile(ROOT/alternate['input'],invalid)
            alt_output=subfolder/'output';alt_output.mkdir()
            rc=native.run([str(native.DOTNET),str(binary),str(invalid),str(alt_output)],folder,90,env,
                          sandbox=True,output=alt_output,input_path=invalid)
            result['checks'][name+'_native_exit_zero']=rc==0
            if rc:
                continue
            if task['kind']=='refusal':
                refusal=json.loads((alt_output/'refused.json').read_text())
                result['checks'][name+'_strict_refusal']=refusal==dict(status='needs_measurement',manufacturing_authorized=False,
                    input_valid=alternate['input_valid'],missing=task['oracle']['missing']) and not list(alt_output.glob('*.stl')) and not list(alt_output.glob('*.vdb'))
            else:
                report=json.loads((alt_output/'report.json').read_text())
                result['checks'][name+'_bounded_geometric_candidate']=report==dict(status='geometric_candidate',qualification='geometry_only',manufacturing_authorized=False)
                alt_mesh=native.mesh_properties(alt_output/'part.stl')
                alt_native,alt_occupied=native.inspect(alt_output/'part.stl',subfolder/'inspection')
                alt_task=dict(task,oracle=alternate['oracle'])
                checks,iou=check_geometry(alt_task,alt_native,alt_occupied,alt_mesh,reference['additional'][name] if reference else None)
                result['checks'].update({name+'_'+k:v for k,v in checks.items()})
                result.setdefault('additional_details',{})[name]=dict(native=alt_native,mesh=alt_mesh,occupancy_iou=iou)
        result['status']='passed' if all(result['checks'].values()) else 'failed'
    except (OSError,ValueError,KeyError,native.subprocess.SubprocessError) as exc:
        result['error']=str(exc)
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references',action='store_true')
    parser.add_argument('--responses',type=Path,help='raw <task-id>.txt responses')
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    args.run_dir=args.run_dir.resolve()
    if args.responses is not None:args.responses=args.responses.resolve()
    if not args.references and not args.responses:
        parser.error('Use references or responses')
    verify()
    tasks=json.loads((ROOT/'development.json').read_text())['tasks']
    args.run_dir.mkdir(parents=True,exist_ok=False)
    results=[]
    for task in tasks:
        if args.references:
            code=(ROOT/task['reference']).read_text();reference=None
        else:
            gold=ROOT/'reference-validation'/task['id']
            if json.loads((gold/'result.json').read_text())['status']!='passed':
                raise ValueError('Authored scan gold must pass before inference')
            reference=dict(primary=(gold/'inspection/occupancy.bin').read_bytes(),additional={
                Path(a['input']).stem:(gold/'additional-inputs'/Path(a['input']).stem/'inspection/occupancy.bin').read_bytes()
                for a in task['oracle'].get('additional_inputs',[])}) if task['kind']=='geometry' else None
            try:
                code=native.extract((args.responses/f'{task["id"]}.txt').read_text())
            except (OSError,ValueError) as exc:
                results.append(dict(id=task['id'],status='failed',error=str(exc)));continue
        result=evaluate(task,code,args.run_dir/task['id'],reference)
        results.append(result);print(task['id'],result['status'],flush=True)
    verify()
    report=dict(development_only=True,reference_only=args.references,passed=sum(r['status']=='passed' for r in results),
                total=len(results),tasks=results,physical_qualification=False,freeze_sha256=digest(ROOT/'freeze.json'))
    (args.run_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='tasks'},indent=2))
    return 0 if report['passed']==len(results) else 1


if __name__=='__main__':
    raise SystemExit(main())
