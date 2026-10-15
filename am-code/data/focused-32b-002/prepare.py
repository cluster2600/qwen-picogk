"""Append native-validated synthetic rehearsal; preserve the prior corpus exactly."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (ROOT / 'train.jsonl').exists():
        raise FileExistsError('Preserve frozen corpora.')
    prior = WORK / 'data/focused-32b-001'
    teachers = WORK / 'data/corrective-007'
    payload = (prior / 'train.jsonl').read_bytes()
    assert sha(prior / 'train.jsonl') == 'ca8e13ad659c55e93192c1c5a7c1029f3228753beceee7873c54a4f81c8519f2'
    cases = json.loads((teachers / 'cases.json').read_text())
    review = json.loads((teachers / 'native-review-001/report.json').read_text())
    assert review['total'] == review['passed'] == cases['count'] == 64
    assert review['acceptance_thresholds_changed'] is False
    assert review['train_sha256'] == cases['train_sha256'] == sha(teachers / 'train.jsonl')
    assert review['cases_sha256'] == sha(teachers / 'cases.json')
    spec = importlib.util.spec_from_file_location('accepted_formulations', WORK / 'data/corrective-005/augment.py')
    author = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(author)
    assert sha(author.HEADER) == author.HEADER_SHA
    header = author.HEADER.read_text()
    rows = [json.loads(line) for line in payload.splitlines()]
    originals = [json.loads(line) for line in (teachers / 'train.jsonl').read_text().splitlines()]
    results = {r['id']: r for r in review['tasks']}
    bindings = []
    for number, (case, row) in enumerate(zip(cases['cases'], originals), 1):
        result = results[case['id']]
        code = (teachers / case['source']).read_text()
        answer = row['messages'][1]['content']
        assert result['status'] == 'passed' and result['native_exit_code'] == 0
        assert result['checks'] and all(type(v) is bool and v for v in result['checks'].values())
        assert result['source_sha256'] == case['source_sha256'] == sha(teachers / case['source'])
        assert result['input_sha256'] == case['input_sha256'] == sha(teachers / case['input'])
        assert answer.split('```csharp\n', 1)[1].rsplit('```', 1)[0] == code
        for style, body in zip(('task_first', 'rephrased'), author.bodies(case, code, teachers / case['input'])):
            if case['family'] == 'scan-normals':
                body += f' Synthetic example centre {case["oracle"]["centre"]}, half-extents {case["oracle"]["half"]} mm; replacement inputs still determine geometry.'
            elif case['family'] == 'xyz-occupancy':
                body += f' Synthetic example observations {case["oracle"]["points"]} mm; always parse the actual replacement file.'
            rows.append({'messages': [{'role': 'user', 'content': header+'\n'+body},
                                      {'role': 'assistant', 'content': answer}]})
            bindings.append(dict(line_1based=len(rows), teacher_row_1based=number, id=case['id'],
                style=style, source_sha256=case['source_sha256'], input_sha256=case['input_sha256'],
                native_result_sha256=sha(teachers / 'native-review-001' / case['id'] / 'result.json'),
                assistant_sha256=hashlib.sha256(answer.encode()).hexdigest()))
    assert len(rows) == 384 and len(bindings) == 128
    assert len({r['messages'][0]['content'] for r in rows}) == 384
    text = payload + ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':'))+'\n'
                             for r in rows[256:]).encode()
    assert text.startswith(payload)
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
        assert full.endswith('<|im_end|>\n') and ids[:len(mask)] == mask and len(mask) < len(ids) <= 6144
        token_rows.append(dict(line_1based=number, full_tokens=len(ids), prompt_mask_offset=len(mask),
            assistant_tokens=len(ids)-len(mask), prompt_sha256=hashlib.sha256(messages[0]['content'].encode()).hexdigest(),
            assistant_sha256=hashlib.sha256(messages[1]['content'].encode()).hexdigest()))
    (ROOT / 'train.jsonl').write_bytes(text)
    (ROOT / 'token-rows.json').write_text(json.dumps(token_rows, indent=2)+'\n')
    manifest = dict(schema='picogk.am.focused-mixture@2', status='native_and_token_checks_passed',
        rows=384, prior_rows_preserved_exactly=256, new_rows=128, new_teacher_cases=64,
        train_sha256=sha(ROOT / 'train.jsonl'), author_sha256=sha(Path(__file__)),
        reused_formulation_source_sha256=sha(WORK / 'data/corrective-005/augment.py'),
        prior_manifest_sha256=sha(prior / 'manifest.json'), prior_corpus_sha256=sha(prior / 'train.jsonl'),
        new_cases_sha256=sha(teachers / 'cases.json'), new_native_report_sha256=sha(teachers / 'native-review-001/report.json'),
        token_rows_sha256=sha(ROOT / 'token-rows.json'), maximum_tokens=max(x['full_tokens'] for x in token_rows),
        total_assistant_tokens=sum(x['assistant_tokens'] for x in token_rows),
        new_row_bindings=bindings, all_prefix_masks_exact=True, all_eos_and_complete_programs=True,
        truncation=False, final_contents_read=False, mlx_imported=False, gpu_used=False,
        source='New synthetic dimensions using known recipes; no captured-answer repair or final answers.',
        original150_preserved_and_previously_trained=True, manufacturing_authorized=False)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({k: manifest[k] for k in ('rows','train_sha256','maximum_tokens','total_assistant_tokens')}))


if __name__ == '__main__':
    main()
