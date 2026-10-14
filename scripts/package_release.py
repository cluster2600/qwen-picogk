"""Build only the verified, allowlisted GitHub/HF release artifacts."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from check_release import ROOT, check


def main():
    check(weights=True)
    output = ROOT/'.release'
    output.mkdir(exist_ok=True)
    assets = {}
    for name in ('planner', 'selector', 'baseline', 'training-parent'):
        target = output/(name+'-mlx.zip')
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for filename in ('adapters.safetensors', 'adapter_config.json'):
                archive.write(ROOT/'models'/name/filename, f'models/{name}/{filename}')
            archive.write(ROOT/'LICENSE', f'models/{name}/LICENSE')
            archive.write(ROOT/'NOTICE', f'models/{name}/NOTICE')
        assets[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        if name in ('planner', 'selector'):
            staging = output/'huggingface'/name
            staging.mkdir(parents=True, exist_ok=True)
            for filename in ('adapters.safetensors', 'adapter_config.json'):
                shutil.copyfile(ROOT/'models'/name/filename, staging/filename)
            for filename in ('LICENSE', 'NOTICE', 'release.json'):
                shutil.copyfile(ROOT/filename, staging/filename)
            shutil.copyfile(ROOT/'hub'/name/'README.md', staging/'README.md')
    staging = output/'huggingface/dataset'
    staging.mkdir(parents=True, exist_ok=True)
    for filename in ('LICENSE', 'NOTICE', 'release.json'):
        shutil.copyfile(ROOT/filename, staging/filename)
    shutil.copyfile(ROOT/'hub/dataset/README.md', staging/'README.md')
    manifest = json.loads((ROOT/'release.json').read_text())
    for name in manifest['data_files']:
        destination = staging/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
    (output/'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name, sha in assets.items()))
    print(json.dumps({'archives': assets, 'hf_staging': ['planner', 'selector', 'dataset'], 'base_weights_included': False}, indent=2))


if __name__ == '__main__':
    main()
