"""Portable MLX inference; proposals never execute geometry or generated code."""
import argparse
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

import contracts

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        sha = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            sha.update(chunk)
        return sha.hexdigest()


def verify_files(folder, expected):
    root = folder.resolve()
    for name, sha in expected.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or digest(path) != sha:
            raise ValueError('Missing, changed or escaping release input: '+name)


def load_model(adapter='planner', base=None):
    manifest = json.loads((ROOT/'release.json').read_text())
    adapter_path = ROOT/'models'/adapter
    verify_files(adapter_path, manifest['adapters'][adapter])
    for package, expected in manifest['packages'].items():
        if version(package) != expected:
            raise ValueError('Use the pinned runtime in requirements.txt: '+package)
    os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1')
    if base is None:
        from huggingface_hub import snapshot_download
        base = Path(snapshot_download(manifest['base']['repo_id'], revision=manifest['base']['revision'],
                                     allow_patterns=list(manifest['base']['files']), token=False))
    verify_files(base, manifest['base']['files'])
    import mlx.core as mx
    from mlx_lm import load
    mx.set_memory_limit(8*1024**3)
    mx.set_cache_limit(256*1024**2)
    mx.random.seed(manifest['decoding']['seed'])
    model, tokenizer = load(str(base), adapter_path=str(adapter_path), tokenizer_config={'trust_remote_code': False})
    tokenizer.add_eos_token('<|im_end|>')
    return model, tokenizer


def generate(model, tokenizer, system, user):
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    prompt = tokenizer.apply_chat_template([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                                          tokenize=False, add_generation_prompt=True)
    if len(tokenizer.encode(prompt)) > 1024:
        raise ValueError('Prompt exceeds the registered context')
    text, last = '', None
    for last in stream_generate(model, tokenizer, prompt=prompt, max_tokens=192, sampler=make_sampler(temp=0)):
        text += last.text
    return text, last.finish_reason if last else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, help='Existing exact pinned MLX base; otherwise download the public revision')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error('Use a new output file in an existing directory')
    if args.request.stat().st_size > 65536:
        parser.error('Request exceeds 64 KiB')
    request = json.loads(args.request.read_text(), object_pairs_hook=contracts.unique)
    expected = contracts.normalize(request)
    receipt = dict(request_sha256=digest(args.request), geometry_executed=False, manufacturing_qualified=False)
    if expected['recipe'] == 'needs_measurement':
        receipt.update(plan=expected, model_called=False, semantic_intent_verified=True)
    else:
        with (ROOT/'models/planner/.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            model, tokenizer = load_model(base=args.base)
            system = json.loads((ROOT/'release.json').read_text())['system_prompt']
            text, finish = generate(model, tokenizer, system, contracts.canonical(request))
            receipt.update(model_called=True, adapter_sha256=digest(ROOT/'models/planner/adapters.safetensors'))
            try:
                receipt.update(plan=contracts.accepted(text, finish, request), semantic_intent_verified=True)
            except (ValueError, TypeError) as error:
                receipt.update(plan=None, semantic_intent_verified=False, error=str(error), raw_response=text)
    with args.output.open('x') as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt['semantic_intent_verified']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
