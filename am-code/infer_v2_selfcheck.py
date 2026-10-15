#!/usr/bin/env python3
"""Synthetic inference-gate checks; never read reserved data or import MLX."""
import ast
import builtins
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('synthetic_infer_v2_check', ROOT/'infer_v2.py')
infer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(infer)
H = {name: hashlib.sha256(name.encode()).hexdigest() for name in
     ('checker','other','adapter','config','base','development','scan','scan-freeze',
      'qualification-source','gate-source','task','selection','profile','model-file')}
PASSED = []


def fails(call, fragment):
    try:
        call()
    except ValueError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError('Expected failure: '+fragment)


def scenario(name, *, selection_mutation=None, missing=False, alias=False,
             bad_adapter=False, profile_failure=False, valid=False,
             tasks_alias=False, profile_alias=False):
    """Exercise the real CLI/selection validator with synthetic reads and hashes."""
    with tempfile.TemporaryDirectory(prefix='infer-v2-check-') as temp:
        work = Path(temp)/'work';work.mkdir()
        tasks = work/'evaluation/final.json'
        selected_path = work/'selection.json'
        supplied_tasks = tasks
        supplied_profile = work/'profile.json'
        adapter = work/'adapter'
        output = work/'capture'
        base = {'directory':work/'synthetic-model', 'base_weights_sha256':H['base'],
                'binding':{'base_profile_sha256':H['profile'],
                           'model_files_sha256':{'synthetic':H['model-file']}}}
        current = {'adapter_sha256':H['adapter'], 'adapter_config_sha256':H['config'],
                   'base_weights_sha256':H['base'], 'development_task_sha256':H['development'],
                   'scan_task_sha256':H['scan'], 'scan_freeze_sha256':H['scan-freeze']}
        selected = {'schema':infer.qualification.SELECTION_SCHEMA,
                    'status':'selected_for_final_evaluation', 'checker_policy':infer.qualification.CHECKER_POLICY,
                    'checker_profile_sha256':H['checker'], 'development_passes':11, 'scan_passes':4,
                    'required_safety_passed':True,
                    'checks':{key:True for key in infer.qualification.QUALIFICATION_CHECK_KEYS},
                    'qualification':'software and geometry only', 'manufacturing_authorized':False,
                    'qualification_source_sha256':H['qualification-source'],
                    'development_gate_source_sha256':H['gate-source'], **current, **base['binding']}
        if selection_mutation:
            selection_mutation(selected)
        if alias:
            (work/'evaluation').mkdir()
            if alias == 'hardlink':
                tasks.write_text('{"synthetic_reserved_only":true}\n')
                selected_path.hardlink_to(tasks)
            else:
                selected_path.symlink_to(tasks)
        if tasks_alias or profile_alias:
            tasks.parent.mkdir(exist_ok=True)
            tasks.write_text('{"synthetic_reserved_only":true}\n')
            if tasks_alias:
                supplied_tasks = work/'task-alias.json'
                supplied_tasks.hardlink_to(tasks)
            if profile_alias:
                supplied_profile.hardlink_to(tasks)
        events = [];captures = [];validated = [False]
        taskfile = {'api_card':None,'tasks':[{'id':'synthetic-only', 'prompt':'Synthetic fixture only.'}]}
        real_validate = infer.qualification.validate_selection

        def checker():
            events.append('profile')
            if profile_failure:
                raise ValueError('synthetic profile failure')
            return {'checker_profile_sha256':H['checker']}

        def verify_base(*args, **kwargs):
            events.append('base')
            return copy.deepcopy(base)

        def digest(path):
            path = Path(path)
            if path == tasks:
                assert validated[0], 'Final task hash attempted before selection validation.'
                events.append('synthetic-final-hash');return H['task']
            if path == selected_path:
                return H['selection']
            if path == adapter/'adapters.safetensors':
                return H['other'] if bad_adapter else H['adapter']
            if path == adapter/'adapter_config.json':return H['config']
            if path == work/'evaluation/development.json':return H['development']
            if path == work/'end-to-end/development.json':return H['scan']
            if path == work/'end-to-end/freeze.json':return H['scan-freeze']
            if path == infer.qualification.ROOT/'qualification_v2.py':return H['qualification-source']
            if path == infer.qualification.ROOT/'qualification.py':return H['gate-source']
            raise AssertionError('Unexpected file hash: '+str(path))

        def read_text(path, *args, **kwargs):
            path = Path(path)
            if path == selected_path:
                assert not alias, 'Aliased selection was read.'
                events.append('selection-read');return json.dumps(selected)
            if path == work/'evaluation/freeze.json':
                assert validated[0], 'Freeze read before selection validation.'
                return json.dumps({'files':{'final.json':H['task']}})
            if path == tasks:
                assert validated[0], 'Reserved task body read before selection validation.'
                events.append('synthetic-final-read');return json.dumps(taskfile)
            raise AssertionError('Unexpected file read: '+str(path))

        def validate(selection, now, checker_hash):
            real_validate(selection, now, checker_hash)
            validated[0] = True

        def capture(*args, **kwargs):
            captures.append((args,kwargs))
            assert args[:3] == (taskfile['tasks'],output,adapter)
            assert args[3:7] == (H['task'],H['selection'],6144,None)
            assert kwargs['checker_hash'] == H['checker']
            kwargs['preflight']()  # Revalidate model/source metadata before a model could load.

        argv = ['infer_v2.py','--tasks',str(supplied_tasks),'--output',str(output),
                '--adapter',str(adapter),'--base-profile',str(supplied_profile)]
        if not missing:
            argv += ['--selection-receipt',str(selected_path)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(infer,'ROOT',work))
            stack.enter_context(patch.object(infer.qualification,'ROOT',work))
            stack.enter_context(patch.object(infer,'digest',digest))
            stack.enter_context(patch.object(infer.qualification,'digest',digest))
            stack.enter_context(patch.object(infer.qualification,'verify_checker_profile',checker))
            stack.enter_context(patch.object(infer.qualification,'validate_selection',validate))
            stack.enter_context(patch.object(infer.base_runtime,'verify_base',verify_base))
            stack.enter_context(patch.object(infer,'run_generation',capture))
            stack.enter_context(patch.object(Path,'read_text',read_text))
            stack.enter_context(patch.object(sys,'argv',argv))
            if valid:
                infer.main()
                assert events.count('synthetic-final-read') == 1 and len(captures) == 1
            else:
                fragment = ('synthetic profile failure' if profile_failure else
                            'Reserved tasks require the canonical final task path.' if tasks_alias else
                            'Metadata and output paths cannot alias reserved final inputs.' if profile_alias else
                            'requires selected candidate' if missing else
                            'cannot alias reserved' if alias else
                            'selected receipt under the current v2' if selected.get('schema') != infer.qualification.SELECTION_SCHEMA or selected.get('checker_profile_sha256') != H['checker'] else
                            'Selected model, task, checker or qualification source changed.' if bad_adapter or selected.get('qualification_source_sha256') != H['qualification-source'] else
                            'Complete current development selection')
                fails(infer.main,fragment)
                assert 'synthetic-final-read' not in events and 'synthetic-final-hash' not in events
                assert not captures and not output.exists()
                if profile_failure:assert events == ['profile']
                if tasks_alias or profile_alias:assert events == ['profile']
                if alias:assert 'selection-read' not in events
        PASSED.append(name)


