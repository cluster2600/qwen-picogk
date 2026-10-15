#!/usr/bin/env python3
"""Select an adapter for reserved final evaluation using fixed development gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('am_qualification_base_runtime', ROOT / 'base_runtime.py')
base_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_runtime)
CRITICAL = {'vent', 'cone-roof', 'scan-normals', 'missing-interfaces'}
QUALIFICATION_CHECK_KEYS = frozenset({
    'development_at_least_11_of_12', 'required_safety_passed', 'retains_all_baseline_passes',
    'all_four_scan_tasks_pass', 'all_candidate_responses_stopped', 'all_scan_responses_stopped',
    'passed_rows_native_evidence_valid', 'passed_sources_bound', 'available_individual_results_bound',
    'inference_task_adapter_config_bound', 'current_pinned_base_bound', 'frozen_development_tasks_bound',
    'frozen_scan_files_and_retained_profiles_bound', 'model_only_scores', 'score_task_freeze_bindings_valid',
})


def complete_checks(checks):
    return (isinstance(checks, dict) and set(checks) == QUALIFICATION_CHECK_KEYS
            and all(value is True for value in checks.values()))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def indexed(rows, expected):
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Expected a list of task records.')
    values = {r['id']: r for r in rows}
    if len(values) != len(rows) or set(values) != expected:
        raise ValueError('Missing, duplicate or unexpected task IDs.')
    return values


def passes(report, expected):
    rows = indexed(report['tasks'], expected)
    if any(r['status'] not in ('passed', 'failed') for r in rows.values()):
        raise ValueError('Unknown scorer task status.')
    for row in rows.values():
        if row['status'] != 'passed':
            continue
        checks = row.get('checks')
        if (type(row.get('native_exit_code')) is not int or row['native_exit_code'] != 0
                or not isinstance(checks, dict) or not checks
                or any(type(value) is not bool or not value for value in checks.values())):
            raise ValueError('Passed task lacks successful native exit and complete Boolean checks.')
    return {key for key, row in rows.items() if row['status'] == 'passed'}


def stopped(responses, expected):
    rows = indexed(responses, expected)
    return all(r.get('finish_reason') == 'stop' and isinstance(r.get('response'), str)
               and r['response'].strip() for r in rows.values())


def gate(baseline, candidate, scan, responses, scan_responses, expected, scan_ids, critical):
    if len(expected) != 12 or len(scan_ids) != 4 or len(critical) != 4 or not critical <= expected:
        raise ValueError('Fixed development gate requires 12 tasks, four critical and four scan tasks.')
    old = passes(baseline, expected)
    new = passes(candidate, expected)
    scan_passes = passes(scan, scan_ids)
    checks = {
        'development_at_least_11_of_12': len(new) >= 11,
        'required_safety_passed': critical <= new,
        'retains_all_baseline_passes': old <= new,
        'all_four_scan_tasks_pass': scan_passes == scan_ids,
        'all_candidate_responses_stopped': stopped(responses, expected),
        'all_scan_responses_stopped': stopped(scan_responses, scan_ids),
    }
    return {'passed': all(checks.values()), 'checks': checks,
            'development_passes': len(new), 'scan_passes': len(scan_passes),
            'lost_baseline_passes': sorted(old - new)}


def bind_responses(path, task_hash, adapter_hash, expected, report, score_path, config_hash=None):
    rows = indexed(read(path), expected)
    protocol_path = path.parent / 'protocol.json'
    protocol = read(protocol_path)
    if (protocol['tasks_sha256'] != task_hash or protocol['adapter_sha256'] != adapter_hash
            or protocol['adapter_config_sha256'] != config_hash
            or set(protocol['task_ids']) != expected or len(protocol['task_ids']) != len(expected)):
        raise ValueError('Inference protocol task, adapter or configuration binding mismatch.')
    result_hashes = {}
    for result in report['tasks']:
        result_path = score_path.parent / result['id'] / 'result.json'
        if result_path.exists():
            if read(result_path) != result:
                raise ValueError('Individual task result differs from aggregate scorer report.')
            result_hashes[result['id']] = digest(result_path)
    # A passed score must describe the captured response that was actually compiled.
    for task_id in passes(report, expected):
        fences = re.findall(r'```(?:csharp|cs|C#)\s*\n(.*?)```', rows[task_id]['response'], re.S)
        code = fences[0].strip() + '\n' if len(fences) == 1 else ''
        result = next(r for r in report['tasks'] if r['id'] == task_id)
        if (not code or (score_path.parent / task_id / 'Program.cs').read_text() != code
                or result.get('source_sha256') != hashlib.sha256(code.encode()).hexdigest()):
            raise ValueError('Passed scorer source differs from captured model response.')
    return {'responses_sha256': digest(path), 'protocol_sha256': digest(protocol_path),
            'task_result_sha256': result_hashes}, protocol


def common_base_hash(protocols, pinned_hash=None):
    values = [p['base_weights_sha256'] for p in protocols]
    if (any(not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{64}', v) is None for v in values)
            or len(set(values)) != 1 or (pinned_hash is not None and values[0] != pinned_hash)):
        raise ValueError('Baseline and candidate base hashes are absent, invalid or different.')
    return values[0]


def verify_scan_freeze():
    frozen = read(ROOT / 'end-to-end/freeze.json')
    if frozen.get('schema') != 'qwen.picogk.am.scan-freeze@1' or frozen.get('development_only') is not True:
        raise ValueError('Expected a development-only scan freeze.')
    for field in ('files', 'retained_profiles_launchers_adapters'):
        if not isinstance(frozen.get(field), dict) or not frozen[field]:
            raise ValueError('Missing frozen scan or retained-profile bindings.')
    for name, expected in frozen['files'].items():
        relative = Path(name)
        resolved = (ROOT / 'end-to-end' / relative).resolve()
        if (relative.is_absolute() or '..' in relative.parts
                or not resolved.is_relative_to((ROOT / 'end-to-end').resolve())
                or any(p == 'final.json' or p.startswith('final-') for p in resolved.parts)):
            raise ValueError('Scan freeze must contain only its development files.')
        if digest(resolved) != expected:
            raise ValueError('Frozen scan file changed: ' + name)
    for name, expected in frozen['retained_profiles_launchers_adapters'].items():
        resolved = (ROOT.parent / name).resolve() if not Path(name).is_absolute() else Path(name).resolve()
        if any(p == 'final.json' or p.startswith('final-') for p in resolved.parts):
            raise ValueError('Retained profile binding must not access reserved final tasks.')
        if digest(resolved) != expected:
            raise ValueError('Retained launcher/profile/adapter changed: ' + name)
    return frozen


def self_check():
    complete = dict.fromkeys(QUALIFICATION_CHECK_KEYS, True)
    assert complete_checks(complete)
    assert not complete_checks({k: v for k, v in complete.items() if k != 'all_four_scan_tasks_pass'})
    assert not complete_checks(dict(complete, extra=True))
    expected = {f'development-{i}' for i in range(12)}
    critical = {f'development-{i}' for i in range(4)}
    scans = {f'scan-{i}' for i in range(4)}
    score = lambda ids: {'tasks': [{'id': i, 'status': 'passed', 'native_exit_code': 0,
                                  'checks': {'native_exit_zero': True}} for i in sorted(ids)]}
    response = lambda ids: [{'id': i, 'response': 'complete response', 'finish_reason': 'stop'} for i in sorted(ids)]
    baseline, candidate, scan = score(expected), score(expected), score(scans)
    answers, scan_answers = response(expected), response(scans)
    check = lambda c=candidate, a=answers, s=scan: gate(baseline, c, s, a, scan_answers, expected, scans, critical)
    assert check()['passed']
    eleven = score(expected); eleven['tasks'][-1]['status'] = 'failed'
    assert gate(eleven, eleven, scan, answers, scan_answers, expected, scans, critical)['passed']
    ten = score(expected)
    for row in ten['tasks'][-2:]: row['status'] = 'failed'
    assert not gate(ten, ten, scan, answers, scan_answers, expected, scans, critical)['passed']
    lost = score(expected); lost['tasks'][-1]['status'] = 'failed'
    assert not check(c=lost)['passed'] and check(c=lost)['lost_baseline_passes']
    failed_critical = score(expected); failed_critical['tasks'][0]['status'] = 'failed'
    assert not check(c=failed_critical)['checks']['required_safety_passed']
    truncated = response(expected); truncated[0]['finish_reason'] = 'length'
    assert not check(a=truncated)['passed']
    failed_scan = score(scans); failed_scan['tasks'][0]['status'] = 'failed'
    assert not check(s=failed_scan)['passed']
    for bad in (answers[:-1], answers[:-1] + [answers[0]]):
        try:
            check(a=bad)
        except ValueError:
            continue
        raise AssertionError('Missing or duplicate responses accepted.')
    for exit_code, checks in ((1, {'native_exit_zero': True}),
                              (0, {'native_exit_zero': False}), (0, {}), (0, {'native_exit_zero': 1})):
        bad_score = score(expected)
        bad_score['tasks'][0].update(native_exit_code=exit_code, checks=checks)
        try:
            check(c=bad_score)
        except ValueError:
            continue
        raise AssertionError('Passed status accepted despite invalid native/check evidence.')
    from unittest.mock import patch
    code = 'source\n'
    source_hash = hashlib.sha256(code.encode()).hexdigest()
    protocol = {'tasks_sha256': 'tasks', 'adapter_sha256': 'adapter',
                'adapter_config_sha256': 'config', 'task_ids': ['task']}
    def binding(p, source=source_hash, has_result=False, result_status='passed'):
        record = {'id': 'task', 'status': 'passed', 'source_sha256': source,
                  'native_exit_code': 0, 'checks': {'native_exit_zero': True}}
        with patch(__name__ + '.read', side_effect=[
                [{'id': 'task', 'response': '```csharp\nsource\n```'}], p]
                + ([dict(record, status=result_status)] if has_result else [])), \
                patch(__name__ + '.digest', return_value='digest'), \
                patch.object(Path, 'read_text', return_value=code), patch.object(Path, 'exists', return_value=has_result):
            return bind_responses(Path('/fixture/responses.json'), 'tasks', 'adapter', {'task'},
                                  {'tasks': [record]},
                                  Path('/fixture/report.json'), 'config')
    assert binding(protocol)
    assert binding(protocol, has_result=True)[0]['task_result_sha256'] == {'task': 'digest'}
    for p, source in ((dict(protocol, tasks_sha256='wrong'), source_hash),
                      (dict(protocol, adapter_sha256='wrong'), source_hash),
                      (dict(protocol, adapter_config_sha256='wrong'), source_hash), (protocol, 'stale')):
        try:
            binding(p, source)
        except ValueError:
            continue
        raise AssertionError('Incorrect task/adapter/source binding accepted.')
    try:
        binding(protocol, has_result=True, result_status='failed')
    except ValueError:
        pass
    else:
        raise AssertionError('Individual result disagrees with aggregate score.')
    assert common_base_hash([{'base_weights_sha256': 'a' * 64}] * 3) == 'a' * 64
    for values in ((None,) * 3, ('',) * 3, ('a' * 64, 'a' * 64, 'b' * 64)):
        try:
            common_base_hash([{'base_weights_sha256': v} for v in values])
        except ValueError:
            continue
        raise AssertionError('Missing or mismatched base binding accepted.')
    try:
        common_base_hash([{'base_weights_sha256': 'a' * 64}] * 3, 'b' * 64)
    except ValueError:
        pass
    else:
        raise AssertionError('Shared base hash differs from installed pinned weights.')
    frozen = {'schema': 'qwen.picogk.am.scan-freeze@1', 'development_only': True,
              'files': {'input.xyz': 'good'}, 'retained_profiles_launchers_adapters': {'/fixture/profile.json': 'good'}}
    with patch(__name__ + '.read', return_value=frozen), patch(__name__ + '.digest', return_value='good'):
        assert verify_scan_freeze() == frozen
    for changed in ('input.xyz', 'profile.json'):
        with patch(__name__ + '.read', return_value=frozen), patch(__name__ + '.digest',
                side_effect=lambda p: 'changed' if p.name == changed else 'good'):
            try:
                verify_scan_freeze()
            except ValueError:
                continue
            raise AssertionError('Frozen input or retained profile change accepted.')
    with patch(__name__ + '.read', return_value=dict(frozen, files={'final.json': 'good'})), \
            patch(__name__ + '.digest') as mocked_digest:
        try:
            verify_scan_freeze()
        except ValueError:
            assert not mocked_digest.called
        else:
            raise AssertionError('Reserved final task was accessed through scan freeze.')
    with patch(__name__ + '.read', return_value=dict(frozen,
            retained_profiles_launchers_adapters={'/fixture/final.json': 'good'})), \
            patch(__name__ + '.digest', return_value='good') as mocked_digest:
        try:
            verify_scan_freeze()
        except ValueError:
            assert all(call.args[0].name != 'final.json' for call in mocked_digest.call_args_list)
        else:
            raise AssertionError('Retained-profile binding accessed a reserved final task.')
    print(json.dumps({'status': 'self_check_passed', 'checks': 31}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--base-profile', type=Path)
    for name in ('baseline-development', 'candidate-development', 'end-to-end',
                 'baseline-responses', 'candidate-responses', 'scan-responses', 'adapter', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if any(getattr(args, name) is None for name in ('baseline_development', 'candidate_development',
            'end_to_end', 'baseline_responses', 'candidate_responses', 'scan_responses', 'adapter', 'output')):
        parser.error('All report, response, adapter and output paths are required.')
    try:
        base = base_runtime.verify_base(ROOT, args.base_profile)
        tasks_path, scans_path = ROOT / 'evaluation/development.json', ROOT / 'end-to-end/development.json'
        task_hash, scan_hash = digest(tasks_path), digest(scans_path)
        scan_frozen = verify_scan_freeze()
        scan_freeze_hash = digest(ROOT / 'end-to-end/freeze.json')
        if (read(ROOT / 'evaluation/freeze.json')['files']['development.json'] != task_hash
                or scan_frozen['files']['development.json'] != scan_hash):
            raise ValueError('Frozen development task files changed.')
        tasks, scan_tasks = read(tasks_path)['tasks'], read(scans_path)['tasks']
        expected, scan_ids = {t['id'] for t in tasks}, {t['id'] for t in scan_tasks}
        critical = {t['id'] for t in tasks if t['family'] in CRITICAL}
        if (len(tasks) != 12 or len(scan_tasks) != 4
                or {t['family'] for t in tasks if t['family'] in CRITICAL} != CRITICAL):
            raise ValueError('Fixed task count or required family coverage changed.')
        baseline, candidate, scan = read(args.baseline_development), read(args.candidate_development), read(args.end_to_end)
        if any(r.get('reference_only') is not False for r in (baseline, candidate, scan)):
            raise ValueError('Only scored model responses may qualify, not references.')
        if (baseline.get('task_sha256') != task_hash or candidate.get('task_sha256') != task_hash
                or scan.get('freeze_sha256') != scan_freeze_hash):
            raise ValueError('Scorer report task/freeze binding mismatch.')
        adapter = args.adapter / 'adapters.safetensors' if args.adapter.is_dir() else args.adapter
        adapter_hash = digest(adapter)
        config_hash = digest(adapter.parent / 'adapter_config.json')
        old_binding, old_protocol = bind_responses(args.baseline_responses, task_hash, None, expected, baseline, args.baseline_development)
        new_binding, new_protocol = bind_responses(args.candidate_responses, task_hash, adapter_hash, expected, candidate, args.candidate_development, config_hash)
        scan_binding, scan_protocol = bind_responses(args.scan_responses, scan_hash, adapter_hash, scan_ids, scan, args.end_to_end, config_hash)
        base_hash = common_base_hash((old_protocol, new_protocol, scan_protocol),
                                     base['base_weights_sha256'])
        base_runtime.verify_evidence(base, old_protocol, new_protocol, scan_protocol)
        result = gate(baseline, candidate, scan, read(args.candidate_responses), read(args.scan_responses), expected, scan_ids, critical)
        if not result['passed']:
            print(json.dumps({'status': 'rejected', **result}, indent=2))
            return 1
        receipt = {'schema': 'picogk.am.development-selection@1', 'status': 'selected_for_final_evaluation',
                   'created_at_utc': datetime.now(timezone.utc).isoformat(), 'adapter_sha256': adapter_hash,
                   'adapter_config_sha256': config_hash,
                   'base_weights_sha256': base_hash,
                   **base['binding'],
                   'development_task_sha256': task_hash, 'scan_task_sha256': scan_hash,
                   'scan_freeze_sha256': scan_freeze_hash,
                   'verified_scan_file_count': len(scan_frozen['files']),
                   'verified_retained_profile_launcher_adapter_count': len(scan_frozen['retained_profiles_launchers_adapters']),
                   'baseline_score_sha256': digest(args.baseline_development),
                   'candidate_score_sha256': digest(args.candidate_development),
                   'scan_score_sha256': digest(args.end_to_end),
                   'response_bindings': {'baseline': old_binding, 'candidate': new_binding, 'scan': scan_binding},
                   'development_passes': result['development_passes'], 'required_safety_passed': True,
                   'scan_passes': result['scan_passes'],
                   'checks': {**result['checks'], 'passed_rows_native_evidence_valid': True,
                              'passed_sources_bound': True, 'available_individual_results_bound': True,
                              'inference_task_adapter_config_bound': True, 'current_pinned_base_bound': True,
                              'frozen_development_tasks_bound': True, 'frozen_scan_files_and_retained_profiles_bound': True,
                              'model_only_scores': True, 'score_task_freeze_bindings_valid': True},
                   'qualification': 'software and geometry only',
                   'manufacturing_authorized': False}
        if not complete_checks(receipt['checks']):
            raise ValueError('Selection receipt lacks the exact qualification check map.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            stream.write(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
