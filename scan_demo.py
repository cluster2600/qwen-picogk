"""Run the guarded Qwen/tool/PicoGK demo chain; rejected meshes are never delivered."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import infer
from scan_mesh import fresh
from scan_policy import execution_plan


def command(args, log, timeout=1800):
    with log.open('w') as stream:
        subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)


def run(args):
    manifest = json.loads((ROOT/'scan-demo.json').read_text())
    infer.verify_files(ROOT,manifest['sources_sha256'])
    adapter = ROOT/'models/scan-demo'
    infer.verify_files(adapter,manifest['adapter'])
    source = args.obj.resolve(strict=True)
    output = fresh(args.output)
    source_sha = infer.digest(source)
    image = subprocess.check_output(['docker','image','inspect',manifest['geometry_image_id'],'--format','{{.Id}}'],text=True).strip()
    if image != manifest['geometry_image_id']:
        raise ValueError('Use the registered local geometry runtime')

    def geometry(stage, *paths):
        print('Geometry: '+stage,flush=True)
        command(['docker','run','--rm','--network','none','--platform','linux/amd64','--entrypoint','python3',
                 '-v',str(ROOT)+':/repo:ro','-v',str(output)+':/private:rw',
                 '-v',str(source)+':/input/scan.obj:ro',image,'/repo/scripts/scan_mesh.py',stage,*paths],
                output/(stage+'.log'))

    geometry('inspect','/input/scan.obj','/private/intake')
    audit = json.loads((output/'intake/intake.json').read_text())
    if audit['input_sha256'] != source_sha or audit['nonmanifold_edges'] or not audit['winding_consistent']:
        raise ValueError('Input changed or unsupported nonmanifold/inconsistent scan')
    request = dict(surface_topology='open' if audit['boundary_edges'] else 'closed',
                   task='end-to-end OBJ to PicoGK STL demo', triangles=audit['triangles'],
                   boundary_edges=audit['boundary_edges'],connected_surface_components=audit['connected_surface_components'],
                   units_confirmed=False,user_allows_demo_assumptions=True,
                   mm_per_source_unit_assumed=1.,voxel_mm_assumed=.5)
    print('Qwen: propose the scan-demo plan',flush=True)
    with (ROOT/'models/planner/.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        model,tokenizer = infer.load_model(base=args.base)
        import mlx.core as mx
        previous = mx.load(str(ROOT/'models/planner/adapters.safetensors'))
        weights = mx.load(str(adapter/'adapters.safetensors'))
        if previous.keys()!=weights.keys() or any(previous[k].shape!=weights[k].shape for k in previous):
            raise ValueError('Scan adapter shapes differ from the registered parent')
        model.load_weights(list(weights.items()),strict=False)
        text,finish = infer.generate(model,tokenizer,manifest['system_prompt'],json.dumps(request,separators=(',',':')))
    transcript = dict(request=request,raw_response=text,finish_reason=finish,
                      adapter_sha256=manifest['adapter']['adapters.safetensors'],model_called=True,
                      geometry_encoder=False,model_response_repaired=False)
    (output/'llm.json').write_text(json.dumps(transcript,indent=2)+'\n')
    plan = execution_plan(text,finish,request)
    del model,tokenizer,weights,previous
    mx.clear_cache()
    geometry('reconstruct','/private/intake','/private/llm.json','/private/reconstruction')
    closed = output/'reconstruction/reconstructed.stl'
    host = ROOT/'scan-native/bin/Release/net9.0/ScanDemo.dll'
    dotnet = shutil.which('dotnet')
    if dotnet is None:
        raise ValueError('Install the PicoGK .NET runtime first')
    command([dotnet,'restore',str(ROOT/'scan-native/ScanDemo.csproj'),'--locked-mode'],output/'restore.log')
    command([dotnet,'build',str(ROOT/'scan-native/ScanDemo.csproj'),'--no-restore','-c','Release'],output/'build.log')
    print('PicoGK: reconstruct the closed surface as voxels and STL',flush=True)
    command([dotnet,str(host),str(closed),infer.digest(closed),str(plan['mm_per_source_unit']),str(plan['voxel_mm']),
             str(output/'native')],output/'native.log')
    geometry('assess','/private/intake','/private/native','/private/assessment')
    quality = json.loads((output/'assessment/quality.json').read_text())
    if infer.digest(source) != source_sha:
        raise ValueError('Source changed during the chain')
    result = dict(status=quality['status'],input_sha256=source_sha,
                  model_adapter_sha256=manifest['adapter']['adapters.safetensors'],
                  sources_sha256=manifest['sources_sha256'],quality=quality,
                  assumptions=dict(mm_per_source_unit=1.,voxel_mm=.5,material='AlSi10Mg',process='laser powder bed fusion'),
                  llm_role='typed topology features to guarded tool plan; not a raw-mesh encoder or C# author',
                  human_geometry_editing=False,manufacturing_qualified=False)
    if quality['status']=='demo_geometry_passed':
        shutil.copyfile(output/'native/candidate.stl',output/'demo.stl')
        result['delivered_stl_sha256'] = infer.digest(output/'demo.stl')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status']+': '+str(output),flush=True)
    return 0 if quality['status']=='demo_geometry_passed' else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--obj',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--base',type=Path)
    parser.add_argument('--demo',action='store_true',help='Explicitly accept the documented unmeasured demo assumptions')
    args=parser.parse_args()
    if not args.demo:
        parser.error('This chain requires --demo; it does not authorise manufacture or rotation')
    try:
        raise SystemExit(run(args))
    except Exception as error:
        print('Failed closed: '+str(error),file=sys.stderr)
        raise SystemExit(2)
