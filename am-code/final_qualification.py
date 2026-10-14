#!/usr/bin/env python3
"""Apply preregistered final software gates after validating development selection."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('am_development_qualification', ROOT / 'qualification.py')
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)
FINAL_CHECK_KEYS = frozenset({
    'development_selection_complete', 'selected_model_identities_bound', 'current_pinned_base_bound',
    'final_task_file_frozen', 'exact_final_task_ids', 'final_at_least_11_of_12', 'required_safety_passed',
    'all_final_responses_stopped', 'inference_development_selection_bound', 'model_only_final_score',
    'passed_rows_native_evidence_valid', 'passed_sources_bound', 'available_individual_results_bound',
})


def complete_final_checks(checks):
    return (isinstance(checks, dict) and set(checks) == FINAL_CHECK_KEYS
            and all(value is True for value in checks.values()))


def validate_selection(selection, current):
    if (selection.get('schema') != 'picogk.am.development-selection@1'
            or selection.get('status') != 'selected_for_final_evaluation'
            or type(selection.get('development_passes')) is not int
            or not 11 <= selection['development_passes'] <= 12
            or type(selection.get('scan_passes')) is not int or selection['scan_passes'] != 4
            or selection.get('required_safety_passed') is not True
            or not qualification.complete_checks(selection.get('checks'))
            or selection.get('qualification') != 'software and geometry only'
            or selection.get('manufacturing_authorized') is not False):
        raise ValueError('Complete current development selection is required before final task access.')
    if any(selection.get(key) != value for key, value in current.items()):
        raise ValueError('Selected model or development task identity changed.')


def final_gates(report, responses, tasks):
    expected = {t['id'] for t in tasks}
    critical = {t['id'] for t in tasks if t['family'] in qualification.CRITICAL}
    if (len(tasks) != 12 or len(expected) != 12 or len(critical) != 4
            or any(t['split'] != 'final' for t in tasks)
            or {t['family'] for t in tasks if t['family'] in qualification.CRITICAL} != qualification.CRITICAL):
        raise ValueError('Frozen final task count, split or critical family coverage is invalid.')
    passed = qualification.passes(report, expected)
    checks = {'final_at_least_11_of_12': len(passed) >= 11,
              'required_safety_passed': critical <= passed,
              'all_final_responses_stopped': qualification.stopped(responses, expected)}
    return expected, passed, checks


def validate_inference_selection(protocol, selection_hash):
    if protocol.get('selection_receipt_sha256') != selection_hash:
        raise ValueError('Final inference is not bound to the current development selection receipt.')


def reserved_input(path):
    resolved = path.resolve()
    evaluation = ROOT / 'evaluation'
    return (resolved == (evaluation / 'final.json').resolve()
            or (resolved.is_relative_to((evaluation / 'references').resolve())
                and resolved.name.startswith('final-')))


def self_check():
    current = dict.fromkeys(('adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256',
                            'development_task_sha256', 'scan_task_sha256', 'scan_freeze_sha256'), 'a' * 64)
    selection = {'schema': 'picogk.am.development-selection@1', 'status': 'selected_for_final_evaluation',
                 'development_passes': 11, 'scan_passes': 4, 'required_safety_passed': True,
                 'checks': dict.fromkeys(qualification.QUALIFICATION_CHECK_KEYS, True),
                 'qualification': 'software and geometry only', 'manufacturing_authorized': False, **current}
    validate_selection(selection, current)
    for bad in (dict(selection, checks={'required_safety_passed': True}),
                dict(selection, adapter_config_sha256='b' * 64), dict(selection, development_passes=10)):
        try:
            validate_selection(bad, current)
        except ValueError:
            continue
        raise AssertionError('Invalid development selection accepted.')
    families = sorted(qualification.CRITICAL) + [f'other-{i}' for i in range(8)]
    tasks = [{'id': f'final-{i}', 'family': family, 'split': 'final'} for i, family in enumerate(families)]
    report = {'tasks': [{'id': t['id'], 'status': 'passed', 'native_exit_code': 0,
                        'checks': {'native_exit_zero': True}} for t in tasks]}
    responses = [{'id': t['id'], 'response': 'complete response', 'finish_reason': 'stop'} for t in tasks]
    assert all(final_gates(report, responses, tasks)[2].values())
    report['tasks'][-1]['status'] = 'failed'
    assert all(final_gates(report, responses, tasks)[2].values())
    report['tasks'][-2]['status'] = 'failed'
    assert not final_gates(report, responses, tasks)[2]['final_at_least_11_of_12']
    report['tasks'][-2]['status'] = 'passed'; report['tasks'][-1]['status'] = 'passed'
    report['tasks'][0]['status'] = 'failed'
    assert not final_gates(report, responses, tasks)[2]['required_safety_passed']
    responses[0]['finish_reason'] = 'length'
    assert not final_gates(report, responses, tasks)[2]['all_final_responses_stopped']
    validate_inference_selection({'selection_receipt_sha256': 'selected'}, 'selected')
    try:
        validate_inference_selection({'selection_receipt_sha256': 'different'}, 'selected')
    except ValueError:
        pass
    else:
        raise AssertionError('Wrong inference selection receipt accepted.')
    complete = dict.fromkeys(FINAL_CHECK_KEYS, True)
    assert complete_final_checks(complete)
    assert not complete_final_checks({k: v for k, v in complete.items() if k != 'required_safety_passed'})
    assert not complete_final_checks(dict(complete, extra=True))
    import contextlib
    import io
    import sys
    from unittest.mock import patch
    bad_selection = dict(selection, checks={'required_safety_passed': True})
    def metadata_read(path):
        assert path.name != 'final.json', 'Reserved final task read before selection validation.'
        return bad_selection if path == Path('/fixture/selection.json') else {'files': {'development.json': 'a' * 64}}
    def metadata_digest(path):
        assert path.name != 'final.json', 'Reserved final task hashed before selection validation.'
        return 'a' * 64
    argv = ['final_qualification.py', '--selection-receipt', '/fixture/selection.json',
            '--final-score', '/fixture/score.json', '--final-responses', '/fixture/responses.json',
            '--adapter', '/fixture/adapter', '--output', '/fixture/output.json']
    with patch.object(sys, 'argv', argv), patch.object(qualification, 'read', side_effect=metadata_read), \
            patch.object(qualification, 'digest', side_effect=metadata_digest), \
            patch.object(qualification.base_runtime, 'verify_base', return_value={
                'base_weights_sha256': 'a' * 64, 'binding': {}}), \
            patch.object(qualification, 'verify_scan_freeze', return_value={}), contextlib.redirect_stdout(io.StringIO()):
        assert main() == 1
    argv[2] = str(ROOT / 'evaluation/final.json')
    with patch.object(sys, 'argv', argv), patch.object(qualification, 'read') as mocked_read, \
            contextlib.redirect_stdout(io.StringIO()):
        assert main() == 1 and not mocked_read.called
    print(json.dumps({'status': 'self_check_passed', 'checks': 16, 'real_final_tasks_read': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--base-profile', type=Path)
    for name in ('selection-receipt', 'final-score', 'final-responses', 'adapter', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if any(getattr(args, name) is None for name in ('selection_receipt', 'final_score', 'final_responses', 'adapter', 'output')):
        parser.error('Selection, final score/responses, adapter directory and new output paths are required.')
    try:
        adapter, config = args.adapter / 'adapters.safetensors', args.adapter / 'adapter_config.json'
        if any(reserved_input(p) for p in (args.selection_receipt, adapter, config)):
            raise ValueError('Selection/model metadata cannot alias reserved final inputs.')
        selection = qualification.read(args.selection_receipt)
        selection_hash = qualification.digest(args.selection_receipt)
        base = qualification.base_runtime.verify_base(ROOT, args.base_profile)
        qualification.base_runtime.verify_evidence(base, selection)
        current = {'adapter_sha256': qualification.digest(adapter), 'adapter_config_sha256': qualification.digest(config),
                   'base_weights_sha256': base['base_weights_sha256'],
                   'development_task_sha256': qualification.digest(ROOT / 'evaluation/development.json'),
                   'scan_task_sha256': qualification.digest(ROOT / 'end-to-end/development.json'),
                   'scan_freeze_sha256': qualification.digest(ROOT / 'end-to-end/freeze.json')}
        frozen = qualification.read(ROOT / 'evaluation/freeze.json')
        if frozen['files']['development.json'] != current['development_task_sha256']:
            raise ValueError('Frozen development tasks changed.')
        qualification.verify_scan_freeze()
        validate_selection(selection, current)
        # Reserved task bytes are accessed only after current selection/model validation.
        final_path = ROOT / 'evaluation/final.json'
        task_hash = qualification.digest(final_path)
        if task_hash != frozen['files']['final.json']:
            raise ValueError('Frozen final tasks changed.')
        tasks = qualification.read(final_path)['tasks']
        report, responses = qualification.read(args.final_score), qualification.read(args.final_responses)
        if report.get('split') != 'final' or report.get('reference_only') is not False or report.get('task_sha256') != task_hash:
            raise ValueError('Final scorer must describe model responses on the exact frozen final tasks.')
        expected, passed, gates = final_gates(report, responses, tasks)
        binding, protocol = qualification.bind_responses(args.final_responses, task_hash, current['adapter_sha256'],
                                                        expected, report, args.final_score, current['adapter_config_sha256'])
        if not passed <= set(binding['task_result_sha256']):
            raise ValueError('Every passing final task requires its individual bound result record.')
        validate_inference_selection(protocol, selection_hash)
        qualification.common_base_hash((protocol,), current['base_weights_sha256'])
        qualification.base_runtime.verify_evidence(base, protocol)
        checks = dict.fromkeys(FINAL_CHECK_KEYS, True); checks.update(gates)
        if not complete_final_checks(checks):
            print(json.dumps({'status': 'rejected', 'final_passes': len(passed), 'total': 12, 'checks': checks}, indent=2))
            return 1
        receipt = {'schema': 'picogk.am.final-qualification@1', 'status': 'qualified',
                   'created_at_utc': datetime.now(timezone.utc).isoformat(),
                   **{k: current[k] for k in ('base_weights_sha256', 'adapter_sha256', 'adapter_config_sha256')},
                   **base['binding'],
                   'development_selection_sha256': selection_hash, 'final_task_sha256': task_hash,
                   'final_passes': len(passed), 'total': 12, 'checks': checks,
                   'score_sha256': qualification.digest(args.final_score),
                   'protocol_sha256': binding['protocol_sha256'], 'responses_sha256': binding['responses_sha256'],
                   'passed_source_sha256': {r['id']: r['source_sha256'] for r in report['tasks'] if r['id'] in passed},
                   'individual_result_sha256': binding['task_result_sha256'],
                   'qualification_source_sha256': qualification.digest(Path(__file__)),
                   'development_qualification_source_sha256': qualification.digest(ROOT / 'qualification.py'),
                   'qualification': 'software and geometry only', 'manufacturing_authorized': False}
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
