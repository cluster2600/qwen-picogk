"""Bind validated compact rehearsal and new native-tested correction programs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    if (ROOT / 'train.jsonl').exists():
        raise FileExistsError('Preserve any prior frozen mixture.')
    prior = module('accepted_short_author', WORK / 'data/corrective-005/augment.py')
    payload = (WORK / 'data/focused-32b-005/train.jsonl').read_text()
    retained = json.loads((WORK / 'data/focused-32b-005/manifest.json').read_text())
    old_teachers = retained['existing_teacher_bindings'] + json.loads((WORK / 'data/corrective-010/cases.json').read_text())['cases']
    old_bindings = retained['existing_row_bindings'] + retained['new_row_bindings']
    assert hashlib.sha256(payload.encode()).hexdigest() == 'c84ae00c5946231e8638dcf54796effed8f1aa5b97266c168aafe1180b3c1385'
    current = module('new_correction_author', WORK / 'data/corrective-011/author.py')
    cases = json.loads((current.ROOT / 'cases.json').read_text())
    report = json.loads((current.ROOT / 'native-review-001/report.json').read_text())
    assert report['passed'] == report['total'] == 48 and report['acceptance_thresholds_changed'] is False
    assert report['train_sha256'] == cases['train_sha256'] == sha(current.ROOT / 'train.jsonl')
    assert report['cases_sha256'] == sha(current.ROOT / 'cases.json')
    results = {row['id']: row for row in report['tasks']}
    new_rows = [json.loads(line) for line in (current.ROOT / 'train.jsonl').read_text().splitlines()]
    rows = [json.loads(line) for line in payload.splitlines()]
    bindings = []
    for number, (row, case) in enumerate(zip(new_rows, cases['cases']), 1):
        result = results[case['id']]
        assert result['status'] == 'passed' and result['native_exit_code'] == 0
        assert result['checks'] and all(type(v) is bool and v for v in result['checks'].values())
        assert result['source_sha256'] == case['source_sha256'] == sha(current.ROOT / case['source'])
        assert result['input_sha256'] == case['input_sha256'] == sha(current.ROOT / case['input'])
        answer = row['messages'][1]['content']
        assert answer.split('```csharp\n', 1)[1].rsplit('```', 1)[0] == (current.ROOT / case['source']).read_text()
        card = module('base_teaching_api', WORK / 'data/corrective-001/author.py').CARD
        if case['kind'] == 'refusal':
            card = card.replace('Use an explicit headless Library with scoped disposal. ',
                                'Do not initialize PicoGK for this refusal; no geometry is justified. ')
        prompt = row['messages'][0]['content']
        assert prompt.startswith(card)
        task = prompt[len(card):]
        if case['family'] == 'stl-roundtrip':
            task += f' Synthetic example centre {case["oracle"]["centre"]}, half-extents {case["oracle"]["half"]} mm; replacement inputs still determine actual geometry.'
        if case['kind'] == 'geometry':
            task += ' Write report.json exactly {"status":"geometric_candidate","qualification":"geometry_only","manufacturing_authorized":false}.'
        for style, body in [('task_first', task), ('receiver_construction', 'Implement the complete program with exact supported receiver types and unchanged solid dimensions and input controls: '+task)]:
            user = prior.HEADER.read_text()+'\n'+body
            rows.append({'messages': [{'role': 'user', 'content': user}, {'role': 'assistant', 'content': answer}]})
            bindings.append(dict(line_1based=len(rows), teacher_row_1based=number, id=case['id'], style=style,
                source_sha256=case['source_sha256'], input_sha256=case['input_sha256'],
                native_result_sha256=sha(current.ROOT / 'native-review-001' / case['id'] / 'result.json'),
                assistant_sha256=hashlib.sha256(answer.encode()).hexdigest()))
    assert len(rows) == 592 and len(bindings) == 96 and len(old_teachers) == 224
    assert len({x['messages'][0]['content'] for x in rows}) == 592
    text = payload+''.join(json.dumps(row, ensure_ascii=False, separators=(',',':'))+'\n' for row in rows[496:])
    assert text.encode().startswith(payload.encode()) and json.loads(text.splitlines()[496]) == rows[496]
    (ROOT / 'train.jsonl').write_text(text)
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1', TOKENIZERS_PARALLELISM='false')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(WORK / 'model32b'), trust_remote_code=False, local_files_only=True)
    token_rows = []
    for number, row in enumerate(rows, 1):
        messages = row['messages']
        full = tokenizer.apply_chat_template(messages, tokenize=False)
        prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
        ids = tokenizer.encode(full, add_special_tokens=False)
        mask = tokenizer.encode(prefix, add_special_tokens=False)
        assert full.endswith('<|im_end|>\n') and ids[:len(mask)] == mask
        assert len(ids) <= 6144 and len(ids) > len(mask)
        token_rows.append(dict(line_1based=number, full_tokens=len(ids), prompt_mask_offset=len(mask),
            assistant_tokens=len(ids)-len(mask), prompt_sha256=hashlib.sha256(messages[0]['content'].encode()).hexdigest(),
            assistant_sha256=hashlib.sha256(messages[1]['content'].encode()).hexdigest()))
    (ROOT / 'token-rows.json').write_text(json.dumps(token_rows, indent=2)+'\n')
    manifest = dict(schema='picogk.am.focused-mixture@1', status='native_and_token_checks_passed',
        rows=592, original_accepted_rows_preserved_exactly=496, new_rows=96, new_teacher_cases=48,
        existing_teacher_cases=224, train_sha256=sha(ROOT/'train.jsonl'), author_sha256=sha(Path(__file__)),
        accepted_corpus_sha256=sha(WORK/'data/focused-32b-005/train.jsonl'),
        accepted_manifest_sha256=sha(WORK/'data/focused-32b-005/manifest.json'),
        new_cases_sha256=sha(current.ROOT/'cases.json'), new_native_report_sha256=sha(current.ROOT/'native-review-001/report.json'),
        new_author_sha256=sha(current.ROOT/'author.py'), token_rows_sha256=sha(ROOT/'token-rows.json'),
        tokenizer_base_profile_sha256=sha(WORK/'base-profile-32b.json'), maximum_tokens=max(x['full_tokens'] for x in token_rows),
        total_assistant_tokens=sum(x['assistant_tokens'] for x in token_rows),
        all_prefix_masks_exact=True, all_eos_and_complete_programs=True, truncation=False,
        existing_teacher_bindings=old_teachers, existing_row_bindings=old_bindings, new_row_bindings=bindings,
        original150_unchanged_previously_trained_in_course009=True,
        task_source='Existing frozen teacher metadata plus new synthetic correction cases, never final task bodies or repaired captured responses.',
        final_contents_read=False, mlx_imported=False, gpu_used=False, manufacturing_authorized=False)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({k: manifest[k] for k in ('rows','train_sha256','maximum_tokens','total_assistant_tokens','status')}, indent=2))


if __name__ == '__main__':
    main()
