"""Verify installed mask and loader behavior without querying model answers."""
from pathlib import Path
from datetime import datetime, timezone
import fcntl, hashlib, json, os
import numpy as np
from safetensors.numpy import load_file
ROOT=Path(__file__).resolve().parent.parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',TOKENIZERS_PARALLELISM='false')
    with (ROOT.parent/'train.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        import mlx.core as mx
        from mlx.utils import tree_flatten
        from mlx_lm import load
        from mlx_lm.tuner.datasets import ChatDataset
        from mlx_lm.tuner.trainer import default_loss,iterate_batches,CacheDataset
        import mlx_lm.tuner.datasets as datasets
        import mlx_lm.tuner.trainer as trainer
        import mlx_lm.tuner.utils as utilities
        mx.set_memory_limit(36*1024**3);mx.set_cache_limit(512*1024**2)
        model,tok=load(str(ROOT/'model32b'),adapter_path=str(ROOT/'runs/32b-corrective007-recovery1/adapter'),tokenizer_config={'trust_remote_code':False})
        expected=load_file(str(ROOT/'runs/32b-corrective007-recovery1/adapter/adapters.safetensors'))
        loaded={k:v for k,v in tree_flatten(model.parameters()) if k.endswith(('.lora_a','.lora_b'))}
        assert set(loaded)==set(expected) and len(loaded)==224
        for k,v in loaded.items():assert np.array_equal(np.array(v),expected[k])
        scales=[m.scale for _,m in model.named_modules() if type(m).__name__=='LoRALinear']
        assert len(scales)==112 and set(scales)=={20.0}
        rows=[json.loads(x) for x in (ROOT/'data/focused-32b-002/train.jsonl').read_text().splitlines()]
        stored=json.loads((ROOT/'data/focused-32b-002/token-rows.json').read_text())
        data=ChatDataset(rows,tok,mask_prompt=True)
        for row,meta in zip(rows,stored):
            ids,offset=data.process(row)
            prefix=tok.apply_chat_template(row['messages'][:-1],add_generation_prompt=True,return_dict=False)
            assert offset==meta['prompt_mask_offset']==len(prefix) and ids[:offset]==prefix
            assert len(ids)==meta['full_tokens']<=6144 and tok.decode(ids).endswith('<|im_end|>\n')
        # Compare the actual installed loss and gradient mask to an independent numeric reference.
        batch=mx.array([[1,2,3,4,5,0,0,0],[2,3,4,5,6,7,0,0]],mx.int32)
        lengths=mx.array([[3,5],[2,6]],mx.int32)
        logits=mx.arange(2*7*16,dtype=mx.float32).reshape(2,7,16)/100
        loss,count=default_loss(lambda _:logits,batch,lengths)
        gradient=mx.grad(lambda x:default_loss(lambda _:x,batch,lengths)[0])(logits)
        array=np.array(logits);targets=np.array(batch)[:,1:];steps=np.arange(1,8)
        mask=(steps[None,:]>=np.array(lengths)[:,0:1])&(steps[None,:]<=np.array(lengths)[:,1:])
        maximum=array.max(axis=-1,keepdims=True)
        logz=np.log(np.exp(array-maximum).sum(axis=-1))+maximum[:,:,0]
        ce=logz-np.take_along_axis(array,targets[:,:,None],axis=-1)[:,:,0]
        assert int(count)==int(mask.sum()) and np.isclose(float(loss),ce[mask].mean(),rtol=1e-5)
        assert np.all(np.array(gradient)[~mask]==0) and np.any(np.array(gradient)[mask]!=0)
        counted=0;assistant=0;extra_labels=[]
        for batch,lengths in iterate_batches(CacheDataset(data),1,6144,loop=False,seed=9931414):
            a=np.array(batch);offset,end=np.array(lengths)[0]
            steps=np.arange(1,a.shape[1]);active=(steps>=offset)&(steps<=end)
            counted+=int(active.sum());assistant+=int(end-offset)
            assert active[end-1] and a[0,end]==0
            extra_labels.append(int(a[0,end]))
        assert counted-assistant==len(rows)==384 and assistant==sum(x['assistant_tokens'] for x in stored)
        result=dict(schema='picogk.am.installed-runtime-diagnostic@1',status='passed',created_at=datetime.now(timezone.utc).isoformat(),
            loaded_adapter_arrays_exact=224,loaded_lora_modules=112,lora_scale=20,actual_chat_rows_verified=384,
            actual_prompt_masks_match=True,actual_eos_retained=True,loss_and_gradient_mask_matches_installed_definition=True,
            assistant_target_tokens=assistant,actual_loss_target_tokens=counted,extra_zero_padding_targets=counted-assistant,
            padding_fraction=(counted-assistant)/counted,
            padding_observation='Installed iterate_batches pads beyond each sequence; default_loss includes one zero padding label after the sequence. Preserved unchanged; small fraction is not a demonstrated cause of qualification failure.',
            dependencies_sha256={Path(x.__file__).name:sha(Path(x.__file__)) for x in (datasets,trainer,utilities)},
            adapter_sha256=sha(ROOT/'runs/32b-corrective007-recovery1/adapter/adapters.safetensors'),
            corpus_sha256=sha(ROOT/'data/focused-32b-002/train.jsonl'),source_sha256=sha(Path(__file__)),
            inference_answers_generated=0,checker_or_training_sources_modified=False,final_contents_read=False,
            peak_memory_bytes=mx.get_peak_memory(),manufacturing_authorized=False)
        with (ROOT/'course012-runtime-diagnostic.json').open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()
