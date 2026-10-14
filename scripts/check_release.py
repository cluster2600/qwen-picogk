"""Check public release inputs without loading MLX or executing dataset code."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import contracts


def check(weights=False):
    manifest = json.loads((ROOT/'release.json').read_text())
    files = dict(manifest['data_files'])
    if weights:
        for name, bindings in manifest['adapters'].items():
            files.update({f'models/{name}/{p}': sha for p, sha in bindings.items()})
    for name, sha in files.items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Release hash mismatch: '+name)
    cases = json.loads((ROOT/'data/planner/cases.json').read_text())
    intents = {}
    for split, count in [('train', 720), ('valid', 60), ('test', 60)]:
        partition = [row for row in cases if row['split'] == split]
        assert len(partition) == count
        assert len({row['id'] for row in partition}) == count
        assert all(contracts.normalize(row['request']) == row['expected'] for row in partition)
        intents[split] = {json.dumps(row['expected'], sort_keys=True) for row in partition if row['expected']['recipe'] != 'needs_measurement'}
    assert not (intents['train'] & intents['valid'] or intents['train'] & intents['test'] or intents['valid'] & intents['test'])
    rows = [json.loads(line) for line in (ROOT/'data/planner/train.jsonl').read_text().splitlines()]
    assert len(rows) == 2096 and rows[720:1408] == rows[1408:]
    assert rows[:720] == [{'messages': row['messages']} for row in cases if row['split'] == 'train']
    forbidden = re.compile(r'/Users/|-----BEGIN .*PRIVATE KEY|Bearer [A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{20,}|VIN\s*[:=]', re.I)
    for row in rows:
        assert set(row) == {'messages'}
        assert [m['role'] for m in row['messages']] == ['system', 'user', 'assistant']
        assert all(type(m['content']) is str for m in row['messages'])
        assert not forbidden.search(json.dumps(row))
    registry = json.loads((ROOT/'native/sources.json').read_text())
    for repository, record in registry.items():
        folder = ROOT/'native/vendor'/repository.split('/')[-1]
        assert record['license'] == 'Apache-2.0'
        for name, sha in record['files'].items():
            assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == sha
    for relative in ['data/planner/README.md', 'hub/planner/README.md', 'hub/selector/README.md', 'hub/dataset/README.md']:
        text = (ROOT/relative).read_text()
        assert 'apache-2.0' in text and '/Users/' not in text
    gallery = ROOT/'docs/visuals/generated'
    if (gallery/'gallery.json').exists():
        receipt = json.loads((gallery/'gallery.json').read_text())
        assert receipt['adapter_sha256'] == manifest['adapters']['planner']['adapters.safetensors']
        assert receipt['corpus_sha256'] == manifest['data_files']['data/planner/cases.json']
        assert len(receipt['records']) == 5
        for record in receipt['records']:
            folder = gallery/record['recipe']
            transcript = json.loads((folder/'llm.json').read_text())
            request = json.loads((folder/'request.json').read_text())
            plan = contracts.accepted(transcript['raw_response'], transcript['finish_reason'], request)
            assert plan == json.loads((folder/'plan.json').read_text())
            assert plan['parameters_mm'] == record['parameters_mm']
            assert transcript['canonical_input'] is False and record['model_called'] is True
            assert record['geometry_screen_passed'] and not record['manufacturing_qualified']
            for name, sha in record['files_sha256'].items():
                path = (gallery/name).resolve()
                assert path.is_relative_to(gallery.resolve())
                assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
            assert (folder/'render.png').read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
        assert hashlib.sha256((gallery/'overview.png').read_bytes()).hexdigest() == receipt['overview_sha256']
        for name, sha in receipt['source_sha256'].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == sha
        assert hashlib.sha256((ROOT/'scripts/render_gallery.py').read_bytes()).hexdigest() == receipt['rendering']['source_sha256']
    advanced = ROOT/'docs/visuals/advanced'
    if (advanced/'manifest.json').exists():
        bindings = json.loads((advanced/'manifest.json').read_text())
        for name, sha in bindings['files_sha256'].items():
            path=(ROOT/name).resolve()
            assert path.is_relative_to(ROOT)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
        rejected=json.loads((advanced/'diffuser-rejected.json').read_text())
        assert rejected['finish_reason']=='length' and not rejected['code_executed'] and not rejected['scan_input']
        probe=json.loads((advanced/'spaceframe/llm.json').read_text())
        from check_beam_code import admitted
        assert len(admitted(probe['raw_response'],probe['finish_reason'],probe))==6
        assert probe['code_executed'] and probe['native_compilation_passed'] and not probe['model_response_repaired']
        assert probe['adapter_sha256']==manifest['adapters']['planner']['adapters.safetensors']
        metrics=json.loads((advanced/'spaceframe/native.json').read_text())
        assert metrics['volume']>0 and metrics['all_beam_midpoints_inside']
        assert metrics['triangles']==metrics['roundtrip_triangles'] and not metrics['manufacturing_qualified']
    for name in ['bcc','thread','spaceframe']:
        gif=ROOT/'docs/visuals/animations'/(name+'.gif')
        if not gif.exists():continue
        receipt=json.loads(gif.with_suffix('.json').read_text())
        mesh=(advanced/'spaceframe/raw.stl')if name=='spaceframe'else gallery/name/'raw.stl'
        assert hashlib.sha256(mesh.read_bytes()).hexdigest()==receipt['mesh_sha256']
        assert hashlib.sha256(gif.read_bytes()).hexdigest()==receipt['gif_sha256']
        assert gif.read_bytes()[:6]in[b'GIF87a',b'GIF89a']
        assert receipt['frames']==24 and receipt['loop']==0 and not receipt['geometry_changed']
        assert hashlib.sha256((ROOT/'scripts/animate_mesh.py').read_bytes()).hexdigest()==receipt['source_sha256']
    print(json.dumps({'data_files_verified': len(manifest['data_files']), 'synthetic_cases': len(cases),
                      'training_rows': len(rows), 'weights_verified': weights, 'dataset_code_executed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', action='store_true')
    check(parser.parse_args().weights)
