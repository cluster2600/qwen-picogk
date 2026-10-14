#!/usr/bin/env python3
"""Capture deterministic model responses for an explicitly selected frozen task file."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('am_qualification',ROOT/'qualification.py')
qualification=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)
base_runtime=qualification.base_runtime
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run_generation(rows, output, adapter, task_hash, selection_hash=None, max_tokens=6144,
                   api_card=None, preflight=None, base_profile=None):
    """Capture text only; verify serving bindings while holding the shared GPU lock."""
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
        HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2')
    with (ROOT.parent/'train.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if preflight is not None: preflight()
        base=base_runtime.verify_base(ROOT,base_profile)
        output.mkdir(parents=True,exist_ok=True)
        import mlx.core as mx
        from mlx_lm import load,stream_generate
        from mlx_lm.sample_utils import make_sampler
        mx.set_memory_limit(36*1024**3);mx.set_cache_limit(512*1024**2)
        mx.random.seed(9931414)
        protocol=dict(started_at=datetime.now(timezone.utc).isoformat(),tasks_sha256=task_hash,
            adapter_sha256=digest(adapter/'adapters.safetensors') if adapter else None,
            adapter_config_sha256=digest(adapter/'adapter_config.json') if adapter else None,
            base_weights_sha256=base['base_weights_sha256'],max_tokens=max_tokens,
            temperature=0,task_ids=[r['id'] for r in rows],selection_receipt_sha256=selection_hash)
        protocol.update(base['binding'])
        (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
        model,tok=load(str(base['directory']),adapter_path=str(adapter) if adapter else None,
            tokenizer_config={'trust_remote_code':False})
        tok.add_eos_token('<|im_end|>')
        results=[]
        for row in rows:
            messages=[{'role':'user','content':row['prompt']}]
            if api_card: messages.insert(0,{'role':'system','content':api_card})
            prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            started=time.monotonic();response='';last=None
            for last in stream_generate(model,tok,prompt=prompt,max_tokens=max_tokens,sampler=make_sampler(temp=0)):
                response+=last.text
            if last is None:raise ValueError('Empty generation stream.')
            (output/(row['id']+'.txt')).write_text(response)
            results.append(dict(id=row['id'],response=response,finish_reason=last.finish_reason,
                tokens=last.generation_tokens,elapsed_seconds=time.monotonic()-started))
            (output/'responses.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({k:results[-1][k] for k in ('id','finish_reason','tokens','elapsed_seconds')}),flush=True)
        receipt=dict(status='completed',count=len(results),protocol_sha256=digest(output/'protocol.json'),
            responses_sha256=digest(output/'responses.json'),
            all_stopped=all(r['finish_reason']=='stop' for r in results),peak_memory_bytes=mx.get_peak_memory())
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--adapter',type=Path)
    parser.add_argument('--ids')
    parser.add_argument('--max-tokens',type=int,default=6144)
    parser.add_argument('--selection-receipt',type=Path)
    parser.add_argument('--base-profile',type=Path)
    a=parser.parse_args()
    base=base_runtime.verify_base(ROOT,a.base_profile)
    selection_hash=None
    if a.tasks.resolve()==(ROOT/'evaluation/final.json').resolve():
        if not a.selection_receipt or not a.adapter: raise ValueError('Final inference requires selected candidate evidence.')
        if base_runtime.reserved(ROOT,a.selection_receipt):
            raise ValueError('Selection metadata cannot alias reserved final inputs.')
        selection=json.loads(a.selection_receipt.read_text())
        checks=selection.get('checks',{})
        if (selection.get('schema')!='picogk.am.development-selection@1'
            or selection.get('status')!='selected_for_final_evaluation'
            or selection.get('development_passes',0)<11 or selection.get('required_safety_passed') is not True
            or not qualification.complete_checks(checks)):
            raise ValueError('Development selection evidence is incomplete.')
        for key,path in (('adapter_sha256',a.adapter/'adapters.safetensors'),
                         ('adapter_config_sha256',a.adapter/'adapter_config.json')):
            if digest(path)!=selection.get(key): raise ValueError('Final inference model differs from selected model: '+key)
        base_runtime.verify_evidence(base,selection)
        frozen=json.loads((ROOT/'evaluation/freeze.json').read_text())
        if digest(a.tasks)!=frozen['files']['final.json']: raise ValueError('Reserved final task file changed.')
        selection_hash=digest(a.selection_receipt)
    if a.output.exists():raise FileExistsError('Preserve existing inference evidence.')
    a.output.mkdir(parents=True)
    taskfile=json.loads(a.tasks.read_text())
    rows=taskfile['tasks']
    if a.ids:
        selected=set(a.ids.split(','));rows=[r for r in rows if r['id'] in selected]
        if len(rows)!=len(selected):raise ValueError('Unknown task ID.')
    if not rows:raise ValueError('Empty inference batch.')
    run_generation(rows,a.output,a.adapter,digest(a.tasks),selection_hash,a.max_tokens,taskfile.get('api_card'),
        base_profile=a.base_profile,
        preflight=(lambda: base_runtime.verify_evidence(base_runtime.verify_base(ROOT,a.base_profile),selection))
            if selection_hash is not None else None)

if __name__=='__main__':main()
