#!/usr/bin/env python3
"""Verify AM public source/data identities without MLX or generated-code execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from prepare_release_assets import is_text_member

ROOT = Path(__file__).resolve().parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def check_completed32b(root, release):
    """Check exported evidence identities without trusting a relocated checker profile."""
    read = lambda name: json.loads((root/name).read_text())
    ledger = read('evidence/source-export-bindings.json')['files']
    bindings = {row['public_path']: row for row in ledger}
    assert len(bindings) == len(ledger)
    for name, row in bindings.items():
        assert digest(root/name) == row['public_sha256'], name
    original = lambda name: bindings[name]['source_sha256']
    capture = read('evidence/baseline32b/capture/responses.json')
    capture_protocol = read('evidence/baseline32b/capture/protocol.json')
    capture_receipt = read('evidence/baseline32b/capture/receipt.json')
    old, new = read('evidence/baseline32b/v1-report.json'), read('evidence/baseline32b/v2-report.json')
    policy = read('evidence/evaluation-policy-v2/checker-profile-v2.json')
    anchor = (root/'evidence/evaluation-policy-v2/checker-profile-v2.sha256').read_text().strip()
    peer = read('diagnostics/evaluation-policy-v2/frozen-profile-independent-review.json')
    assert len(capture) == len(old['tasks']) == len(new['tasks']) == 12
    assert all(row['finish_reason'] == 'stop' and row['response'].strip() for row in capture)
    assert capture_receipt['status'] == 'completed' and capture_receipt['all_stopped'] is True
    assert capture_receipt['responses_sha256'] == original('evidence/baseline32b/capture/responses.json')
    assert capture_receipt['protocol_sha256'] == original('evidence/baseline32b/capture/protocol.json')
    assert capture_protocol['adapter_sha256'] is None and capture_protocol['adapter_config_sha256'] is None
    assert old['passed'] == new['passed'] == 5 and old['total'] == new['total'] == 12
    assert {row['id'] for row in old['tasks'] if row['status'] == 'passed'} == {
        row['id'] for row in new['tasks'] if row['status'] == 'passed'}
    assert new['schema'] == 'picogk.am.native-score@2' and new['checker_profile_sha256'] == anchor
    assert all(row['checker_profile_sha256'] == anchor and row['checker_policy'] == new['checker_policy']
               for row in new['tasks'])
    answers = {row['id']: row['response'] for row in capture}
    source_rows = [row for row in new['tasks'] if row.get('source_sha256')]
    assert len(source_rows) == 11
    for row in source_rows:
        fences = re.findall(r'```(?:csharp|cs|C#)\s*\n(.*?)```', answers[row['id']], re.S)
        assert len(fences) == 1
        assert hashlib.sha256((fences[0].strip()+'\n').encode()).hexdigest() == row['source_sha256']
    cone = next(row for row in new['tasks'] if row['id'] == 'development-cone-roof')
    assert cone['status'] == 'failed' and cone['checks']['static_allowlist'] is True
    assert 'C# compilation failed' in cone['error']
    assert peer['status'] == 'passed' and len(peer['checks']) == 17 and all(peer['checks'].values())
    assert peer['capture_responses_sha256'] == original('evidence/baseline32b/capture/responses.json')
    assert peer['historical_v1_report_sha256'] == original('evidence/baseline32b/v1-report.json')
    assert peer['v2_report_sha256'] == original('evidence/baseline32b/v2-report.json')
    assert peer['checker_profile_sha256'] == anchor == original('evidence/evaluation-policy-v2/checker-profile-v2.json')
    assert len(policy['files']) == 40 and len(policy['external_files']) == 14
    assert digest(root/'evidence/evaluation-policy-v2/checker-profile-v2.json') != anchor
    assert not (root/'checker-profile-v2.json').exists() and not (root/'checker-profile-v2.sha256').exists()
    for name in ('qualification_v2.py', 'final_qualification_v2.py', 'infer_v2.py',
                 'evaluation/policy_v2.py', 'evaluation/evaluate_v2.py', 'end-to-end/evaluate_v2.py',
                 'evaluation/PolicyLexer/Program.cs', 'evaluation/PolicyLexer/PolicyLexer.csproj',
                 'sealed-reference-hashes-v2.json'):
        assert policy['files'][name] == original(name), name
    sealed = read('sealed-reference-hashes-v2.json')
    assert sealed['schema'] == 'picogk.am.sealed-reference-hashes@2' and len(sealed['files']) == 140
    assert sealed['preparation'] == 'blind_streaming_sha256_no_semantic_final_access'
    assert all(re.fullmatch('[0-9a-f]{64}', value) for value in sealed['files'].values())
    lexical = read('diagnostics/evaluation-policy-v2/lexical-results-v2.json')
    assert lexical['status'] == 'passed' and len(lexical['cases']) == 18
    assert all(row['passed'] is True for row in lexical['cases'])
    smoke = read('evidence/memory-smoke32b/cpu-audit.json')
    receipt = read('evidence/memory-smoke32b/training-receipt.json')
    assert len(smoke['checks']) == 97 and all(smoke['checks'].values())
    assert smoke['qualification_eligible'] is False and smoke['full_training_may_resume_smoke_adapter'] is False
    assert smoke['full_course_memory_or_stability_proven'] is False
    assert smoke['trainable_arrays'] == 224 and smoke['trainable_parameters'] == 16777216
    assert smoke['maximum_actual_tokens'] == receipt['maximum_tokens'] == 5416
    assert smoke['training_steps'] == receipt['training_steps'] == smoke['training_rows'] == 1
    assert receipt['adapter_sha256'] == smoke['adapter_sha256'] == release['memory_smoke32b']['adapter_sha256']
    assert receipt['peak_memory_bytes'] == 31790475366 < 36*1024**3
    one = (root/'diagnostics/model32b-preparation/memory-smoke-longest/train.jsonl').read_bytes()
    assert one == (root/'data/train-chat.jsonl').read_bytes().splitlines(keepends=True)[134]
    registration, runtime = read('evidence/course-009-protocol.json'), read('evidence/course009-runtime-protocol.json')
    assert registration['checker_profile_sha256'] == anchor and registration['parent_adapter'] is None
    assert registration['smoke_adapter_resumed'] is False and registration['fresh_optimizer'] is True
    assert registration['iterations'] == registration['training_rows'] == runtime['supplemental_rows'] == 310
    assert registration['learning_rate'] == runtime['config']['learning_rate'] == 5e-7
    assert runtime['config']['resume_adapter_file'] is None and runtime['config']['iters'] == 310
    assert runtime['corpus_sha256'] == registration['corpus_sha256'] == digest(root/'data/mixed-14b-001/train.jsonl')
    launch = read('evidence/course009-launch-independent-review.json')
    assert launch['status'] == 'passed' and len(launch['checks']) == 32 and all(launch['checks'].values())
    assert launch['prospective_protocol_sha256'] == original('evidence/course-009-protocol.json')
    assert launch['runtime_protocol_sha256'] == original('evidence/course009-runtime-protocol.json')
    assert launch['checker_profile_sha256'] == anchor and launch['training_rows'] == 310
    assert release['current_training']['active_weights_logs_captures_or_scores_included'] is False
    assert release['checker_v2']['profile_reanchored'] is False


def check(root=ROOT, assets=None, native_runtime=False):
    release = json.loads((root/'release.json').read_text())
    assert release['schema'] == 'picogk.am.public-release@1'
    assert release['qualified_adapter'] is False and release['manufacturing_authorized'] is False
    for relative, expected in release['files_sha256'].items():
        path = (root/relative).resolve()
        assert path.is_relative_to(root.resolve()) and digest(path) == expected, relative
        assert relative != 'evaluation/final.json' and not relative.startswith('evaluation/references/final-')
    raw = [json.loads(line) for line in (root/'data/train.jsonl').read_text().splitlines()]
    chat = [json.loads(line) for line in (root/'data/train-chat.jsonl').read_text().splitlines()]
    assert len(raw) == len(chat) == 150
    for original, parsed in zip(raw, chat):
        user, assistant = parsed['messages']
        assert [user['role'], assistant['role']] == ['user', 'assistant']
        assert original == {'text': '<|im_start|>user\n'+user['content']+'\n<|im_end|>\n<|im_start|>assistant\n'+assistant['content']+'\n<|im_end|>'}
    compact = [json.loads(line) for line in (root/'data/corrective-001/train.jsonl').read_text().splitlines()]
    expanded = [json.loads(line) for line in (root/'data/corrective-002/train.jsonl').read_text().splitlines()]
    cases = json.loads((root/'data/corrective-001/cases.json').read_text())['cases']
    assert len(compact) == len(cases) == 64 and len(expanded) == 192
    for index, (row, case) in enumerate(zip(compact, cases)):
        answer = row['messages'][1]['content']
        assert answer.count('```') == 2 and answer.count('```csharp\n') == 1
        source = answer.split('```csharp\n', 1)[1].rsplit('```', 1)[0]
        assert source == (root/'data/corrective-001'/case['source']).read_text()
        assert digest(root/'data/corrective-001'/case['source']) == case['source_sha256']
        assert digest(root/'data/corrective-001'/case['input']) == case['input_sha256']
        assert expanded[3*index]['messages'][0] == row['messages'][0]
        for style in range(3):
            assert expanded[3*index+style]['messages'][1] == row['messages'][1]
    mixed = root/'data/mixed-7b-001/train.jsonl'
    assert mixed.read_bytes() == (root/'data/train-chat.jsonl').read_bytes()+(root/'data/corrective-002/train.jsonl').read_bytes()
    assert len(mixed.read_text().splitlines()) == 342
    fresh_root = root/'data/corrective-003'
    fresh = [json.loads(line) for line in (fresh_root/'train.jsonl').read_text().splitlines()]
    fresh_manifest = json.loads((fresh_root/'cases.json').read_text())
    assert len(fresh) == 32 and len(fresh_manifest['cases']) == 16
    assert digest(fresh_root/'train.jsonl') == fresh_manifest['train_sha256']
    for name, header in fresh_manifest['headers'].items():
        assert digest(fresh_root/'headers'/(name+'.txt')) == header['sha256']
        assert digest(root/'data'/header['source']) == header['sha256']
    for case in fresh_manifest['cases']:
        source = (fresh_root/case['source']).read_text()
        assert digest(fresh_root/case['source']) == case['source_sha256']
        assert digest(fresh_root/case['input']) == case['input_sha256']
        for index, style in zip(case['row_indices'], ['compact', 'development_generic']):
            user, assistant = fresh[index]['messages']
            assert [user['role'], assistant['role']] == ['user', 'assistant']
            assert user['content'] == (fresh_root/'headers'/(style+'.txt')).read_text()+'\n'+case['task_body']
            answer = assistant['content']
            assert answer.count('```') == 2 and answer.count('```csharp\n') == 1
            assert answer.split('```csharp\n', 1)[1].rsplit('```', 1)[0] == source
            assert hashlib.sha256(answer.encode()).hexdigest() == case['assistant_sha256']
    native = json.loads((fresh_root/'native-review-002/report.json').read_text())
    assert native['passed'] == native['total'] == 16
    checks = [value for task in native['tasks'] for value in task['checks'].values()]
    assert len(checks) == 648 and all(value is True for value in checks)
    targeted = root/'data/targeted-7b-001/train.jsonl'
    assert targeted.read_bytes() == (root/'data/corrective-002/train.jsonl').read_bytes()+(fresh_root/'train.jsonl').read_bytes()
    assert len(targeted.read_text().splitlines()) == 224
    token_receipt = json.loads((root/'data/targeted-7b-001/token-receipt.json').read_text())
    assert token_receipt['rows'] == 224 and token_receipt['truncated_rows'] == 0
    assert token_receipt['corpus_sha256'] == digest(targeted)
    assert token_receipt['all_assistant_eos_exact'] and token_receipt['all_prompt_prefixes_exact'] and token_receipt['all_single_csharp_fences']
    seen_root = root/'evidence/seen-replay005'
    selected = json.loads((seen_root/'selected-rows.json').read_text())
    comparison = json.loads((seen_root/'comparison.json').read_text())
    seen_answers = {row['id']: row['response'] for row in json.loads((seen_root/'capture/responses.json').read_text())}
    target_rows = [json.loads(line) for line in targeted.read_text().splitlines()]
    assert len(selected['rows']) == len(seen_answers) == 6
    assert selected['corpus_sha256'] == digest(targeted)
    assert comparison['qualification_eligible'] is False and comparison['qualification_credit'] == 0
    assert comparison['all_code_and_answer_bytes_exact'] is True and comparison['native_execution_repeated'] is False
    for row in selected['rows']:
        answer = target_rows[row['training_line_1based']-1]['messages'][1]['content']
        assert seen_answers[row['id']] == answer
        assert hashlib.sha256(answer.encode()).hexdigest() == row['expected_answer_sha256']
    diversity_root = root/'data/corrective-004'
    diversity = [json.loads(line) for line in (diversity_root/'train.jsonl').read_text().splitlines()]
    diversity_manifest = json.loads((diversity_root/'manifest.json').read_text())
    assert len(diversity) == 320 and len(diversity_manifest['teacher_bindings']) == 80
    assert len({teacher['source_sha256'] for teacher in diversity_manifest['teacher_bindings']}) == 71
    assert digest(diversity_root/'train.jsonl') == diversity_manifest['train_sha256']
    header = (diversity_root/'generic-header.txt').read_text()
    assert digest(diversity_root/'generic-header.txt') == digest(root/'data/corrective-002/headers/development_generic.txt')
    teachers = {teacher['original_teacher_id']: teacher for teacher in diversity_manifest['teacher_bindings']}
    parents = {name: [json.loads(line) for line in (root/'data'/name/'train.jsonl').read_text().splitlines()]
               for name in ['corrective-001', 'corrective-003']}
    for teacher in teachers.values():
        assert digest(root/teacher['source']) == teacher['source_sha256']
        assert digest(root/teacher['input']) == teacher['input_sha256']
    for row, binding in zip(diversity, diversity_manifest['row_bindings']):
        teacher = teachers[binding['original_teacher_id']]
        user, assistant = row['messages']
        assert [user['role'], assistant['role']] == ['user', 'assistant']
        assert user['content'].startswith(header+'\n')
        assert hashlib.sha256(user['content'].encode()).hexdigest() == binding['prompt_sha256']
        original = parents[teacher['original_dataset']][teacher['original_corpus_line_1based']-1]['messages'][1]
        assert assistant == original
        assert hashlib.sha256(assistant['content'].encode()).hexdigest() == binding['assistant_sha256']
        assert assistant['content'].split('```csharp\n', 1)[1].rsplit('```', 1)[0] == (root/teacher['source']).read_text()
    history = [json.loads(line) for line in (diversity_root/'history/attempt-001/train.jsonl').read_text().splitlines()]
    correction = json.loads((diversity_root/'prose-correction-receipt.json').read_text())
    changed = [index for index, (old, new) in enumerate(zip(history, diversity), 1)
               if old['messages'][0] != new['messages'][0]]
    assert len(history) == 320 and len(changed) == 16 and changed == correction['changed_prompt_lines_1based']
    assert all(old['messages'][1] == new['messages'][1] for old, new in zip(history, diversity))
    assert all(teachers[diversity_manifest['row_bindings'][index-1]['original_teacher_id']]['family'] == 'scan-normals'
               for index in changed)
    short_root = root/'data/corrective-005'
    short = [json.loads(line) for line in (short_root/'train.jsonl').read_text().splitlines()]
    short_manifest = json.loads((short_root/'manifest.json').read_text())
    assert len(short) == 160 and len(short_manifest['teacher_bindings']) == 80
    assert len({row['messages'][0]['content'] for row in short}) == 160
    assert digest(short_root/'train.jsonl') == short_manifest['train_sha256']
    for teacher in short_manifest['teacher_bindings']:
        prior = {key:value for key,value in teachers[teacher['original_teacher_id']].items()
                 if key != 'semantic_specification'}
        assert teacher == prior
    for row, binding in zip(short, short_manifest['row_bindings']):
        teacher = teachers[binding['original_teacher_id']]
        user, assistant = row['messages']
        assert [user['role'], assistant['role']] == ['user', 'assistant']
        assert user['content'].startswith(header+'\n')
        body = user['content'][len(header)+1:]
        assert len(body) == binding['task_body_chars'] and len(body) <= binding['task_body_limit']
        assert hashlib.sha256(user['content'].encode()).hexdigest() == binding['prompt_sha256']
        assert hashlib.sha256(body.encode()).hexdigest() == binding['task_body_sha256']
        assert assistant == parents[teacher['original_dataset']][teacher['original_corpus_line_1based']-1]['messages'][1]
        assert hashlib.sha256(assistant['content'].encode()).hexdigest() == binding['assistant_sha256']
    short_tokens = json.loads((short_root/'tokenization-receipt.json').read_text())
    assert short_tokens['rows'] == 160 and short_tokens['max_full_tokens'] == 1759
    assert short_tokens['truncated_rows'] == 0 and all(value is True for value in short_tokens['checks'].values())
    profile14b = json.loads((root/'base-profile-14b.json').read_text())
    repack = json.loads((root/'diagnostics/model14b-preparation/repack-receipt.json').read_text())
    assert short_tokens['base_profile_sha256'] == digest(root/'base-profile-14b.json') == repack['profile_sha256']
    assert repack['output_files_sha256'] == profile14b['model_files_sha256']
    assert len(profile14b['model_files_sha256']) == 9 and len(repack['tensor_records']) == repack['tensor_count'] == 1255
    assert repack['repacker_source_sha256'] == digest(root/'repack_model14b.py')
    baseline14b = json.loads((root/'evidence/baseline-14b-report.json').read_text())
    assert baseline14b['passed'] == 4 and baseline14b['total'] == 12
    results = json.loads((root/'evidence/results-summary.json').read_text())['results']
    assert [(row['development_passed'], row.get('scan_passed')) for row in results if row['status'] == 'rejected'] == [(0, 0), (0, 0), (2, 0), (3, 0), (4, 2), (2, 3), (4, 1), (4, 0)]
    assert all(row['manufacturing_authorized'] is False for row in results)
    check_completed32b(root, release)
    assert 'TRUSTED_PROFILE_SHA256 = None' in (root/'qwen-picogk-am').read_text()
    forbidden = re.compile(r'/Users/|-----BEGIN .*PRIVATE KEY|Bearer [A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{20,}|VIN\s*[:=]', re.I)
    for relative in release['files_sha256']:
        path = root/relative
        if is_text_member(relative, path.read_bytes()) and relative not in ('check_publication.py', 'prepare_release_assets.py'):
            assert not forbidden.search(path.read_text()), 'Private/credential-shaped public text: '+relative
    if assets is not None:
        for record in release['assets']:
            path = assets/record['asset']
            assert path.stat().st_size == record['bytes'] and digest(path) == record['sha256']
    if native_runtime:
        expected = json.loads((root/'native-runtime-manifest.json').read_text())
        pico = Path(os.environ.get('QWEN_PICOGK_AM_PICO', str(root/'work/picogk-runtime')))
        dotnet = Path(os.environ.get('QWEN_PICOGK_AM_DOTNET', shutil.which('dotnet') or str(root/'work/dotnet/dotnet')))
        assert digest(dotnet) == expected['dotnet_executable_sha256'], 'Pinned .NET executable changed'
        for name, value in expected['files_sha256'].items():
            assert digest(pico/name) == value, 'Pinned PicoGK dependency changed: '+name
    return {'verified_files': len(release['files_sha256']), 'raw_pairs': 150,
            'validated_teachers': 64, 'prompt_augmented_rows': 192, 'mixed7b_rows': 342,
            'new_validated_teachers': 16, 'new_teacher_checks': 648,
            'targeted7b_rows': 224,
            'seen_training_answers_exact': 6, 'seen_replay_qualification_credit': 0,
            'task_body_augmented_rows': 320, 'existing_diversity_teachers': 80,
            'existing_diversity_source_programs': 71, 'retained_prose_corrections': 16,
            'short_task_augmented_rows': 160, 'short_task_max14b_tokens': 1759,
            'repacked_base_tensor_metadata': 1255, 'untouched14b_baseline_passes': 4,
            'untouched32b_v1_and_v2_baseline_passes': [5, 5], 'memory_smoke_qualification_eligible': False,
            'historical_checker_profile_reanchored': False, 'active_course009_payload_included': False,
            'asset_hashes_checked': assets is not None, 'native_payload_hashes_checked': native_runtime,
            'mlx_imported': False, 'generated_code_executed': False,
            'qualified_adapter': False, 'manufacturing_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--native-runtime', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(assets=args.assets, native_runtime=args.native_runtime), indent=2))
