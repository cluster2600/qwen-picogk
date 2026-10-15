#!/usr/bin/env python3
"""Augment only generic prompt headers; retain all 64 validated teacher targets."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent/'corrective-001'
WORK = ROOT.parents[1]
MARKER = 'Prefer a compact complete program.'
REFUSAL = 'Do not initialize PicoGK for this refusal; no geometry is justified. '


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def literal_constant(path, name):
    # AST extraction executes neither the serving CLI nor teacher generator.
    tree = ast.parse(path.read_text())
    assignments = [node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    assert len(assignments) == 1
    value = ast.literal_eval(assignments[0])
    assert isinstance(value, str) and value
    return value


def generate():
    source = PARENT/'train.jsonl'
    cases_path = PARENT/'cases.json'
    native_path = PARENT/'native-review-002/report.json'
    development_path = WORK/'evaluation/development.json'
    serving_path = WORK/'qwen-picogk-am'
    source_rows = [json.loads(line) for line in source.read_text().splitlines()]
    cases = json.loads(cases_path.read_text())['cases']
    native = json.loads(native_path.read_text())
    assert len(source_rows) == len(cases) == 64 and native['passed'] == native['total'] == 64
    assert native['train_sha256'] == sha(source)
    assert native['cases_sha256'] == sha(cases_path)
    passed = {task['id']: task for task in native['tasks']}
    card = literal_constant(PARENT/'author.py', 'CARD')
    guidance = literal_constant(serving_path, 'API_GUIDANCE')
    # Read DEVELOPMENT only. Every task must have the same generic prefix.
    development = json.loads(development_path.read_text())['tasks']
    prefixes = []
    heldout_suffixes = []
    for task in development:
        prefix, boundary, suffix = task['prompt'].partition(MARKER)
        assert boundary == MARKER and prefix and suffix.strip()
        assert task['id'] not in prefix
        prefixes.append(prefix)
        heldout_suffixes.append(suffix.strip())
    assert len(development) == 12 and len(set(prefixes)) == 1
    full = prefixes[0]
    headers = {'compact': card, 'development_generic': full, 'serving_generic': guidance}
    (ROOT/'headers').mkdir(parents=True, exist_ok=True)
    for style, header in headers.items():
        with (ROOT/'headers'/(style+'.txt')).open('x') as out:
            out.write(header)

    rows = []
    bindings = []
    for original, case in zip(source_rows, cases):
        assert set(original) == {'messages'}
        user, assistant = original['messages']
        assert user['role'] == 'user' and assistant['role'] == 'assistant'
        target = assistant['content']
        assert target.count('```') == 2 and target.count('```csharp\n') == 1
        code = target.split('```csharp\n', 1)[1].rsplit('```', 1)[0]
        assert code == (PARENT/case['source']).read_text()
        assert text_sha(code) == case['source_sha256'] == passed[case['id']]['source_sha256']
        assert sha(PARENT/case['input']) == case['input_sha256'] == passed[case['id']]['input_sha256']
        assert passed[case['id']]['status'] == 'passed' and passed[case['id']]['native_exit_code'] == 0
        assert all(type(value) is bool and value for value in passed[case['id']]['checks'].values())
        original_card = card
        if case['kind'] == 'refusal':
            original_card = card.replace('Use an explicit headless Library with scoped disposal. ', REFUSAL)
            assert REFUSAL in user['content'] and 'using Library' not in code
        assert user['content'].startswith(original_card)
        body = user['content'][len(original_card):]
        assert body
        for style, header in headers.items():
            if style == 'compact':
                prompt = original_card+body
                assert prompt == user['content']
            else:
                separator = '\n' if style == 'development_generic' else '\n\nUser request:\n'
                override = REFUSAL if case['kind'] == 'refusal' else ''
                prompt = header+separator+override+body
                # The only suffix is the fresh original teacher body and its refusal override.
                assert prompt[len(header)+len(separator):] == override+body
            assert all(suffix not in prompt for suffix in heldout_suffixes)
            assert all(task['id'] not in prompt for task in development)
            if case['kind'] == 'refusal':
                assert REFUSAL in prompt
            rows.append({'messages': [{'role': 'user', 'content': prompt},
                                      {'role': 'assistant', 'content': target}]})
            bindings.append({'line': len(rows), 'teacher_id': case['id'], 'family': case['family'],
                             'style': style, 'teacher_line': len(bindings)//3+1,
                             'prompt_sha256': text_sha(prompt), 'task_body_sha256': text_sha(body),
                             'target_sha256': text_sha(target), 'source_sha256': case['source_sha256'],
                             'input_sha256': case['input_sha256'],
                             'native_result_sha256': sha(PARENT/'native-review-002'/case['id']/'result.json')})
    assert len(rows) == len(bindings) == 192
    assert len({row['messages'][0]['content'] for row in rows}) == 192
    assert all(rows[3*i+s]['messages'][1]['content'] == source_rows[i]['messages'][1]['content']
               for i in range(64) for s in range(3))
    train = ROOT/'train.jsonl'
    with train.open('x') as out:
        out.write(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':'))+'\n' for row in rows))
    provenance = {
        'schema': 'picogk.am.generic-header-provenance@1',
        'compact': {'source': '../corrective-001/author.py', 'source_sha256': sha(PARENT/'author.py'),
                    'extraction': 'AST literal CARD; original refusal replacement preserved',
                    'header_sha256': text_sha(card)},
        'development_generic': {'source': '../../evaluation/development.json',
                    'source_sha256': sha(development_path), 'extraction': 'Exact common prefix strictly before marker',
                    'marker': MARKER, 'same_generic_prefix_in_all12': True, 'header_sha256': text_sha(full),
                    'task_specific_text_copied': False},
        'serving_generic': {'source': '../../qwen-picogk-am', 'source_sha256': sha(serving_path),
                    'extraction': 'AST literal API_GUIDANCE; no CLI import or execution',
                    'header_sha256': text_sha(guidance)},
        'refusal_override': REFUSAL, 'refusal_override_source': 'Exact original compact refusal card sentence',
        'final_task_contents_read': False}
    with (ROOT/'header-provenance.json').open('x') as out:
        out.write(json.dumps(provenance, indent=2)+'\n')
    manifest = {'schema': 'picogk.am.prompt-style-augmentation@1', 'status': 'targets_bound_tokenization_pending',
        'rows': 192, 'independently_authored_teachers': 64, 'header_styles': 3,
        'style_counts': dict(Counter(b['style'] for b in bindings)),
        'train_sha256': sha(train), 'parent_train_sha256': sha(source), 'parent_cases_sha256': sha(cases_path),
        'parent_native_report_sha256': sha(native_path),
        'parent_compile_receipt_sha256': sha(PARENT/'compile-review-001/receipt.json'),
        'parent_release_manifest_sha256': sha(PARENT/'release-manifest.json'),
        'header_provenance_sha256': sha(ROOT/'header-provenance.json'), 'augment_source_sha256': sha(Path(__file__)),
        'all_targets_unchanged': True, 'all_sources_fixtures_unchanged': True,
        'all_targets_single_complete_csharp_fence': True, 'all_refusal_no_initialization_directives_retained': True,
        'all64_parent_native_results_pass': True, 'native_execution_repeated': False,
        'development_task_suffixes_copied': False, 'captured_model_answers_used': False,
        'final_task_contents_read': False, 'model_loading': False, 'gpu_inference': False, 'training': False,
        'qualification': 'Prompt-style augmentation of64 validated teacher programs; not192 new programs or model qualification.',
        'manufacturing_authorized': False, 'rows_binding': bindings}
    with (ROOT/'manifest.json').open('x') as out:
        out.write(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'rows_binding'}, indent=2))


if __name__ == '__main__':
    generate()
