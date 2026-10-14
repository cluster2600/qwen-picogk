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
    print(json.dumps({'data_files_verified': len(manifest['data_files']), 'synthetic_cases': len(cases),
                      'training_rows': len(rows), 'weights_verified': weights, 'dataset_code_executed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', action='store_true')
    check(parser.parse_args().weights)
