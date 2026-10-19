"""Run unchanged native teaching oracles against the new correction cases."""
import fcntl
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    tools = module('prior_teaching_validator', WORK / 'data/corrective-001/validate.py')
    tools.ROOT = ROOT
    policy = module('teaching_v2_policy', WORK / 'evaluation/policy_v2.py')
    checker = policy.verify_checker_profile()['checker_profile_sha256']
    tools.core.static_gate = lambda code: policy.static_gate(code, expected_profile_sha256=checker)
    manifest = json.loads((ROOT / 'cases.json').read_text())
    cases = manifest['cases']
    assert len(cases) == manifest['count'] == 8
    assert tools.digest(ROOT / 'train.jsonl') == manifest['train_sha256']
    rows = [json.loads(line) for line in (ROOT / 'train.jsonl').read_text().splitlines()]
    assert len(rows) == len(cases)
    for row, case in zip(rows, cases):
        assert [m['role'] for m in row['messages']] == ['user', 'assistant']
        assert tools.core.extract(row['messages'][1]['content']) == (ROOT / case['source']).read_text()
    output = ROOT / 'native-review-001'
    output.mkdir(exist_ok=False)
    with (WORK.parent / 'train.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binary, env = tools.core.build(tools.PROBE, output / 'trusted-probe')
        results = []
        for case in cases:
            result = tools.run_case(case, cases, output, binary, env)
            results.append(result)
            print(case['id'], result['status'], flush=True)
        assert policy.verify_checker_profile()['checker_profile_sha256'] == checker
    report = dict(schema='picogk.am.typed-validation@2', total=8,
        passed=sum(r['status'] == 'passed' for r in results), tasks=results,
        checker_profile_sha256=checker, train_sha256=tools.digest(ROOT / 'train.jsonl'),
        cases_sha256=tools.digest(ROOT / 'cases.json'), validator_sha256=tools.digest(Path(__file__)),
        reused_validator_sha256=tools.digest(WORK / 'data/corrective-001/validate.py'),
        reused_native_engine_sha256=tools.digest(WORK / 'evaluation/evaluate.py'),
        acceptance_thresholds_changed=False, cases_run_serially=True,
        final_contents_read=False, model_or_gpu_used=False, manufacturing_authorized=False)
    (output / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, indent=2))
    return 0 if report['passed'] == 8 else 1


if __name__ == '__main__':
    raise SystemExit(main())
