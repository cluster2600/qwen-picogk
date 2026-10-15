#!/usr/bin/env python3
"""Bind the unchanged development gates to one verified v2 checker profile."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


core = _module('am_qualification_v2_core', ROOT / 'qualification.py')
base_runtime = core.base_runtime
CRITICAL = core.CRITICAL
QUALIFICATION_CHECK_KEYS = core.QUALIFICATION_CHECK_KEYS
complete_checks = core.complete_checks
digest = core.digest
read = core.read
gate = core.gate
bind_responses = core.bind_responses
common_base_hash = core.common_base_hash
verify_scan_freeze = core.verify_scan_freeze
CHECKER_POLICY = 'roslyn-static-allowlist@2'
SCORE_SCHEMA = 'picogk.am.native-score@2'
SELECTION_SCHEMA = 'picogk.am.development-selection@2'


def verify_checker_profile(path=None):
    """Use the shared verifier, including its separately pinned SHA sidecar."""
    policy = _module('am_qualification_v2_policy', ROOT / 'evaluation/policy_v2.py')
    result = policy.verify_checker_profile(path)
    if (not isinstance(result, dict) or not _sha(result.get('checker_profile_sha256'))
            or not isinstance(result.get('profile'), dict)
            or result['profile'].get('schema') != 'picogk.am.checker-profile@2'
            or result['profile'].get('policy') != CHECKER_POLICY):
        raise ValueError('A complete verified v2 checker profile is required.')
    return result


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def require_score_profiles(checker_hash, *reports):
    """Reject legacy/mixed policies in every aggregate and individual task row."""
    if not _sha(checker_hash) or not reports:
        raise ValueError('A nonempty verified checker identity is required.')
    for report in reports:
        if (not isinstance(report, dict) or report.get('schema') != SCORE_SCHEMA
                or report.get('checker_policy') != CHECKER_POLICY
                or report.get('checker_profile_sha256') != checker_hash
                or not isinstance(report.get('tasks'), list) or not report['tasks']):
            raise ValueError('Every scorer report must use the same verified v2 checker.')
        for row in report['tasks']:
            if (not isinstance(row, dict) or row.get('checker_policy') != CHECKER_POLICY
                    or row.get('checker_profile_sha256') != checker_hash):
                raise ValueError('Individual task evidence uses a missing or different checker.')


def require_protocol_profiles(checker_hash, *protocols, required=False):
    """Legacy captures may be regraded; declared checker metadata cannot conflict."""
    if not _sha(checker_hash):
        raise ValueError('Invalid current checker identity.')
    for protocol in protocols:
        if not isinstance(protocol, dict):
            raise ValueError('Inference protocol must be an object.')
        if ((required or 'checker_profile_sha256' in protocol or 'checker_policy' in protocol)
                and protocol.get('checker_profile_sha256') != checker_hash):
            raise ValueError('Inference protocol checker identity mismatch.')
        if 'checker_policy' in protocol and protocol['checker_policy'] != CHECKER_POLICY:
            raise ValueError('Inference protocol checker policy mismatch.')


def require_selection_profile(selection, checker_hash):
    if (not _sha(checker_hash) or not isinstance(selection, dict)
            or selection.get('schema') != SELECTION_SCHEMA
            or selection.get('checker_policy') != CHECKER_POLICY
            or selection.get('checker_profile_sha256') != checker_hash):
        raise ValueError('A selected receipt under the current v2 checker is required.')


def validate_selection(selection, current, checker_hash):
    """Validate selection/model/source metadata before any reserved final access."""
    require_selection_profile(selection, checker_hash)
    required = {'adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256',
                'development_task_sha256', 'scan_task_sha256', 'scan_freeze_sha256'}
    if (not isinstance(current, dict) or not required <= set(current)
            or any(not _sha(current[key]) for key in required)
            or selection.get('status') != 'selected_for_final_evaluation'
            or type(selection.get('development_passes')) is not int
            or not 11 <= selection['development_passes'] <= 12
            or type(selection.get('scan_passes')) is not int or selection['scan_passes'] != 4
            or selection.get('required_safety_passed') is not True
            or not complete_checks(selection.get('checks'))
            or selection.get('qualification') != 'software and geometry only'
            or selection.get('manufacturing_authorized') is not False):
        raise ValueError('Complete current development selection is required before final task access.')
    sources = {'checker_profile_sha256': checker_hash,
               'qualification_source_sha256': digest(ROOT / 'qualification_v2.py'),
               'development_gate_source_sha256': digest(ROOT / 'qualification.py')}
    if any(key in current and current[key] != value for key, value in sources.items()):
        raise ValueError('Current checker or qualification source identity conflicts.')
    if any(selection.get(key) != value for key, value in {**current, **sources}.items()):
        raise ValueError('Selected model, task, checker or qualification source changed.')


def is_reserved_input(path):
    """Detect path, symlink and hardlink aliases using filesystem metadata only."""
    path = Path(path)
    if base_runtime.reserved(ROOT, path):
        return True
    if not path.exists():
        return False
    evaluation = ROOT / 'evaluation'
    reserved = [evaluation / 'final.json', *(evaluation / 'references').glob('final-*')]
    return any(candidate.exists() and path.samefile(candidate) for candidate in reserved)


def reject_reserved_inputs(paths):
    if any(is_reserved_input(path) for path in paths):
        raise ValueError('Metadata and output paths cannot alias reserved final inputs.')


def select(args):
    adapter = args.adapter / 'adapters.safetensors' if args.adapter.is_dir() else args.adapter
    reject_reserved_inputs((args.baseline_development, args.candidate_development, args.end_to_end,
                            args.baseline_responses, args.candidate_responses,
                            args.scan_responses, adapter, adapter.parent / 'adapter_config.json', args.output,
                            *([args.base_profile] if args.base_profile is not None else [])))
    checker_hash = verify_checker_profile()['checker_profile_sha256']
    baseline, candidate, scan = read(args.baseline_development), read(args.candidate_development), read(args.end_to_end)
    require_score_profiles(checker_hash, baseline, candidate, scan)
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
    if any(report.get('reference_only') is not False for report in (baseline, candidate, scan)):
        raise ValueError('Only scored model responses may qualify, not references.')
    if (baseline.get('task_sha256') != task_hash or candidate.get('task_sha256') != task_hash
            or scan.get('freeze_sha256') != scan_freeze_hash):
        raise ValueError('Scorer report task/freeze binding mismatch.')
    adapter_hash, config_hash = digest(adapter), digest(adapter.parent / 'adapter_config.json')
    old_binding, old_protocol = bind_responses(args.baseline_responses, task_hash, None, expected,
                                                baseline, args.baseline_development)
    new_binding, new_protocol = bind_responses(args.candidate_responses, task_hash, adapter_hash,
                                                expected, candidate, args.candidate_development, config_hash)
    scan_binding, scan_protocol = bind_responses(args.scan_responses, scan_hash, adapter_hash,
                                                  scan_ids, scan, args.end_to_end, config_hash)
    require_protocol_profiles(checker_hash, old_protocol)
    require_protocol_profiles(checker_hash, new_protocol, scan_protocol, required=True)
    base_hash = common_base_hash((old_protocol, new_protocol, scan_protocol), base['base_weights_sha256'])
    base_runtime.verify_evidence(base, old_protocol, new_protocol, scan_protocol)
    result = gate(baseline, candidate, scan, read(args.candidate_responses), read(args.scan_responses),
                  expected, scan_ids, critical)
    if not result['passed']:
        return {'status': 'rejected', 'checker_profile_sha256': checker_hash, **result}
    receipt = {'schema': SELECTION_SCHEMA, 'status': 'selected_for_final_evaluation',
               'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'checker_profile_sha256': checker_hash, 'checker_policy': CHECKER_POLICY,
               'qualification_source_sha256': digest(ROOT / 'qualification_v2.py'),
               'development_gate_source_sha256': digest(ROOT / 'qualification.py'),
               'adapter_sha256': adapter_hash, 'adapter_config_sha256': config_hash,
               'base_weights_sha256': base_hash, **base['binding'],
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
               'qualification': 'software and geometry only', 'manufacturing_authorized': False}
    if not complete_checks(receipt['checks']):
        raise ValueError('Selection receipt lacks the exact qualification check map.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--base-profile', type=Path)
    for name in ('baseline-development', 'candidate-development', 'end-to-end',
                 'baseline-responses', 'candidate-responses', 'scan-responses', 'adapter', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.self_check:
        _module('am_v2_focused_tests', ROOT / 'test_qualification_v2.py').run_checks()
        return 0
    names = ('baseline_development', 'candidate_development', 'end_to_end', 'baseline_responses',
             'candidate_responses', 'scan_responses', 'adapter', 'output')
    if any(getattr(args, name) is None for name in names):
        parser.error('All report, response, adapter and new output paths are required.')
    try:
        result = select(args)
        print(json.dumps(result, indent=2))
        return 0 if result.get('status') == 'selected_for_final_evaluation' else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
