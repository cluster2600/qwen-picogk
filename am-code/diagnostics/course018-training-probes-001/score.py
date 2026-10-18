"""Score one prospectively registered seen-training capture, with no qualification credit."""
import fcntl
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    tools = module('seen_training_native', ROOT / 'data/corrective-001/validate.py')
    tools.ROOT = ROOT / 'data/corrective-013'
    policy = module('seen_training_policy', ROOT / 'evaluation/policy_v2.py')
    checker = policy.verify_checker_profile()['checker_profile_sha256']
    tools.core.static_gate = lambda code: policy.static_gate(code, expected_profile_sha256=checker)
    read = lambda p: json.loads(p.read_text())
    plan = read(HERE / 'protocol.json')
    capture = HERE / 'capture'
    receipt = read(capture / 'receipt.json')
    assert plan['qualification_credit'] == 0 and len(plan['bindings']) == 4
    assert tools.digest(HERE / 'tasks.json') == plan['tasks_sha256']
    assert tools.digest(ROOT / 'data/focused-32b-008/train.jsonl') == plan['train_corpus_sha256']
    assert tools.digest(ROOT / 'infer_v2.py') == plan['infer_source_sha256']
    assert tools.digest(ROOT / 'checker-profile-v2.json') == checker == plan['checker_profile_sha256']
    assert receipt['status'] == 'completed' and receipt['count'] == 4
    assert tools.digest(capture / 'responses.json') == receipt['responses_sha256']
    assert read(capture / 'protocol.json')['adapter_sha256'] == plan['adapter_sha256']
    cases = read(tools.ROOT / 'cases.json')['cases']
    responses = read(capture / 'responses.json')
    assert {row['id'] for row in responses} == {b['id'] for b in plan['bindings']}
    output = HERE / 'native-score-001'
    output.mkdir(exist_ok=False)
    with (ROOT.parent / 'train.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binary, env = tools.core.build(tools.PROBE, output / 'trusted-probe')
        results = []
        for binding in plan['bindings']:
            case = dict(next(c for c in cases if c['id'] == binding['teacher_id']))
            assert case['source_sha256'] == binding['teacher_source_sha256']
            assert case['input_sha256'] == binding['input_sha256']
            raw = capture / (binding['id'] + '.txt')
            try:
                code = tools.core.extract(raw.read_text())
                source = output / (binding['id'] + '.cs')
                source.write_text(code)
                case.update(id=binding['id'], source=str(source), source_sha256=tools.digest(source))
                result = tools.run_case(case, cases, output, binary, env)
            except ValueError as error:
                result = dict(id=binding['id'], status='failed', error=str(error), checks={})
            result['original_raw_answer_sha256'] = tools.digest(raw)
            result['known_training_case'] = True
            result['qualification_credit'] = 0
            results.append(result)
            print(binding['id'], result['status'], flush=True)
        assert policy.verify_checker_profile()['checker_profile_sha256'] == checker
    report = dict(schema='picogk.am.seen-training-reproduction@1', total=4,
        passed=sum(r['status'] == 'passed' for r in results), tasks=results,
        protocol_sha256=tools.digest(HERE / 'protocol.json'), responses_sha256=receipt['responses_sha256'],
        scorer_source_sha256=tools.digest(Path(__file__)), checker_profile_sha256=checker,
        known_training_cases=True, qualification_credit=0, no_answer_repairs=True,
        final_contents_read=False, manufacturing_authorized=False)
    with (output / 'report.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}))


if __name__ == '__main__':
    main()
