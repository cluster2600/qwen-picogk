#!/usr/bin/env python3
"""Apply unchanged final gates only after one verified v2 selection/checker binding."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import importlib.util


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


qualification = _module('am_final_v2_development', ROOT / 'qualification_v2.py')
core = _module('am_final_v2_core', ROOT / 'final_qualification.py')
FINAL_CHECK_KEYS = core.FINAL_CHECK_KEYS
complete_final_checks = core.complete_final_checks
final_gates = core.final_gates
validate_inference_selection = core.validate_inference_selection
validate_selection = qualification.validate_selection
FINAL_SCHEMA = 'picogk.am.final-qualification@2'


def qualify(args):
    adapter, config = args.adapter / 'adapters.safetensors', args.adapter / 'adapter_config.json'
    qualification.reject_reserved_inputs((args.selection_receipt, args.final_score,
                                         args.final_responses, adapter, config, args.output,
                                         *([args.base_profile] if args.base_profile is not None else [])))
    checker_hash = qualification.verify_checker_profile()['checker_profile_sha256']
    selection = qualification.read(args.selection_receipt)
    report = qualification.read(args.final_score)
    # Validate all policy metadata before even hashing the sealed final task file.
    qualification.require_selection_profile(selection, checker_hash)
    qualification.require_score_profiles(checker_hash, report)
    selection_hash = qualification.digest(args.selection_receipt)
    base = qualification.base_runtime.verify_base(ROOT, args.base_profile)
    qualification.base_runtime.verify_evidence(base, selection)
    current = {'adapter_sha256': qualification.digest(adapter),
               'adapter_config_sha256': qualification.digest(config),
               'base_weights_sha256': base['base_weights_sha256'], **base['binding'],
               'development_task_sha256': qualification.digest(ROOT / 'evaluation/development.json'),
               'scan_task_sha256': qualification.digest(ROOT / 'end-to-end/development.json'),
               'scan_freeze_sha256': qualification.digest(ROOT / 'end-to-end/freeze.json')}
    frozen = qualification.read(ROOT / 'evaluation/freeze.json')
    if frozen['files']['development.json'] != current['development_task_sha256']:
        raise ValueError('Frozen development tasks changed.')
    qualification.verify_scan_freeze()
    validate_selection(selection, current, checker_hash)
    # These are the first accesses to reserved task bytes, after all early guards.
    final_path = ROOT / 'evaluation/final.json'
    task_hash = qualification.digest(final_path)
    if task_hash != frozen['files']['final.json']:
        raise ValueError('Frozen final tasks changed.')
    tasks = qualification.read(final_path)['tasks']
    responses = qualification.read(args.final_responses)
    if (report.get('split') != 'final' or report.get('reference_only') is not False
            or report.get('task_sha256') != task_hash):
        raise ValueError('Final scorer must describe model responses on the exact frozen final tasks.')
    expected, passed, gates = final_gates(report, responses, tasks)
    binding, protocol = qualification.bind_responses(
        args.final_responses, task_hash, current['adapter_sha256'], expected,
        report, args.final_score, current['adapter_config_sha256'])
    if not passed <= set(binding['task_result_sha256']):
        raise ValueError('Every passing final task requires its individual bound result record.')
    validate_inference_selection(protocol, selection_hash)
    qualification.require_protocol_profiles(checker_hash, protocol, required=True)
    qualification.common_base_hash((protocol,), current['base_weights_sha256'])
    qualification.base_runtime.verify_evidence(base, protocol)
    checks = dict.fromkeys(FINAL_CHECK_KEYS, True)
    checks.update(gates)
    if not complete_final_checks(checks):
        return {'status': 'rejected', 'checker_profile_sha256': checker_hash,
                'final_passes': len(passed), 'total': 12, 'checks': checks}
    receipt = {'schema': FINAL_SCHEMA, 'status': 'qualified',
               'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'checker_profile_sha256': checker_hash,
               'checker_policy': qualification.CHECKER_POLICY,
               **{key: current[key] for key in ('base_weights_sha256', 'adapter_sha256', 'adapter_config_sha256')},
               **base['binding'], 'development_selection_sha256': selection_hash,
               'final_task_sha256': task_hash, 'final_passes': len(passed), 'total': 12,
               'checks': checks, 'score_sha256': qualification.digest(args.final_score),
               'protocol_sha256': binding['protocol_sha256'],
               'responses_sha256': binding['responses_sha256'],
               'passed_source_sha256': {row['id']: row['source_sha256']
                                        for row in report['tasks'] if row['id'] in passed},
               'individual_result_sha256': binding['task_result_sha256'],
               'qualification_source_sha256': qualification.digest(ROOT / 'final_qualification_v2.py'),
               'development_qualification_source_sha256': qualification.digest(ROOT / 'qualification_v2.py'),
               'final_gate_source_sha256': qualification.digest(ROOT / 'final_qualification.py'),
               'development_gate_source_sha256': qualification.digest(ROOT / 'qualification.py'),
               'qualification': 'software and geometry only', 'manufacturing_authorized': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--base-profile', type=Path)
    for name in ('selection-receipt', 'final-score', 'final-responses', 'adapter', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.self_check:
        _module('am_v2_final_focused_tests', ROOT / 'test_qualification_v2.py').run_checks()
        return 0
    if any(getattr(args, name) is None for name in
           ('selection_receipt', 'final_score', 'final_responses', 'adapter', 'output')):
        parser.error('Selection, final score/responses, adapter directory and new output paths are required.')
    try:
        receipt = qualify(args)
        print(json.dumps(receipt, indent=2))
        return 0 if receipt.get('status') == 'qualified' else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
