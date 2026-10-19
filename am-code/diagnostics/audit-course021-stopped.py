"""CPU-only immutable audit of the user-stopped, ineligible course021."""
from pathlib import Path
from datetime import datetime,timezone
import fcntl,hashlib,json,re,subprocess
import numpy as np
from safetensors.numpy import load_file
ROOT=Path(__file__).resolve().parent.parent
RUN=ROOT/'runs/32b-semantic014-rate5-continuation1'
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
 with (ROOT.parent/'train.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  checks={};bindings={}
  def check(k,v):
   checks[k]=bool(v)
   if not v:raise ValueError(k)
  def bind(n,h=None):
   actual=digest(ROOT/n);bindings[n]=actual
   if h:check('hash:'+n,actual==h)
   return actual
  p=read(ROOT/'course-021-protocol.json');runtime=read(RUN/'protocol.json');config=read(RUN/'adapter/adapter_config.json')
  check('training_process_exited',subprocess.run(['ps','-p','80855','-o','command='],capture_output=True,text=True).returncode!=0)
  check('no_matching_training_process',not any('train.py --name 32b-semantic014-rate5-continuation1' in line for line in subprocess.check_output(['ps','-axo','command='],text=True).splitlines()))
  check('no_completion_receipt',not(RUN/'training-receipt.json').exists())
  check('parent_lock_free',True)
  bind('course-021-protocol.json','e006d93fabcc43496dc06bbb02ee98c111c50d49b97e91b5fac9202fb0b01c11')
  bind(str((RUN/'protocol.json').relative_to(ROOT)),'66879110f8a8bb1e5d904ac50c3e9359b201e5091529b4d02710f78920197554')
  bind('course020-cpu-audit.json','e9f9f2637ef415ebc6596a76691d6b0b45bfa6233cab82dec88a48b640157c4e')
  check('parent_audit_passed',all(read(ROOT/'course020-cpu-audit.json')['checks'].values()))
  parent=ROOT/p['parent_adapter'];bind(p['parent_adapter'],'6d1297c2758022d4d471d0125c5595fafe91239efab3529bb1f6a9587987f4d0')
  check('exact_parent_binding',p['parent_adapter_sha256']==runtime['resume_adapter_sha256']==digest(parent))
  receipt=parent.parent.parent/'training-receipt.json';check('completed020_parent',read(receipt)['status']=='completed' and read(receipt)['adapter_sha256']==digest(parent));bind(str(receipt.relative_to(ROOT)))
  for k,expected in dict(iters=272,learning_rate=5e-6,seed=9931414,num_layers=16,batch_size=1,max_seq_length=6144,mask_prompt=True,grad_checkpoint=True).items():check('config:'+k,runtime['config'][k]==config[k]==expected)
  check('lora_config',config['lora_parameters']==dict(rank=8,scale=20.,dropout=0.))
  check('full_pass_plan',p['iterations']==p['training_rows']==272 and p['epochs']==1 and p['new_teacher_cases']==p['new_formulations']==0)
  for n,h in p['historical_corpora_preserved_sha256'].items():bind(n,h)
  bind(p['corpus'],p['corpus_sha256']);check('runtime_corpus',runtime['corpus_sha256']==p['corpus_sha256']);bind(str((RUN/'data/train.jsonl').relative_to(ROOT)),p['corpus_sha256'])
  bind('data/train.jsonl','ed3247fb4c8ecacc013eb95f16fb6ac6d822680e40d32ae95cafb130893108d7');bind('data/train-chat.jsonl','1ac93688653ea7aa26b1e93b739eaac21717e11af4f9996972b6735bb20fe684')
  for key,n in [('train_source_sha256','train.py'),('infer_source_sha256','infer_v2.py'),('base_runtime_source_sha256','base_runtime.py'),('checker_profile_sha256','checker-profile-v2.json'),('base_profile_sha256','base-profile-32b.json')]:bind(n,p[key])
  profile=read(ROOT/'base-profile-32b.json')
  for n,h in profile['model_files_sha256'].items():bind('model32b/'+n,h)
  for n in ['course021-launch-receipt.json','course021-launch-verification.json','course021-protocol-addendum-001.json','diagnostics/course021-optimization-decision.json',str((RUN/'adapter/adapter_config.json').relative_to(ROOT))]:bind(n)
  text=(ROOT/'training-32b-semantic014-rate5-continuation1.log').read_text();steps=[int(x) for x in re.findall(r'Iter (\d+):',text)];last=max(steps)
  check('logged_before_planned_completion',last==120<272);bind('training-32b-semantic014-rate5-continuation1.log')
  dims={'self_attn.q_proj':(5120,5120),'self_attn.k_proj':(5120,1024),'self_attn.v_proj':(5120,1024),'self_attn.o_proj':(5120,5120),'mlp.gate_proj':(5120,27648),'mlp.up_proj':(5120,27648),'mlp.down_proj':(27648,5120)}
  shapes={}
  for layer in range(48,64):
   for mod,(i,o) in dims.items():
    shapes[f'model.layers.{layer}.{mod}.lora_a']=(i,8);shapes[f'model.layers.{layer}.{mod}.lora_b']=(8,o)
  tensorfiles=sorted((RUN/'adapter').glob('*.safetensors'));check('two_durable_plus_latest',len(tensorfiles)==3)
  for f in tensorfiles:
   arr=load_file(str(f));check('exact_keys_shapes:'+f.name,{k:v.shape for k,v in arr.items()}==shapes);check('finite_fp32:'+f.name,all(v.dtype==np.float32 and np.isfinite(v).all() for v in arr.values()));bind(str(f.relative_to(ROOT)))
  latest=RUN/'adapter/adapters.safetensors';durable=RUN/'adapter/0000120_adapters.safetensors';check('latest_exact_durable120',digest(latest)==digest(durable))
  bind(str(Path(__file__).relative_to(ROOT)))
  result=dict(schema='picogk.am.interrupted-course-cpu-audit@1',status='passed',created_at_utc=datetime.now(timezone.utc).isoformat(),run=p['course'],course='021',training_status='interrupted_ineligible',cause='User explicitly requested stop; SIGTERM sent to verified PID80855 and process exit/lock release observed. No infrastructure fault inferred.',last_logged_step=last,latest_durable_checkpoint_step=120,planned_steps=272,training_rows=272,completed_receipt_exists=False,checks=checks,files_sha256=bindings,latest_adapter_sha256=digest(latest),trainable_arrays=224,exact_tensor_files=3,checkpoint_evaluated=False,qualification_credit=0,recovery_authorized=False,automation_status='PAUSED',gpu_used=False,mlx_imported=False,final_contents_read=False,manufacturing_authorized=False)
  with (ROOT/'course021-stopped-cpu-audit.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
  print(json.dumps(dict(status='passed',checks=len(checks),audit_sha256=digest(ROOT/'course021-stopped-cpu-audit.json'),latest_adapter_sha256=result['latest_adapter_sha256'])))
if __name__=='__main__':main()
