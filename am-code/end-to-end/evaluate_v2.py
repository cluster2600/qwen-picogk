"""Score scan responses with prospective v2 lexical policy and frozen v1 native checks."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('am_scan_policy_v2', ROOT.parent / 'evaluation/policy_v2.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
spec = importlib.util.spec_from_file_location('am_scan_geometry_v1', ROOT / 'evaluate.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', action='store_true')
    parser.add_argument('--responses', type=Path, help='directory of unchanged <task-id>.txt responses')
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.references and args.responses is None:
        parser.error('Use references or responses')
    binding = policy.verify_checker_profile()
    profile_hash = binding['checker_profile_sha256']
    metadata = policy.score_metadata(binding)
    engine.native.static_gate = lambda code: policy.static_gate(code, expected_profile_sha256=profile_hash)
    engine.verify()
    tasks = json.loads((ROOT / 'development.json').read_text())['tasks']
    args.run_dir = args.run_dir.resolve()
    if args.responses is not None:
        args.responses = args.responses.resolve()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for task in tasks:
        folder = args.run_dir / task['id']
        policy.verify_reference_artifacts(task, 'end-to-end')
        if args.references:
            code = (ROOT / task['reference']).read_text()
            reference = None
        else:
            gold = ROOT / 'reference-validation' / task['id']
            if json.loads((gold / 'result.json').read_text())['status'] != 'passed':
                raise ValueError('authored scan reference must validate before candidate execution')
            reference = dict(primary=(gold / 'inspection/occupancy.bin').read_bytes(), additional={
                Path(alternate['input']).stem:
                    (gold / 'additional-inputs' / Path(alternate['input']).stem /
                     'inspection/occupancy.bin').read_bytes()
                for alternate in task['oracle'].get('additional_inputs', [])
            }) if task['kind'] == 'geometry' else None
            try:
                code = policy.extract((args.responses / (task['id'] + '.txt')).read_text(),
                                      expected_profile_sha256=profile_hash)
            except (OSError, ValueError) as exc:
                result = dict(id=task['id'], status='failed', error=str(exc), **metadata)
                folder.mkdir(parents=True, exist_ok=False)
                (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
                results.append(result)
                print(task['id'], result['status'], flush=True)
                continue
        result = engine.evaluate(task, code, folder, reference)
        result.update(metadata)
        if result['status'] == 'passed':
            if (folder / 'Program.cs').read_bytes() != code.encode('utf-8'):
                raise ValueError('compiled source differs from extracted response')
            if result['source_sha256'] != hashlib.sha256(code.encode('utf-8')).hexdigest():
                raise ValueError('passed source hash differs from compiled source')
        (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
        print(task['id'], result['status'], flush=True)
    engine.verify()
    if policy.verify_checker_profile()['checker_profile_sha256'] != profile_hash:
        raise ValueError('checker profile changed during evaluation')
    report = dict(schema=policy.SCORE_SCHEMA, development_only=True, reference_only=args.references,
                  passed=sum(row['status'] == 'passed' for row in results), total=len(results),
                  tasks=results, physical_qualification=False,
                  freeze_sha256=engine.digest(ROOT / 'freeze.json'), **metadata)
    (args.run_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'tasks'}, indent=2))
    return 0 if report['passed'] == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
