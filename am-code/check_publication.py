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
    results = json.loads((root/'evidence/results-summary.json').read_text())['results']
    assert [(row['development_passed'], row.get('scan_passed')) for row in results if row['status'] == 'rejected'] == [(0, 0), (0, 0), (2, 0), (3, 0), (4, 2), (2, 3)]
    assert all(row['manufacturing_authorized'] is False for row in results)
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
            'asset_hashes_checked': assets is not None, 'native_payload_hashes_checked': native_runtime,
            'mlx_imported': False, 'generated_code_executed': False,
            'qualified_adapter': False, 'manufacturing_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--native-runtime', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(assets=args.assets, native_runtime=args.native_runtime), indent=2))