def profile_changed_under_lock():
    """The real generation entry point must stop before even importing MLX."""
    with tempfile.TemporaryDirectory(prefix='infer-v2-lock-check-') as temp:
        work = Path(temp)/'work';work.mkdir();output = work/'capture'
        events = [];original_import = builtins.__import__
        def lock(*args):events.append('lock')
        def checker():
            assert events == ['lock']
            events.append('profile');return {'checker_profile_sha256':H['other']}
        def forbid_import(name,*args,**kwargs):
            assert name != 'mlx' and not name.startswith(('mlx.','mlx_lm')), 'MLX/model import attempted.'
            return original_import(name,*args,**kwargs)
        with patch.object(infer,'ROOT',work), patch.object(infer.fcntl,'flock',lock), \
             patch.object(infer.qualification,'verify_checker_profile',checker), \
             patch.object(infer.base_runtime,'verify_base',side_effect=AssertionError('Base accessed after checker change.')), \
             patch.object(builtins,'__import__',forbid_import):
            fails(lambda:infer.run_generation([],output,None,H['task'],checker_hash=H['checker']),
                  'Checker profile changed before generation.')
        assert events == ['lock','profile'] and not output.exists()
    PASSED.append('checker-change-under-lock-before-model-import')


def unchanged_generation():
    """Compare executable AST for prompt/decoding/capture behavior, not formatting."""
    old_bytes = (ROOT/'infer.py').read_bytes()
    assert hashlib.sha256(old_bytes).hexdigest() == 'cd9eaa33502eb9cf9e9d3e6581be92dd79477dc64c1a1186a39271e6e88cc8fa'
    old = ast.parse(old_bytes);new = ast.parse((ROOT/'infer_v2.py').read_bytes())
    def generation(tree):return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_generation')
    def row_loop(tree):return next(n for n in ast.walk(generation(tree)) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='row')
    assert ast.dump(row_loop(old),include_attributes=False) == ast.dump(row_loop(new),include_attributes=False)
    def calls(tree):
        wanted = ('load','tok.add_eos_token','mx.set_memory_limit','mx.set_cache_limit','mx.random.seed')
        return [ast.dump(n,include_attributes=False) for n in ast.walk(generation(tree))
                if isinstance(n,ast.Call) and ast.unparse(n.func) in wanted]
    assert calls(old) == calls(new)
    def ids(tree):return next(n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=='a.ids')
    assert ast.dump(ids(old),include_attributes=False) == ast.dump(ids(new),include_attributes=False)
    PASSED.append('v1-prompt-decoding-row-batch-source-preserved')


def main():
    unchanged_generation()
    scenario('profile-rejected-before-any-task-read',profile_failure=True)
    scenario('missing-selection-before-reserved-read',missing=True)
    scenario('legacy-selection-before-reserved-read',selection_mutation=lambda s:s.update(schema='picogk.am.development-selection@1'))
    scenario('mixed-checker-selection-before-reserved-read',selection_mutation=lambda s:s.update(checker_profile_sha256=H['other']))
    scenario('incomplete-gate-map-before-reserved-read',selection_mutation=lambda s:s.update(checks={}))
    scenario('aliased-selection-before-read',alias=True)
    scenario('hardlinked-selection-before-read',alias='hardlink')
    scenario('hardlinked-task-rejected-before-read',tasks_alias=True)
    scenario('hardlinked-base-profile-before-base-access',profile_alias=True)
    scenario('adapter-hash-mismatch-before-reserved-read',bad_adapter=True)
    scenario('qualification-code-hash-mismatch-before-reserved-read',selection_mutation=lambda s:s.update(qualification_source_sha256=H['other']))
    scenario('valid-current-model-code-task-checker-bindings',valid=True)
    profile_changed_under_lock()
    assert not any(name=='mlx' or name.startswith('mlx.') for name in sys.modules)
    print(json.dumps({'status':'passed','checks':len(PASSED),'cases':PASSED,
                      'real_reserved_data_read_or_hashed':False,'model_loaded':False,
                      'mlx_imported':False,'gpu_used':False,'v1_modified':False},indent=2))


if __name__=='__main__':main()
