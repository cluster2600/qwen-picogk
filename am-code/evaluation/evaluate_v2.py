"""Score development responses with prospective v2 lexical policy and frozen v1 geometry."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('am_policy_v2', ROOT / 'policy_v2.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
spec = importlib.util.spec_from_file_location('am_native_geometry_v1', ROOT / 'evaluate.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
spec = importlib.util.spec_from_file_location('am_score_qualification_v2', ROOT.parent / 'qualification_v2.py')
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def final_context(args, checker_hash):
    """Validate current selection/model/protocol metadata without reading final tasks."""
    if (args.references or args.selection_receipt is None or args.adapter is None
            or args.base_profile is None or args.responses is None):
        raise ValueError('final scoring requires selected model responses, adapter and base profile')
    qualification.reject_reserved_inputs((args.selection_receipt, args.adapter, args.base_profile,
                                          args.responses, args.run_dir))
    selection = qualification.read(args.selection_receipt)
    qualification.require_selection_profile(selection, checker_hash)
    base = qualification.base_runtime.verify_base(ROOT.parent, args.base_profile)
    adapter = args.adapter / 'adapters.safetensors' if args.adapter.is_dir() else args.adapter
    qualification.reject_reserved_inputs((adapter, adapter.parent / 'adapter_config.json'))
    current = dict(adapter_sha256=qualification.digest(adapter),
        adapter_config_sha256=qualification.digest(adapter.parent / 'adapter_config.json'),
        base_weights_sha256=base['base_weights_sha256'],
        development_task_sha256=qualification.digest(ROOT / 'development.json'),
        scan_task_sha256=qualification.digest(ROOT.parent / 'end-to-end/development.json'),
        scan_freeze_sha256=qualification.digest(ROOT.parent / 'end-to-end/freeze.json'),
        **base['binding'])
    frozen = qualification.read(ROOT / 'freeze.json')
    if frozen['files']['development.json'] != current['development_task_sha256']:
        raise ValueError('frozen development tasks changed')
    qualification.verify_scan_freeze()
    qualification.validate_selection(selection, current, checker_hash)
    qualification.base_runtime.verify_evidence(base, selection)
    protocol = qualification.read(args.responses / 'protocol.json')
    qualification.require_protocol_profiles(checker_hash, protocol, required=True)
    selection_hash = qualification.digest(args.selection_receipt)
    if (protocol.get('selection_receipt_sha256') != selection_hash
            or any(protocol.get(key) != current[key] for key in
                   ('adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256'))):
        raise ValueError('final response model or development selection binding changed')
    qualification.base_runtime.verify_evidence(base, protocol)
    return {'selection_receipt_sha256': selection_hash, 'protocol': protocol}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', action='store_true')
    parser.add_argument('--split', choices=['development', 'final'], default='development')
    parser.add_argument('--responses', type=Path, help='directory of unchanged <task-id>.txt responses')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--selection-receipt', type=Path)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--base-profile', type=Path)
    args = parser.parse_args()
    if not args.references and args.responses is None:
        parser.error('Use references or responses')
    binding = policy.verify_checker_profile()
    profile_hash = binding['checker_profile_sha256']
    metadata = policy.score_metadata(binding)
    native.static_gate = lambda code: policy.static_gate(code, expected_profile_sha256=profile_hash)

    # Selection validation is mandatory before even hashing the reserved final task.
    context = final_context(args, profile_hash) if args.split == 'final' else None
    frozen = json.loads((ROOT / 'freeze.json').read_text())
    task_path = ROOT / (args.split + '.json')
    task_hash = native.digest(task_path)
    if task_hash != frozen['files'][task_path.name]:
        raise ValueError('frozen tasks changed')
    if context is not None and context['protocol'].get('tasks_sha256') != task_hash:
        raise ValueError('final protocol task binding changed')
    tasks = json.loads(task_path.read_text())['tasks']
    if context is not None:
        expected = {task['id'] for task in tasks}
        if (set(context['protocol'].get('task_ids', [])) != expected
                or len(context['protocol'].get('task_ids', [])) != len(expected)):
            raise ValueError('final protocol task IDs changed')
    args.run_dir = args.run_dir.resolve()
    if args.responses is not None:
        args.responses = args.responses.resolve()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for task in tasks:
        folder = args.run_dir / task['id']
        policy.verify_reference_artifacts(task, 'evaluation', allow_final=context is not None)
        if args.references:
            code = (ROOT / task['reference']).read_text()
            reference = None
        else:
            gold = ROOT / 'reference-validation' / task['id']
            gold_result = json.loads((gold / 'result.json').read_text())
            if gold_result['status'] != 'passed':
                raise ValueError('authored reference must validate before candidate execution')
            reference = (json.loads((gold / 'inspection/native.json').read_text()),
                         (gold / 'inspection/occupancy.bin').read_bytes(),
                         gold_result['details']['mesh']) if task['kind'] != 'refusal' else None
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
        result = native.evaluate(task, code, folder, reference)
        result.pop('_reference', None)
        result.update(metadata)
        if result['status'] == 'passed':
            if (folder / 'Program.cs').read_bytes() != code.encode('utf-8'):
                raise ValueError('compiled source differs from extracted response')
            if result['source_sha256'] != hashlib.sha256(code.encode('utf-8')).hexdigest():
                raise ValueError('passed source hash differs from compiled source')
        (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
        print(task['id'], result['status'], flush=True)
    if policy.verify_checker_profile()['checker_profile_sha256'] != profile_hash:
        raise ValueError('checker profile changed during evaluation')
    report = dict(schema=policy.SCORE_SCHEMA, split=args.split, reference_only=args.references,
                  passed=sum(row['status'] == 'passed' for row in results), total=len(results),
                  tasks=results, physical_qualification=False, task_sha256=task_hash,
                  **metadata)
    if context is not None:
        report['selection_receipt_sha256'] = context['selection_receipt_sha256']
    (args.run_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'tasks'}, indent=2))
    return 0 if report['passed'] == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
