"""Temporary-file preflight assertions; never import/load an MLX model."""
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('am_prompt_cli_test', str(ROOT/'qwen-picogk-am'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def fixture(folder, final):
    runtime = folder/'runtime'; work = runtime/'am'; work.mkdir(parents=True)
    base = runtime/'model'; base.mkdir()
    for name in cli.BASE_NAMES: (base/name).write_bytes(('synthetic '+name).encode())
    save(base/'config.json', {'model_type':'qwen2'})
    base_hashes = {name: digest(base/name) for name in cli.BASE_NAMES}
    save(work/'base-manifest.json', {'model_files_sha256': base_hashes})
    adapter = work/'adapter'; adapter.mkdir()
    (adapter/'adapters.safetensors').write_bytes(b'not model weights')
    (adapter/'adapter_config.json').write_text('{}\n')
    receipt = dict(schema='picogk.am.final-qualification@1', status='qualified',
        base_weights_sha256=base_hashes['model.safetensors'],
        adapter_sha256=digest(adapter/'adapters.safetensors'),
        adapter_config_sha256=digest(adapter/'adapter_config.json'),
        final_passes=11, total=12, qualification='software and geometry only', manufacturing_authorized=False,
        checks={name: True for name in final.FINAL_CHECK_KEYS})
    save(work/'final-receipt.json', receipt)
    profile = dict(schema='picogk.am.qualified-profile@1', status='qualified', manufacturing_authorized=False,
        model_files_sha256=base_hashes, adapter='adapter', adapter_sha256=receipt['adapter_sha256'],
        adapter_config_sha256=receipt['adapter_config_sha256'], final_receipt='final-receipt.json',
        final_receipt_sha256=digest(work/'final-receipt.json'))
    save(work/'qualified-profile.json', profile)
    return work, runtime, profile, receipt


def explicit_fixture(folder, final):
    work, runtime, profile, receipt = fixture(folder, final)
    model = work/'model7b'; model.mkdir()
    for name in cli.BASE_NAMES: (model/name).write_bytes((runtime/'model'/name).read_bytes())
    save(work/'base.json', {'schema': 'picogk.am.base-profile@1', 'model_directory': 'model7b',
        'repository': 'synthetic/model', 'revision': 'a'*40,
        'model_files_sha256': profile['model_files_sha256']})
    profile.update(base_profile='base.json', base_profile_sha256=digest(work/'base.json'))
    receipt.update(base_profile_sha256=profile['base_profile_sha256'],
        model_files_sha256=profile['model_files_sha256'])
    save(work/'final-receipt.json', receipt)
    profile['final_receipt_sha256']=digest(work/'final-receipt.json')
    save(work/'qualified-profile.json', profile)
    return work, runtime, profile, receipt


def main():
    installed_hash=cli.TRUSTED_PROFILE_SHA256
    installed_profile=ROOT/'qualified-profile.json'
    installed_profile_hash=digest(installed_profile) if installed_profile.exists() else None
    spec = importlib.util.spec_from_file_location('am_prompt_test_final', ROOT/'final_qualification.py')
    final = importlib.util.module_from_spec(spec); spec.loader.exec_module(final)
    checked = 0
    mutations = {
        'missing-profile': lambda w,r,p,f: (w/'qualified-profile.json').unlink(),
        'profile-tamper': lambda w,r,p,f: (w/'qualified-profile.json').write_text('{}'),
        'tokenizer-tamper': lambda w,r,p,f: (r/'model/tokenizer_config.json').write_text('changed'),
        'tensor-tamper': lambda w,r,p,f: (w/'adapter/adapters.safetensors').write_bytes(b'changed'),
        'config-tamper': lambda w,r,p,f: (w/'adapter/adapter_config.json').write_text('changed'),
        'receipt-tamper': lambda w,r,p,f: (w/'final-receipt.json').write_text('{}'),
    }
    for name, mutate in mutations.items():
        with tempfile.TemporaryDirectory(prefix='am-cli-test-', dir=ROOT) as temp:
            work,runtime,profile,receipt = fixture(Path(temp), final)
            trusted = digest(work/'qualified-profile.json'); mutate(work,runtime,profile,receipt)
            try: cli.verify_profile(work,runtime,trusted)
            except (OSError,ValueError,KeyError,TypeError): checked += 1
            else: raise AssertionError('Accepted '+name)
    for change in ('old-schema','missing-base','extra-base','different-base','escape','symlink',
                   'wrong-model-receipt','incomplete-final-checks','final-not-qualified','duplicate-profile-field'):
        with tempfile.TemporaryDirectory(prefix='am-cli-test-', dir=ROOT) as temp:
            work,runtime,profile,receipt = fixture(Path(temp), final)
            if change == 'old-schema': profile['schema']='qwen.picogk.qualified-profile@1'
            if change == 'missing-base': profile['model_files_sha256'].pop('merges.txt')
            if change == 'extra-base': profile['model_files_sha256']['other.json']='a'*64
            if change == 'different-base': profile['model_files_sha256']['config.json']='b'*64
            if change == 'escape': profile['adapter']='../outside'
            if change == 'symlink':
                outside=Path(temp)/'outside'; outside.mkdir(); (work/'escape').symlink_to(outside,target_is_directory=True)
                profile['adapter']='escape'
            if change == 'wrong-model-receipt': receipt['adapter_config_sha256']='c'*64
            if change == 'incomplete-final-checks': receipt['checks'].pop(next(iter(receipt['checks'])))
            if change == 'final-not-qualified': receipt['status']='rejected'
            save(work/'final-receipt.json',receipt);profile['final_receipt_sha256']=digest(work/'final-receipt.json')
            save(work/'qualified-profile.json',profile)
            if change == 'duplicate-profile-field':
                text=(work/'qualified-profile.json').read_text();(work/'qualified-profile.json').write_text(text.rstrip()[:-1]+',"status":"qualified"}')
            trusted=digest(work/'qualified-profile.json')
            try: cli.verify_profile(work,runtime,trusted)
            except (OSError,ValueError,KeyError,TypeError): checked += 1
            else: raise AssertionError('Accepted '+change)
    with tempfile.TemporaryDirectory(prefix='am-cli-test-',dir=ROOT) as temp:
        work,runtime,profile,receipt=fixture(Path(temp),final)
        trusted=digest(work/'qualified-profile.json')
        assert cli.verify_profile(work,runtime,trusted)[1] == work/'adapter'; checked += 1
        old_root,old_runtime,old_hash,old_generation=cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256,cli.infer.run_generation
        calls=[]
        def capture(rows,output,adapter,task_hash,**kwargs):
            kwargs['preflight']();calls.append({'rows':rows,'hash':task_hash});output.mkdir()
            (output/'answer.txt').write_text('authored fake response; no model and no C# execution\n')
            return {'all_stopped':True,'status':'completed'}
        try:
            cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256=work,runtime,trusted
            cli.infer.run_generation=capture
            assert cli.main(['--prompt','Synthetic test','--output',str(work/'answer-1')]) == 0
            prompt_file=work/'prompt.txt';prompt_file.write_text('Multiline\nsynthetic prompt')
            assert cli.main(['--prompt-file',str(prompt_file),'--output',str(work/'answer-2')]) == 0
            assert len(calls)==2;checked += 2
            combined=cli.API_GUIDANCE+'\n\nUser request:\nSynthetic test'
            assert calls[0]=={'rows':[{'id':'answer','prompt':combined}],
                              'hash':hashlib.sha256(combined.encode()).hexdigest()};checked += 1
            cli.TRUSTED_PROFILE_SHA256=None
            try: cli.main(['--prompt','Synthetic test','--output',str(work/'refused')])
            except SystemExit as error: assert error.code==1
            else: raise AssertionError('Uninstalled profile reached generation')
            assert len(calls)==2 and not (work/'refused').exists();checked += 1
        finally:
            cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256=old_root,old_runtime,old_hash
            cli.infer.run_generation=old_generation
        old_root=cli.infer.ROOT;cli.infer.ROOT=work
        try:
            with (runtime/'train.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                try: cli.infer.run_generation([{'id':'answer','prompt':'x'}],work/'blocked',work/'adapter','d'*64)
                except BlockingIOError: checked += 1
                else: raise AssertionError('GPU lock contention did not stop before MLX imports')
            assert not (work/'blocked').exists()
        finally: cli.infer.ROOT=old_root
    for change in ('base-profile-hash', 'null-profile-hash', 'receipt-profile', 'receipt-files', 'unpaired-profile', 'profile-escape'):
        with tempfile.TemporaryDirectory(prefix='am-cli-test-',dir=ROOT) as temp:
            work,runtime,profile,receipt=explicit_fixture(Path(temp),final)
            if change=='base-profile-hash': profile['base_profile_sha256']='f'*64
            if change=='null-profile-hash': profile['base_profile_sha256']=None
            if change=='receipt-profile': receipt['base_profile_sha256']='f'*64
            if change=='receipt-files': receipt['model_files_sha256']=dict(receipt['model_files_sha256'], config_json='a'*64)
            if change=='unpaired-profile': profile.pop('base_profile_sha256')
            if change=='profile-escape': profile['base_profile']='../outside.json'
            save(work/'final-receipt.json',receipt);profile['final_receipt_sha256']=digest(work/'final-receipt.json')
            save(work/'qualified-profile.json',profile)
            try: cli.verify_profile(work,runtime,digest(work/'qualified-profile.json'))
            except (OSError,ValueError,KeyError,TypeError): checked+=1
            else: raise AssertionError('Invalid explicit serving profile accepted: '+change)
    with tempfile.TemporaryDirectory(prefix='am-cli-test-',dir=ROOT) as temp:
        work,runtime,profile,receipt=explicit_fixture(Path(temp),final)
        trusted=digest(work/'qualified-profile.json')
        assert cli.verify_profile(work,runtime,trusted)[1]==work/'adapter';checked+=1
        old_root,old_runtime,old_hash,old_generation=cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256,cli.infer.run_generation
        calls=[]
        def capture_explicit(rows,output,adapter,task_hash,**kwargs):
            kwargs['preflight']()
            calls.append((rows,task_hash,kwargs['base_profile']))
            output.mkdir();(output/'answer.txt').write_text('synthetic response')
            return {'all_stopped':True,'status':'completed'}
        try:
            cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256=work,runtime,trusted
            cli.infer.run_generation=capture_explicit
            assert cli.main(['--prompt','Synthetic profile test','--output',str(work/'answer')])==0
            combined=cli.API_GUIDANCE+'\n\nUser request:\nSynthetic profile test'
            assert calls==[([{'id':'answer','prompt':combined}],hashlib.sha256(combined.encode()).hexdigest(),work/'base.json')];checked+=1
        finally:
            cli.ROOT,cli.RUNTIME,cli.TRUSTED_PROFILE_SHA256=old_root,old_runtime,old_hash
            cli.infer.run_generation=old_generation
    assert cli.TRUSTED_PROFILE_SHA256==installed_hash
    assert (digest(installed_profile) if installed_profile.exists() else None)==installed_profile_hash
    print(json.dumps({'status':'preflight_assertions_passed','checks':checked,'model_loaded':False,'geometry_executed':False}))


if __name__ == '__main__': main()
