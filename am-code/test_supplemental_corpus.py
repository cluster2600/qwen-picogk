"""Assert supplemental corpus boundaries with temporary JSONL; no MLX/model calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('am_supplemental_train',ROOT/'train.py')
train=importlib.util.module_from_spec(spec);spec.loader.exec_module(train)


def main():
    checks=0
    assert train.supplemental_corpus(None,None)==(None,0);checks+=1
    assert train.resume_adapter(None) is None;checks+=1
    with tempfile.TemporaryDirectory(prefix='am-corpus-test-',dir=ROOT) as temp:
        path=Path(temp)/'train.jsonl'
        valid={'messages':[{'role':'user','content':'Synthetic request'},
                           {'role':'assistant','content':'Complete synthetic answer'}]}
        payload=(json.dumps(valid,ensure_ascii=False)+'\n').encode()
        path.write_bytes(payload);expected=hashlib.sha256(payload).hexdigest()
        weights=Path(temp)/'adapters.safetensors';weights.write_bytes(b'synthetic adapter bytes')
        assert train.resume_adapter(weights)==hashlib.sha256(weights.read_bytes()).hexdigest();checks+=1
        for invalid_resume in (Path(temp)/'missing.safetensors',Path(temp)):
            try:train.resume_adapter(invalid_resume)
            except ValueError:checks+=1
            else:raise AssertionError('Accepted missing/nonfile resume adapter')
        data,rows=train.supplemental_corpus(path,expected)
        assert data==payload and rows==1;checks+=1
        for source,sha in ((path,None),(None,expected),(path,'bad-hash')):
            try:train.supplemental_corpus(source,sha)
            except ValueError:checks+=1
            else:raise AssertionError('Accepted unpaired arguments or incorrect SHA')
        invalid=[{'text':'legacy text'}, {'messages':[]}, {'messages':valid['messages'][:1]},
                 {'messages':[valid['messages'][0],{'role':'assistant','content':'  '}]},
                 {'messages':[{'role':'system','content':'not requested'},valid['messages'][1]]},
                 {'messages':[valid['messages'][0],{'role':'assistant','content':None}]},
                 {'messages':valid['messages'],'extra':1}]
        for row in invalid:
            bad=(json.dumps(row)+'\n').encode();path.write_bytes(bad)
            try:train.supplemental_corpus(path,hashlib.sha256(bad).hexdigest())
            except ValueError:checks+=1
            else:raise AssertionError('Accepted incomplete/non-chat row')
        for bad in (b'',b'not-json\n',payload+b'\n'):
            path.write_bytes(bad)
            try:train.supplemental_corpus(path,hashlib.sha256(bad).hexdigest())
            except ValueError:checks+=1
            else:raise AssertionError('Accepted malformed/empty JSONL')
        path.write_bytes(payload)
        for flags in (['--corpus',str(path)],['--corpus-sha256',expected],
                      ['--corpus',str(path),'--corpus-sha256','wrong'],
                      ['--resume',str(Path(temp)/'missing.safetensors')],['--resume',str(Path(temp))]):
            run='preflight-'+hashlib.sha256(' '.join(flags).encode()).hexdigest()[:12]
            result=subprocess.run([sys.executable,str(ROOT/'train.py'),'--name',run,'--iters','1',*flags],
                                  capture_output=True,text=True)
            assert result.returncode==2 and not (ROOT/'runs'/run).exists();checks+=1
    print(json.dumps({'status':'supplemental_corpus_assertions_passed','checks':checks,
                      'model_loaded':False,'training_started':False}))


if __name__=='__main__':main()
