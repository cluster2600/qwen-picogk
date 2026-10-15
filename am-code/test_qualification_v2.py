#!/usr/bin/env python3
"""Focused CPU-only v2 binding checks; all final tasks are synthetic temp fixtures."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def run_checks():
    final = load('am_test_final_v2', ROOT / 'final_qualification_v2.py')
    q = final.qualification
    checks = []
    checker = 'c' * 64
    verified = {'checker_profile_sha256': checker,
                'profile': {'schema': 'picogk.am.checker-profile@2', 'policy': q.CHECKER_POLICY}}

    def good(name, condition):
        assert condition, name
        checks.append(name)

    def rejects(name, operation):
        try:
            operation()
        except (ValueError, OSError, KeyError, TypeError):
            checks.append(name)
            return
        raise AssertionError(name + ': invalid evidence accepted')

    row = {'id': 'fixture', 'checker_policy': q.CHECKER_POLICY, 'checker_profile_sha256': checker}
    report = {'schema': q.SCORE_SCHEMA, 'checker_policy': q.CHECKER_POLICY,
              'checker_profile_sha256': checker, 'tasks': [row]}
    q.require_score_profiles(checker, report, report, report)
    good('matching_three_report_profiles', True)
    for name, bad in (
        ('missing_report_profile', {key: value for key, value in report.items() if key != 'checker_profile_sha256'}),
        ('legacy_report', dict(report, schema='picogk.am.native-score@1')),
        ('mixed_report', dict(report, checker_profile_sha256='d' * 64)),
        ('mixed_policy', dict(report, checker_policy='regex-static-allowlist@1')),
        ('mixed_individual_row', dict(report, tasks=[dict(row, checker_profile_sha256='d' * 64)])),
        ('missing_individual_row_profile', dict(report, tasks=[{'id': 'fixture'}])),
        ('empty_rows', dict(report, tasks=[])),
    ):
        rejects(name, lambda bad=bad: q.require_score_profiles(checker, report, bad, report))
    rejects('empty_current_profile', lambda: q.require_score_profiles('', report))
    q.require_protocol_profiles(checker, {})  # Existing baseline captures can be regraded.
    good('immutable_legacy_baseline_protocol_allowed', True)
    rejects('new_capture_requires_profile', lambda: q.require_protocol_profiles(checker, {}, required=True))
    rejects('declared_protocol_mismatch', lambda: q.require_protocol_profiles(checker, {'checker_profile_sha256': 'd' * 64}))
    good('development_exact_15_checks', len(q.QUALIFICATION_CHECK_KEYS) == 15)
    good('final_exact_13_checks', len(final.FINAL_CHECK_KEYS) == 13)
    good('development_gate_is_v1_function', q.gate is q.core.gate)
    good('final_gate_is_v1_function', final.final_gates is final.core.final_gates)

    # This fixture verifies actual file/hash/compiled-source binding with tiny inert files.
    # Its synthetic final.json is outside the AM workspace and contains no reserved data.
    with TemporaryDirectory(prefix='am-v2-qualification-') as temporary, ExitStack() as stack:
        work = Path(temporary)
        for name in ('qualification.py', 'qualification_v2.py', 'final_qualification.py', 'final_qualification_v2.py'):
            (work / name).write_bytes((ROOT / name).read_bytes())
        for module in (q, q.core, final):
            stack.enter_context(patch.object(module, 'ROOT', work))
        stack.enter_context(patch.object(q, 'verify_checker_profile', return_value=verified))
        families = sorted(q.CRITICAL) + ['ordinary-' + str(i) for i in range(8)]
        dev = [{'id': 'dev-' + str(i), 'family': family, 'split': 'development'}
               for i, family in enumerate(families)]
        scans = [{'id': 'scan-' + str(i), 'family': 'scan', 'split': 'development'} for i in range(4)]
        final_tasks = [{'id': 'synthetic-final-' + str(i), 'family': family, 'split': 'final'}
                       for i, family in enumerate(families)]
        put(work / 'evaluation/development.json', {'tasks': dev})
        put(work / 'end-to-end/development.json', {'tasks': scans})
        put(work / 'evaluation/final.json', {'tasks': final_tasks})
        put(work / 'evaluation/freeze.json', {'files': {
            'development.json': q.digest(work / 'evaluation/development.json'),
            'final.json': q.digest(work / 'evaluation/final.json')}})
        (work / 'retained.txt').write_text('historical retained fixture\n')
        put(work / 'end-to-end/freeze.json', {'schema': 'qwen.picogk.am.scan-freeze@1',
            'development_only': True,
            'files': {'development.json': q.digest(work / 'end-to-end/development.json')},
            'retained_profiles_launchers_adapters': {str(work / 'retained.txt'): q.digest(work / 'retained.txt')}})
        model = work / 'model-fixture'
        model.mkdir()
        for name in q.base_runtime.BASE_NAMES:
            (model / name).write_text('{}\n' if name == 'config.json' else 'inert fixture ' + name + '\n')
        profile = work / 'base-profile.json'
        put(profile, {'schema': 'picogk.am.base-profile@1', 'model_directory': 'model-fixture',
                      'repository': 'synthetic/test-only', 'revision': 'a' * 40,
                      'model_files_sha256': {name: q.digest(model / name) for name in q.base_runtime.BASE_NAMES}})
        base = q.base_runtime.verify_base(work, profile)
        adapter = work / 'adapter'
        adapter.mkdir()
        (adapter / 'adapters.safetensors').write_text('inert adapter fixture, never loaded\n')
        put(adapter / 'adapter_config.json', {'test_only': True})
        code = 'public static class Program { public static void Main(string[] args) {} }\n'

        def capture(name, tasks, adapted, selected=None):
            folder = work / name
            task_path = work / ('end-to-end/development.json' if name == 'scan' else
                                'evaluation/final.json' if name == 'final' else 'evaluation/development.json')
            protocol = {'tasks_sha256': q.digest(task_path), 'task_ids': [task['id'] for task in tasks],
                        'adapter_sha256': q.digest(adapter / 'adapters.safetensors') if adapted else None,
                        'adapter_config_sha256': q.digest(adapter / 'adapter_config.json') if adapted else None,
                        'base_weights_sha256': base['base_weights_sha256'], **base['binding']}
            if name != 'baseline':
                protocol.update(checker_profile_sha256=checker, checker_policy=q.CHECKER_POLICY)
            if selected is not None:
                protocol['selection_receipt_sha256'] = selected
            put(folder / 'protocol.json', protocol)
            responses = [{'id': task['id'], 'response': '```csharp\n' + code + '```', 'finish_reason': 'stop'}
                         for task in tasks]
            put(folder / 'responses.json', responses)
            rows = []
            for task in tasks:
                item = {'id': task['id'], 'status': 'passed', 'native_exit_code': 0,
                        'checks': {'synthetic_evidence': True}, 'source_sha256': q.core.hashlib.sha256(code.encode()).hexdigest(),
                        'checker_profile_sha256': checker, 'checker_policy': q.CHECKER_POLICY}
                rows.append(item)
                put(folder / task['id'] / 'result.json', item)
                (folder / task['id'] / 'Program.cs').write_text(code)
            score = {'schema': q.SCORE_SCHEMA, 'checker_policy': q.CHECKER_POLICY,
                     'checker_profile_sha256': checker, 'reference_only': False, 'tasks': rows,
                     'task_sha256': q.digest(task_path), 'split': 'final' if name == 'final' else 'development',
                     'freeze_sha256': q.digest(work / 'end-to-end/freeze.json')}
            put(folder / 'report.json', score)
            return folder

        baseline = capture('baseline', dev, False)
        candidate = capture('candidate', dev, True)
        scan = capture('scan', scans, True)
        selected_path = work / 'selected.json'
        args = SimpleNamespace(baseline_development=baseline / 'report.json',
            candidate_development=candidate / 'report.json', end_to_end=scan / 'report.json',
            baseline_responses=baseline / 'responses.json', candidate_responses=candidate / 'responses.json',
            scan_responses=scan / 'responses.json', adapter=adapter, base_profile=profile, output=selected_path)
        selected = q.select(args)
        good('complete_selection_with_nine_real_fixture_hashes', selected['schema'] == q.SELECTION_SCHEMA
             and selected['checker_profile_sha256'] == checker and q.complete_checks(selected['checks'])
             and len(selected['model_files_sha256']) == 9)
        current = {key: selected[key] for key in ('adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256',
                   'development_task_sha256', 'scan_task_sha256', 'scan_freeze_sha256')}
        q.validate_selection(selected, current, checker)
        good('infer_v2_six_key_selection_api', True)
        for name, bad in (
            ('legacy_selection_rejected', dict(selected, schema='picogk.am.development-selection@1')),
            ('missing_selected_profile', {key: value for key, value in selected.items() if key != 'checker_profile_sha256'}),
            ('selected_source_changed', dict(selected, qualification_source_sha256='d' * 64)),
            ('selected_v1_gate_changed', dict(selected, development_gate_source_sha256='d' * 64)),
            ('selected_incomplete_checks', dict(selected, checks={'required_safety_passed': True})),
            ('selected_extra_checks', dict(selected, checks=dict(selected['checks'], extra=True))),
            ('selected_nonboolean_checks', dict(selected, checks=dict.fromkeys(q.QUALIFICATION_CHECK_KEYS, 1))),
        ):
            rejects(name, lambda bad=bad: q.validate_selection(bad, current, checker))
        rejects('selected_model_changed', lambda: q.validate_selection(selected, dict(current, adapter_sha256='d' * 64), checker))
        rejects('selection_requires_complete_current_identity', lambda: q.validate_selection(selected, {}, checker))
        before = (candidate / 'dev-0/Program.cs').read_text()
        (candidate / 'dev-0/Program.cs').write_text(before + '// changed\n')
        args.output = work / 'must-not-exist.json'
        rejects('raw_response_compiled_source_mismatch', lambda: q.select(args))
        good('failed_selection_writes_no_receipt', not args.output.exists())
        (candidate / 'dev-0/Program.cs').write_text(before)
        candidate_protocol = q.read(candidate / 'protocol.json')
        put(candidate / 'protocol.json', {key: value for key, value in candidate_protocol.items()
                                         if key not in ('checker_profile_sha256', 'checker_policy')})
        rejects('new_candidate_protocol_profile_required', lambda: q.select(args))
        put(candidate / 'protocol.json', candidate_protocol)
        scan_protocol = q.read(scan / 'protocol.json')
        put(scan / 'protocol.json', dict(scan_protocol, checker_profile_sha256='d' * 64))
        rejects('scan_protocol_profile_mismatch', lambda: q.select(args))
        put(scan / 'protocol.json', scan_protocol)

        final_folder = capture('final', final_tasks, True, q.digest(selected_path))
        final_args = SimpleNamespace(selection_receipt=selected_path, final_score=final_folder / 'report.json',
            final_responses=final_folder / 'responses.json', adapter=adapter, base_profile=profile,
            output=work / 'qualified.json')
        real_digest, real_read = q.digest, q.read

        def no_final_digest(path):
            assert path != work / 'evaluation/final.json', 'Final bytes hashed before early metadata rejection.'
            return real_digest(path)

        def no_final_read(path):
            assert path != work / 'evaluation/final.json', 'Final body read before early metadata rejection.'
            return real_read(path)

        def early_reject(name, mutation=None, verifier_error=False):
            original_score, original_selection = real_read(final_args.final_score), real_read(selected_path)
            if mutation is not None:
                mutation()
            try:
                with patch.object(q, 'digest', side_effect=no_final_digest), patch.object(q, 'read', side_effect=no_final_read):
                    if verifier_error:
                        with patch.object(q, 'verify_checker_profile', side_effect=ValueError('Tampered checker fixture')):
                            rejects(name, lambda: final.qualify(final_args))
                    else:
                        rejects(name, lambda: final.qualify(final_args))
            finally:
                put(final_args.final_score, original_score)
                put(selected_path, original_selection)

        early_reject('tampered_checker_rejects_before_final_access', verifier_error=True)
        early_reject('mixed_final_score_before_final_access', lambda: put(final_args.final_score,
            dict(real_read(final_args.final_score), checker_profile_sha256='d' * 64)))
        early_reject('mixed_final_row_before_final_access', lambda: put(final_args.final_score,
            dict(real_read(final_args.final_score), tasks=[dict(item, checker_profile_sha256='d' * 64)
                                                         for item in real_read(final_args.final_score)['tasks']])))
        early_reject('mixed_selected_profile_before_final_access', lambda: put(selected_path,
            dict(selected, checker_profile_sha256='d' * 64)))
        early_reject('incomplete_selection_before_final_access', lambda: put(selected_path,
            dict(selected, checks={'required_safety_passed': True})))
        final_args.final_score = work / 'evaluation/final.json'
        with patch.object(q, 'read') as mocked:
            rejects('metadata_alias_rejected_without_read', lambda: final.qualify(final_args))
            good('metadata_alias_did_not_read', not mocked.called)
        final_args.final_score = final_folder / 'report.json'
        alias = work / 'hardlink-metadata.json'
        alias.hardlink_to(work / 'evaluation/final.json')
        good('hardlink_reserved_identity_detected', q.is_reserved_input(alias))
        final_args.selection_receipt = alias
        with patch.object(q, 'read') as mocked:
            rejects('hardlink_metadata_rejected_before_read', lambda: final.qualify(final_args))
            good('hardlink_metadata_did_not_read', not mocked.called)
        final_args.selection_receipt = selected_path
        args.baseline_development = alias
        with patch.object(q, 'read') as mocked:
            rejects('hardlink_development_metadata_before_read', lambda: q.select(args))
            good('hardlink_development_metadata_did_not_read', not mocked.called)
        args.baseline_development = baseline / 'report.json'
        args.base_profile = alias
        final_args.base_profile = alias
        with patch.object(q.base_runtime, 'verify_base') as mocked:
            rejects('hardlink_development_base_profile_before_read', lambda: q.select(args))
            rejects('hardlink_final_base_profile_before_read', lambda: final.qualify(final_args))
            good('hardlink_base_profile_not_verified_or_read', not mocked.called)
        args.base_profile = profile
        final_args.base_profile = profile
        reference = work / 'evaluation/references/final-synthetic.cs'
        reference.parent.mkdir()
        reference.write_text('synthetic reference, never executed\n')
        reference_alias = work / 'reference-hardlink.txt'
        reference_alias.hardlink_to(reference)
        good('hardlink_reference_identity_detected', q.is_reserved_input(reference_alias))
        qualified = final.qualify(final_args)
        good('qualified_receipt_profile_and_exact_13_checks', qualified['schema'] == final.FINAL_SCHEMA
             and qualified['checker_profile_sha256'] == checker
             and final.complete_final_checks(qualified['checks']))
        good('qualified_receipt_binds_both_gate_versions',
             qualified['development_qualification_source_sha256'] == q.digest(work / 'qualification_v2.py')
             and qualified['qualification_source_sha256'] == q.digest(work / 'final_qualification_v2.py')
             and qualified['development_gate_source_sha256'] == q.digest(work / 'qualification.py')
             and qualified['final_gate_source_sha256'] == q.digest(work / 'final_qualification.py'))
        good('all_passed_final_individual_sources_bound', len(qualified['passed_source_sha256']) == 12
             and len(qualified['individual_result_sha256']) == 12)
        rejects('receipt_not_overwritten', lambda: final.qualify(final_args))
        final_args.output = work / 'must-not-qualify.json'
        final_protocol = q.read(final_folder / 'protocol.json')
        put(final_folder / 'protocol.json', {key: value for key, value in final_protocol.items()
                                           if key not in ('checker_profile_sha256', 'checker_policy')})
        rejects('final_protocol_profile_required', lambda: final.qualify(final_args))
        put(final_folder / 'protocol.json', dict(final_protocol, selection_receipt_sha256='d' * 64))
        rejects('final_protocol_selected_receipt_required', lambda: final.qualify(final_args))
        put(final_folder / 'protocol.json', final_protocol)
        good('failed_final_writes_no_receipt', not final_args.output.exists())

        # Direct v1 gate calls prove unchanged numerical/critical/retention/EOS rules.
        old = real_read(baseline / 'report.json')
        new = real_read(candidate / 'report.json')
        scan_report = real_read(scan / 'report.json')
        answers, scan_answers = real_read(candidate / 'responses.json'), real_read(scan / 'responses.json')
        expected, scan_ids = {task['id'] for task in dev}, {task['id'] for task in scans}
        critical = {task['id'] for task in dev if task['family'] in q.CRITICAL}
        old['tasks'][-1]['status'] = 'failed'
        eleven = deepcopy(new)
        eleven['tasks'][-1]['status'] = 'failed'
        good('unchanged_eleven_passes', q.gate(old, eleven, scan_report, answers, scan_answers,
                                              expected, scan_ids, critical)['passed'])
        ten = deepcopy(eleven)
        ten['tasks'][-2]['status'] = 'failed'
        good('unchanged_ten_rejected', not q.gate(old, ten, scan_report, answers, scan_answers,
                                                expected, scan_ids, critical)['passed'])
        lost = deepcopy(new)
        lost['tasks'][-2]['status'] = 'failed'
        good('unchanged_baseline_retention', not q.gate(old, lost, scan_report, answers, scan_answers,
            expected, scan_ids, critical)['checks']['retains_all_baseline_passes'])
        unsafe = deepcopy(new)
        unsafe['tasks'][0]['status'] = 'failed'
        good('unchanged_all_critical', not q.gate(old, unsafe, scan_report, answers, scan_answers,
            expected, scan_ids, critical)['checks']['required_safety_passed'])
        truncated = deepcopy(answers)
        truncated[0]['finish_reason'] = 'length'
        good('unchanged_eos_gate', not q.gate(old, new, scan_report, truncated, scan_answers,
            expected, scan_ids, critical)['passed'])
        bad_scan = deepcopy(scan_report)
        bad_scan['tasks'][0]['status'] = 'failed'
        good('unchanged_four_scan_gate', not q.gate(old, new, bad_scan, answers, scan_answers,
            expected, scan_ids, critical)['passed'])
    print(json.dumps({'status': 'self_check_passed', 'checks': len(checks), 'check_names': checks,
                      'real_final_tasks_read': False, 'model_or_native_execution': False}))
    return checks


if __name__ == '__main__':
    run_checks()
