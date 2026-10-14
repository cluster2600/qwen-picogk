#!/usr/bin/env python3
"""Run the installed MLX trainer in the process holding its memory limit and lock."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'model'
spec=importlib.util.spec_from_file_location('am_training_base_runtime',ROOT/'base_runtime.py')
base_runtime=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_runtime)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def supplemental_corpus(path, expected_sha256):
    """Verify an exact-byte chat corpus before importing or loading a model."""
    if (path is None) != (expected_sha256 is None):
        raise ValueError('--corpus and --corpus-sha256 must be provided together.')
    if path is None: return None, 0
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('Supplemental corpus SHA-256 mismatch.')
    lines = payload.decode('utf-8').splitlines()
    if not lines: raise ValueError('Supplemental corpus is empty.')
    for number, line in enumerate(lines, 1):
        try: row = json.loads(line)
        except ValueError: raise ValueError('Invalid supplemental JSONL row '+str(number)) from None
        messages = row.get('messages') if isinstance(row, dict) else None
        if (not isinstance(row, dict) or set(row) != {'messages'} or not isinstance(messages, list)
                or len(messages) != 2 or any(not isinstance(m, dict) or set(m) != {'role', 'content'}
                    or m['role'] != role or not isinstance(m['content'], str) or not m['content'].strip()
                    for m, role in zip(messages, ('user', 'assistant')))):
            raise ValueError('Complete nonempty user/assistant messages required at row '+str(number))
    return payload, len(lines)

def resume_adapter(path):
    if path is not None and not path.is_file():
        raise ValueError('Resume adapter must be an existing file.')
    return digest(path) if path is not None else None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True)
    parser.add_argument('--iters',type=int,required=True)
    parser.add_argument('--learning-rate',type=float,default=1e-5)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--corpus',type=Path)
    parser.add_argument('--corpus-sha256')
    parser.add_argument('--base-profile',type=Path)
    args=parser.parse_args()
    if args.iters<1 or not args.name.replace('-','').isalnum(): parser.error('Positive iterations and a simple run name required.')
    try:
        supplemental, supplemental_rows=supplemental_corpus(args.corpus,args.corpus_sha256)
        resume_sha256=resume_adapter(args.resume)
        base=base_runtime.verify_base(ROOT,args.base_profile)
    except (OSError,ValueError,KeyError,TypeError) as error: parser.error(str(error))
    out=ROOT/'runs'/args.name
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'data/manifest.json').read_text())
    corpus=ROOT/'data/train-chat.jsonl'
    if digest(corpus)!=manifest['training_files']['train-chat.jsonl']['sha256']: raise ValueError('Training data changed.')
    data_folder=ROOT/'data/chat'
    if supplemental is not None:
        data_folder=out/'data';data_folder.mkdir()
        corpus=data_folder/'train.jsonl';corpus.write_bytes(supplemental)
        if digest(corpus)!=args.corpus_sha256: raise ValueError('Copied supplemental corpus changed.')
    if shutil.disk_usage(ROOT).free<2*1024**3: raise RuntimeError('Need at least 2 GiB free for bounded adapter/checkpoint output.')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
        HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2')
    lock=(ROOT.parent/'train.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.lora import CONFIG_DEFAULTS,train_model
    from mlx_lm.tuner.datasets import load_dataset
    mx.set_memory_limit(36*1024**3)
    mx.set_cache_limit(512*1024**2)
    config=CONFIG_DEFAULTS|dict(model=str(base['directory']),data=str(data_folder),train=True,
        num_layers=16,batch_size=1,iters=args.iters,learning_rate=args.learning_rate,
        max_seq_length=6144,mask_prompt=True,grad_checkpoint=True,seed=9931414,
        steps_per_report=1 if args.iters<=5 else 10,steps_per_eval=60,val_batches=-1,
        save_every=3 if args.iters<=5 else 60,adapter_path=str(out/'adapter'),
        resume_adapter_file=str(args.resume) if args.resume else None)
    protocol=dict(registered_at=datetime.now(timezone.utc).isoformat(),config=config,
        corpus_sha256=digest(corpus),source_corpus_sha256=manifest['source_dataset_sha256'],
        base_weights_sha256=base['base_weights_sha256'],memory_limit_bytes=36*1024**3,
        packages={n:importlib.metadata.version(n) for n in ('mlx','mlx-lm','transformers')},
        selection='Smoke is ineligible. Code qualification requires independent native development/final gates. No existing adapter replacement.')
    protocol.update(base['binding'])
    if supplemental is not None:
        protocol.update(supplemental_corpus_sha256=args.corpus_sha256,supplemental_rows=supplemental_rows,
            original_training_corpus_sha256=manifest['training_files']['train-chat.jsonl']['sha256'])
    if args.resume is not None: protocol['resume_adapter_sha256']=resume_sha256
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    print(json.dumps({'run':args.name,'iters':args.iters,'registered':protocol['registered_at']}),flush=True)
    mx.random.seed(config['seed'])
    np.random.seed(config['seed'])
    model,tok=load(str(base['directory']),tokenizer_config={'trust_remote_code':False})
    train,valid,_=load_dataset(SimpleNamespace(**config),tok)
    if supplemental is not None and len(train)!=supplemental_rows: raise ValueError('Supplemental row coverage changed.')
    lengths=[len(train.process(train[i])[0]) for i in range(len(train))]
    if max(lengths)>config['max_seq_length']: raise ValueError('Sequence truncation forbidden.')
    print(json.dumps({'rows':len(train),'valid_rows':len(valid),'maximum_tokens':max(lengths)}),flush=True)
    start=time.monotonic()
    train_model(SimpleNamespace(**config),model,train,valid)
    tensors=mx.load(str(out/'adapter/adapters.safetensors'))
    finite=bool(tensors) and all(bool(mx.all(mx.isfinite(t)).item()) for t in tensors.values())
    if not finite: raise ValueError('Nonfinite learned adapter.')
    receipt=dict(status='completed',training_steps=args.iters,elapsed_seconds=time.monotonic()-start,
        peak_memory_bytes=mx.get_peak_memory(),trainable_arrays=len(tensors),all_tensors_finite=finite,
        adapter_sha256=digest(out/'adapter/adapters.safetensors'),protocol_sha256=digest(out/'protocol.json'),
        training_rows=len(train),maximum_tokens=max(lengths),physical_qualification=False)
    (out/'training-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
