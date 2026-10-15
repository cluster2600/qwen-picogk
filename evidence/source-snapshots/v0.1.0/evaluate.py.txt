"""Repeat exposed model tests; optional trusted native recipe screen."""
import argparse
import collections
import json
import math
from pathlib import Path
import subprocess
import tempfile

import contracts
import infer


def native(plan, host, output_dir=None):
    with tempfile.TemporaryDirectory(prefix='qwen-picogk-native-') as tmp:
        folder = Path(tmp) if output_dir is None else output_dir
        if output_dir is not None:
            folder.mkdir(exist_ok=False)
        (folder/'plan.json').write_text(json.dumps(plan))
        run = subprocess.run(['dotnet', str(host.resolve()), str(folder/'plan.json'), str(folder/'raw.stl'), '0.5'],
                             capture_output=True, text=True, timeout=45, check=True)
        lines = [line for line in run.stdout.splitlines() if line.startswith('{')]
        if len(lines) != 1:
            raise ValueError('Expected exactly one native metrics record')
        result = json.loads(lines[0])
        params = plan['parameters_mm']
        okay = (result['volume'] > 0 and result['triangles'] > 0 and result['roundtrip_triangles'] == result['triangles'] and
                result['material_inside'] and not result['distant_point_inside'] and
                result['axis_inside'] == (plan['recipe'] not in ('pipe', 'washer')))
        if plan['recipe'] in ('cylinder', 'pipe', 'washer'):
            analytic = math.pi * (params[1]**2 - (params[2]**2 if len(params) == 3 else 0)) * params[0]
            result['relative_volume_error'] = abs(result['volume']-analytic)/analytic
            okay = okay and result['relative_volume_error'] <= 0.15
        if not okay:
            raise ValueError('Native recipe screen failed')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--adapter', choices=['planner', 'baseline', 'training-parent', 'selector'], default='planner')
    parser.add_argument('--split', choices=['valid', 'test'], default='test')
    parser.add_argument('--native-host', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error('Use a new output file in an existing directory')
    selector = args.adapter == 'selector'
    cases = json.loads((infer.ROOT/'data'/('selector' if selector else 'planner')/'cases.json').read_text())
    model, tokenizer = infer.load_model(args.adapter, args.base)
    results = []
    for row in cases:
        if row['split'] != args.split:
            continue
        # Evaluation sends the recorded raw user request, never its gold plan.
        text, finish = infer.generate(model, tokenizer, row['messages'][0]['content'], row['messages'][1]['content'])
        result = dict(id=row['id'], language=row['language'], text=text, finish=finish, passed=False)
        try:
            if selector:
                operation = json.loads(text, object_pairs_hook=contracts.unique)
                if finish != 'stop' or type(operation) is not dict or set(operation) != {'operation'} or operation['operation'] != row['expected']:
                    raise ValueError('Wrong or incomplete operation')
            else:
                plan = contracts.accepted(text, finish, row['request'])
                if args.native_host and plan['recipe'] != 'needs_measurement':
                    result['native'] = native(plan, args.native_host)
            result['passed'] = True
        except (ValueError, TypeError, subprocess.SubprocessError) as error:
            result['error'] = str(error)
        results.append(result)
    receipt = dict(adapter=args.adapter, split=args.split, total=len(results), passed=sum(r['passed'] for r in results),
                   by_language=dict(collections.Counter(r['language'] for r in results if r['passed'])),
                   native_checked=bool(args.native_host) and not selector, exposed_public_test=True,
                   manufacturing_qualified=False, results=results)
    with args.output.open('x') as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'results'}))


if __name__ == '__main__':
    main()
