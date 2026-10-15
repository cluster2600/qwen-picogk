"""Freeze exact mixed-corpus bytes and validate with a CPU-only pinned tokenizer."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path('am-code')
OUTPUT = Path(__file__).resolve().parent
SOURCES = (
    ('data/train-chat.jsonl', 150, '1ac93688653ea7aa26b1e93b739eaac21717e11af4f9996972b6735bb20fe684'),
    ('data/corrective-002/train.jsonl', 192, '9966a99f998f544fdfe3d9370f53e131e5ae31061b3e89ae196d3f34e56d6a65'),
)
PROFILE_SHA256 = 'e518369dfb009746e5ab92497741286b72d581b4ac05c3995404d6a6a0657129'
MAX_SEQUENCE = 6144


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + '\n')


def strict_rows(payload):
    assert payload.endswith(b'\n'), 'No separator bytes may be invented during concatenation.'
    rows = [json.loads(line) for line in payload.decode('utf-8').splitlines()]
    for number, row in enumerate(rows, 1):
        assert isinstance(row, dict) and set(row) == {'messages'}, number
        assert isinstance(row['messages'], list) and len(row['messages']) == 2, number
        assert all(isinstance(message, dict) and set(message) == {'role', 'content'}
                   and message['role'] == role and isinstance(message['content'], str)
                   and message['content'].strip()
                   for message, role in zip(row['messages'], ('user', 'assistant'))), number
    return rows


def main():
    assert not (OUTPUT / 'train.jsonl').exists(), 'Preserve prior mixed-corpus evidence.'
    payloads = []
    source_records = []
    for name, count, expected in SOURCES:
        payload = (ROOT / name).read_bytes()
        assert sha(payload) == expected and len(strict_rows(payload)) == count
        payloads.append(payload)
        source_records.append({'path': name, 'rows': count, 'bytes': len(payload), 'sha256': expected})
    payload = b''.join(payloads)
    rows = strict_rows(payload)
    assert len(rows) == 342
    with (OUTPUT / 'train.jsonl').open('xb') as stream:
        stream.write(payload)
    assert (OUTPUT / 'train.jsonl').read_bytes() == payload

    profile_bytes = (ROOT / 'base-profile-7b.json').read_bytes()
    assert sha(profile_bytes) == PROFILE_SHA256
    profile = json.loads(profile_bytes)
    model = ROOT / profile['model_directory']
    for name in ('added_tokens.json', 'config.json', 'merges.txt', 'model.safetensors.index.json',
                 'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json'):
        assert sha((model / name).read_bytes()) == profile['model_files_sha256'][name]
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
                      HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false',
                      USE_TORCH='0', USE_TF='0', USE_FLAX='0')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
    # Load this standalone CPU-only source by file path, bypassing mlx_lm.__init__.
    datasets_path = Path('runtime/venv/lib/python3.12/site-packages/mlx_lm/tuner/datasets.py')
    spec = importlib.util.spec_from_file_location('mixed_cpu_chat_dataset', datasets_path)
    datasets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(datasets)
    dataset = datasets.ChatDataset(rows, tokenizer, mask_prompt=True)
    assert tokenizer.eos_token == '<|im_end|>'
    evidence = []
    for index, row in enumerate(rows):
        tokens, offset = dataset.process(row)
        prefix = tokenizer.apply_chat_template(row['messages'][:-1], tools=None,
            add_generation_prompt=True, return_dict=False)
        answer = row['messages'][1]['content']
        fences = re.findall(r'```(?:csharp|cs|C#)\s*\n(.*?)```', answer, re.S)
        assert len(fences) == 1 and answer.count('```') == 2, index
        assert 0 < offset < len(tokens) <= MAX_SEQUENCE, index
        assert tokens[:offset] == prefix, index
        assistant = tokens[offset:]
        assert assistant.count(tokenizer.eos_token_id) == 1, index
        assert tokenizer.decode(assistant, skip_special_tokens=False) == answer + '<|im_end|>\n', index
        evidence.append({'row': index + 1, 'source': SOURCES[0][0] if index < 150 else SOURCES[1][0],
                         'full_tokens': len(tokens), 'prompt_mask_offset': offset,
                         'assistant_tokens': len(assistant), 'assistant_eos_count': 1,
                         'csharp_fences': 1, 'row_sha256': sha(json.dumps(row, sort_keys=True).encode())})
    assert not any(name == 'mlx' or name.startswith('mlx.') for name in sys.modules)
    save(OUTPUT / 'token-rows.json', evidence)
    full = [entry['full_tokens'] for entry in evidence]
    assistants = [entry['assistant_tokens'] for entry in evidence]
    token_receipt = {
        'schema': 'picogk.am.mixed-tokenizer-validation@1', 'status': 'passed', 'rows': len(rows),
        'train_sha256': sha(payload), 'base_profile_sha256': PROFILE_SHA256,
        'model_files_sha256': profile['model_files_sha256'],
        'tokenizer_class': type(tokenizer).__name__, 'tokenizer_eos_token_id': tokenizer.eos_token_id,
        'chat_dataset_source_sha256': sha(datasets_path.read_bytes()),
        'packages': {name: importlib.metadata.version(name) for name in ('transformers', 'tokenizers', 'mlx-lm')},
        'max_full_tokens': max(full), 'min_full_tokens': min(full), 'mean_full_tokens': sum(full) / len(full),
        'max_assistant_tokens': max(assistants), 'total_full_tokens': sum(full),
        'total_assistant_tokens': sum(assistants), 'max_sequence_length': MAX_SEQUENCE,
        'all_prompt_prefixes_exact': True, 'mask_prompt': True,
        'all_single_csharp_fences': True, 'all_assistant_eos_exact': True,
        'truncated_rows': 0, 'mlx_imported': False, 'model_loaded': False, 'gpu_used': False,
        'token_rows_sha256': sha((OUTPUT / 'token-rows.json').read_bytes()),
    }
    save(OUTPUT / 'token-receipt.json', token_receipt)
    provenance = {
        'schema': 'picogk.am.mixed-corpus@1', 'status': 'frozen_for_registration',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'sources': source_records,
        'operation': 'exact byte concatenation in declared source order; no reserialization',
        'train_sha256': sha(payload), 'rows': len(rows), 'bytes': len(payload),
        'unique_user_prompts': len({row['messages'][0]['content'] for row in rows}),
        'unique_assistant_answers': len({row['messages'][1]['content'] for row in rows}),
        'base_profile_sha256': PROFILE_SHA256,
        'preparation_source_sha256': sha(Path(__file__).read_bytes()),
        'token_receipt_sha256': sha((OUTPUT / 'token-receipt.json').read_bytes()),
        'qualification': 'teaching corpus and tokenizer validation only', 'manufacturing_authorized': False,
        'training_started': False, 'model_loaded': False, 'gpu_used': False,
    }
    # Check original sources again before releasing this derivative.
    for name, _, expected in SOURCES:
        assert sha((ROOT / name).read_bytes()) == expected
    save(OUTPUT / 'provenance.json', provenance)
    print(json.dumps({'rows': len(rows), 'train_sha256': sha(payload),
                      'max_full_tokens': max(full), 'max_assistant_tokens': max(assistants),
                      'token_receipt_sha256': provenance['token_receipt_sha256'],
                      'provenance_sha256': sha((OUTPUT / 'provenance.json').read_bytes()),
                      'model_loaded': False, 'mlx_imported': False}), flush=True)


if __name__ == '__main__':
    main()
