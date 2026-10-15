"""Assert base identity and guarded final access using synthetic bytes, never MLX."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('am_base_identity_test', ROOT / 'base_runtime.py')
base_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_runtime)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def fixture(folder):
    runtime = folder / 'runtime'
    work = runtime / 'am'
    work.mkdir(parents=True)
    for directory in (runtime / 'model', work / 'model7b'):
        directory.mkdir()
        for name in base_runtime.BASE_NAMES:
            (directory / name).write_bytes(('synthetic ' + directory.name + ' ' + name).encode())
        save(directory / 'config.json', {'model_type': 'qwen2'})
    hashes = {name: base_runtime.digest(runtime / 'model' / name) for name in base_runtime.BASE_NAMES}
    save(work / 'base-manifest.json', {'model_files_sha256': hashes})
    profile = {'schema': 'picogk.am.base-profile@1', 'repository': 'synthetic/model',
               'revision': 'a' * 40, 'model_directory': 'model7b',
               'model_files_sha256': {name: base_runtime.digest(work / 'model7b' / name) for name in base_runtime.BASE_NAMES}}
    save(work / 'base.json', profile)
    return runtime, work, profile


def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix='am-base-test-', dir=ROOT) as temp:
        runtime, work, profile = fixture(Path(temp))
        legacy = base_runtime.verify_base(work)
        assert legacy['directory'] == runtime / 'model' and legacy['binding'] == {}; checks += 1
        explicit = base_runtime.verify_base(work, Path('base.json'))
        assert explicit['directory'] == work / 'model7b'
        assert explicit['binding'] == {'base_profile_sha256': base_runtime.digest(work / 'base.json'),
                                       'model_files_sha256': profile['model_files_sha256']}; checks += 1
        assert base_runtime.verify_base(work, work / 'base.json', expected_profile_sha256=explicit['binding']['base_profile_sha256']) == explicit; checks += 1
        old_record = {'base_weights_sha256': legacy['base_weights_sha256']}
        new_record = {'base_weights_sha256': explicit['base_weights_sha256'], **explicit['binding']}
        base_runtime.verify_evidence(legacy, old_record)
        base_runtime.verify_evidence(explicit, new_record, new_record); checks += 2
        save(work / 'same-base.json', profile)
        with (work / 'same-base.json').open('a') as stream: stream.write('\n')
        same_weights = base_runtime.verify_base(work, work / 'same-base.json')
        assert same_weights['base_weights_sha256'] == explicit['base_weights_sha256']; checks += 1
        for base, record in ((legacy, new_record), (explicit, old_record), (same_weights, new_record),
                             (explicit, dict(new_record, base_profile_sha256='b' * 64)),
                             (explicit, {key: value for key, value in new_record.items() if key != 'model_files_sha256'}),
                             (legacy, dict(old_record, base_profile_sha256=None))):
            try: base_runtime.verify_evidence(base, record)
            except ValueError: checks += 1
            else: raise AssertionError('Mixed or incomplete profile evidence accepted.')
        try: base_runtime.verify_base(work, work / 'base.json', expected_profile_sha256='f' * 64)
        except ValueError: checks += 1
        else: raise AssertionError('Incorrect trusted profile hash accepted.')

    for variant in ('hash', 'missing', 'extra', 'schema', 'revision', 'relative-escape',
                    'absolute-directory', 'directory-symlink', 'file-symlink', 'extra-shard', 'duplicate', 'custom-code'):
        with tempfile.TemporaryDirectory(prefix='am-base-test-', dir=ROOT) as temp:
            runtime, work, profile = fixture(Path(temp))
            if variant == 'hash': profile['model_files_sha256']['config.json'] = 'b' * 64
            if variant == 'missing': profile['model_files_sha256'].pop('merges.txt')
            if variant == 'extra': profile['model_files_sha256']['other.json'] = 'a' * 64
            if variant == 'schema': profile['schema'] = 'old'
            if variant == 'revision': profile['revision'] = 'unpinned'
            if variant == 'relative-escape': profile['model_directory'] = '../model'
            if variant == 'absolute-directory': profile['model_directory'] = str(work / 'model7b')
            if variant == 'directory-symlink':
                (work / 'escape').symlink_to(runtime / 'model', target_is_directory=True)
                profile['model_directory'] = 'escape'
            if variant == 'file-symlink':
                (work / 'model7b/config.json').unlink()
                (work / 'model7b/config.json').symlink_to(runtime / 'model/config.json')
            if variant == 'extra-shard': (work / 'model7b/model-extra.safetensors').write_bytes(b'unpinned')
            if variant == 'custom-code':
                save(work / 'model7b/config.json', {'model_type': 'qwen2', 'model_file': 'untrusted.py'})
                profile['model_files_sha256']['config.json'] = base_runtime.digest(work / 'model7b/config.json')
            save(work / 'base.json', profile)
            if variant == 'duplicate':
                value = (work / 'base.json').read_text().rstrip()[:-1] + ',"revision":"' + 'a' * 40 + '"}'
                (work / 'base.json').write_text(value)
            try: base_runtime.verify_base(work, work / 'base.json')
            except (OSError, ValueError, KeyError, TypeError): checks += 1
            else: raise AssertionError('Invalid base accepted: ' + variant)

    infer = load('am_base_test_infer', 'infer.py')
    final = load('am_base_test_final', 'final_qualification.py')
    with tempfile.TemporaryDirectory(prefix='am-base-test-', dir=ROOT) as temp:
        runtime, work, profile = fixture(Path(temp))
        calls = []
        # Substitute tiny modules before the function imports MLX; no native runtime is imported.
        fake_mlx = ModuleType('mlx'); core = ModuleType('mlx.core')
        core.set_memory_limit=lambda value:calls.append(('memory',value))
        core.set_cache_limit=lambda value:calls.append(('cache',value))
        core.random=SimpleNamespace(seed=lambda value:calls.append(('seed',value)))
        core.get_peak_memory=lambda:0;fake_mlx.core=core
        lm=ModuleType('mlx_lm');samples=ModuleType('mlx_lm.sample_utils')
        tokenizer=SimpleNamespace(add_eos_token=lambda value:calls.append(('eos',value)),
            apply_chat_template=lambda messages,**kwargs:(calls.append(('messages',messages,kwargs)) or 'synthetic-template'))
        def mocked_load(directory,**kwargs):
            calls.append(('load',directory,kwargs));return object(),tokenizer
        def mocked_generate(model,tok,**kwargs):
            calls.append(('generate',kwargs))
            return iter([SimpleNamespace(text='complete fake answer',finish_reason='stop',generation_tokens=3)])
        lm.load=mocked_load;lm.stream_generate=mocked_generate
        samples.make_sampler=lambda **kwargs:(calls.append(('sampler',kwargs)) or 'fake-sampler')
        with patch.object(infer,'ROOT',work), patch.dict(sys.modules,
                {'mlx':fake_mlx,'mlx.core':core,'mlx_lm':lm,'mlx_lm.sample_utils':samples}):
            rows=[{'id':'answer','prompt':'Synthetic unchanged prompt'}]
            with contextlib.redirect_stdout(io.StringIO()):
                infer.run_generation(rows,work/'legacy-capture',None,'e'*64)
            protocol=json.loads((work/'legacy-capture/protocol.json').read_text())
            assert not base_runtime.BINDING_KEYS.intersection(protocol);checks+=1
            assert ('load',str(runtime/'model'),{'adapter_path':None,'tokenizer_config':{'trust_remote_code':False}}) in calls;checks+=1
            assert ('memory',36*1024**3) in calls and ('cache',512*1024**2) in calls and ('seed',9931414) in calls
            assert ('eos','<|im_end|>') in calls and ('sampler',{'temp':0}) in calls
            assert ('messages',[{'role':'user','content':rows[0]['prompt']}],{'tokenize':False,'add_generation_prompt':True}) in calls
            assert next(call[1] for call in calls if call[0]=='generate')=={'prompt':'synthetic-template','max_tokens':6144,'sampler':'fake-sampler'};checks+=1
            calls.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                infer.run_generation(rows,work/'explicit-capture',None,'e'*64,base_profile=work/'base.json')
            protocol=json.loads((work/'explicit-capture/protocol.json').read_text())
            base=base_runtime.verify_base(work,work/'base.json')
            base_runtime.verify_evidence(base,protocol);checks+=1
            assert ('load',str(work/'model7b'),{'adapter_path':None,'tokenizer_config':{'trust_remote_code':False}}) in calls;checks+=1
            assert (work/'legacy-capture/answer.txt').read_bytes()==(work/'explicit-capture/answer.txt').read_bytes();checks+=1
    with tempfile.TemporaryDirectory(prefix='am-base-test-', dir=ROOT) as temp:
        runtime, work, profile = fixture(Path(temp))
        # These are explicitly authored test files, never real reserved cases.
        fake_final = work / 'evaluation/final.json'
        fake_final.parent.mkdir()
        fake_final.write_text('FORBIDDEN FAKE FINAL CONTENT')
        with patch.object(base_runtime, 'digest') as mocked_digest:
            try: base_runtime.verify_base(work, fake_final)
            except ValueError: assert not mocked_digest.called; checks += 1
            else: raise AssertionError('Reserved final file used as a base profile.')
        outside = runtime / 'outside-profile.json'; save(outside, profile)
        try: base_runtime.verify_base(work, outside)
        except ValueError: checks += 1
        else: raise AssertionError('Profile outside AM root accepted.')
        base = base_runtime.verify_base(work, work / 'base.json')
        selection = {'schema': 'picogk.am.development-selection@1', 'status': 'selected_for_final_evaluation',
            'development_passes': 12, 'scan_passes': 4, 'required_safety_passed': True,
            'checks': dict.fromkeys(infer.qualification.QUALIFICATION_CHECK_KEYS, True),
            'base_weights_sha256': base['base_weights_sha256'], **base['binding'],
            'adapter_sha256': 'c' * 64, 'adapter_config_sha256': 'd' * 64,
            'qualification': 'software and geometry only', 'manufacturing_authorized': False}
        selection['base_profile_sha256'] = 'f' * 64
        selection_path = work / 'selection.json'; save(selection_path, selection)
        adapter = work / 'adapter'; adapter.mkdir()
        for name in ('adapters.safetensors', 'adapter_config.json'): (adapter / name).write_text('synthetic')
        def infer_digest(path):
            assert path != fake_final, 'Final hashed before selected profile validation.'
            return 'c' * 64 if path.name == 'adapters.safetensors' else 'd' * 64
        argv = ['infer.py', '--tasks', str(fake_final), '--output', str(work / 'capture'),
                '--adapter', str(adapter), '--selection-receipt', str(selection_path), '--base-profile', str(work / 'base.json')]
        with patch.object(infer, 'ROOT', work), patch.object(sys, 'argv', argv), \
                patch.object(infer, 'digest', side_effect=infer_digest), \
                patch.object(infer, 'run_generation') as generation:
            try: infer.main()
            except ValueError: assert not generation.called and not (work / 'capture').exists(); checks += 1
            else: raise AssertionError('Wrong selected profile reached final inference.')
        argv[argv.index('--selection-receipt') + 1] = str(fake_final)
        with patch.object(infer, 'ROOT', work), patch.object(sys, 'argv', argv), \
                patch.object(infer, 'run_generation') as generation:
            try: infer.main()
            except ValueError: assert not generation.called; checks += 1
            else: raise AssertionError('Reserved selection alias accepted.')
        argv = ['final_qualification.py', '--selection-receipt', str(selection_path),
                '--final-score', str(work / 'score.json'), '--final-responses', str(work / 'responses.json'),
                '--adapter', str(adapter), '--output', str(work / 'qualified.json'), '--base-profile', str(work / 'base.json')]
        with patch.object(final, 'ROOT', work), patch.object(sys, 'argv', argv), \
                patch.object(final.qualification, 'digest', side_effect=lambda p: infer_digest(p)), \
                contextlib.redirect_stdout(io.StringIO()):
            assert final.main() == 1 and not (work / 'qualified.json').exists(); checks += 1
    print(json.dumps({'status': 'base_identity_assertions_passed', 'checks': checks,
                      'model_loaded': False, 'real_final_tasks_read': False}))


if __name__ == '__main__':
    main()
