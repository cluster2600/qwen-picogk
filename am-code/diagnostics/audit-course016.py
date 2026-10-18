"""Audit the completed fixed-step course on CPU before any candidate inference."""
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from safetensors.numpy import load_file

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / 'runs/32b-field011-continuation1'
FILES = {}


def digest(path):
    path = Path(path).resolve(strict=True)
    if path not in FILES:
        with path.open('rb') as stream:
            FILES[path] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return FILES[path]


def read(path):
    return json.loads(Path(path).read_text())


def main():
    with (ROOT.parent / 'train.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checks = {}

        def check(name, passed):
            checks[name] = bool(passed)
            if not passed:
                raise ValueError('Completed-course audit failed: ' + name)

        plan = read(ROOT / 'course-016-protocol.json')
        receipt = read(RUN / 'training-receipt.json')
        protocol = read(RUN / 'protocol.json')
        config = read(RUN / 'adapter/adapter_config.json')
        check('registered_plan_unchanged', digest(ROOT / 'course-016-protocol.json') ==
              '1e5d5ad21beb98096b1c2ba26370b2eaf460b8a903313b3e213667dc0dd8d28e')
        check('completed_fixed_step_rows', receipt['status'] == 'completed' and
              receipt['training_steps'] == config['iters'] == plan['iterations'] == 592 and
              receipt['training_rows'] == plan['training_rows'] == 592)
        check('protocol_bound', digest(RUN / 'protocol.json') == receipt['protocol_sha256'])
        for key, expected in {'learning_rate': 2e-6, 'num_layers': 16, 'batch_size': 1,
                'max_seq_length': 6144, 'mask_prompt': True, 'grad_checkpoint': True,
                'seed': 9931414, 'resume_adapter_file': str(ROOT / plan['parent_adapter'])}.items():
            check('registered_config_' + key, config[key] == protocol['config'][key] == expected)
        check('rank_scale_dropout', config['lora_parameters'] == {'rank': 8, 'scale': 20., 'dropout': 0.})
        check('fresh_adam', config['optimizer'] == 'adam' and config['grad_accumulation_steps'] == 1
              and plan['fresh_optimizer'] is True)
        check('completed_parent_bound', digest(ROOT / plan['parent_adapter']) == plan['parent_adapter_sha256'] ==
              protocol['resume_adapter_sha256'] == '43489285c8bddf9ecac501329aee0360e07dfa7f8f274b997003764282ded549')
        check('completed_parent_cpu_audit_bound', digest(ROOT / 'course015-cpu-audit.json') == plan['parent_cpu_audit_sha256'] and read(ROOT / 'course015-cpu-audit.json')['status'] == 'passed')
        corpus = RUN / 'data/train.jsonl'
        check('exact_corpus', digest(corpus) == plan['corpus_sha256'] == protocol['corpus_sha256'] ==
              'a253acd42a733facbd7dc34bf471e18b8196a34a5a5f215135bfc1acf9d6eb18')
        check('exact_focused592', corpus.read_bytes() == (ROOT / plan['corpus']).read_bytes())
        check('exact_previous496_prefix', corpus.read_bytes().startswith(
              (ROOT / 'data/focused-32b-005/train.jsonl').read_bytes()))
        check('focused_manifest_bound', digest(ROOT / 'data/focused-32b-006/manifest.json') == plan['provenance_sha256'])
        check('native_teachers_bound', digest(ROOT / 'data/corrective-011/native-review-001/report.json') == plan['new_native_report_sha256'])
        check('token_rows_bound', digest(ROOT / 'data/focused-32b-006/token-rows.json') == plan['token_rows_sha256'])
        check('maximum_tokens_no_truncation', receipt['maximum_tokens'] == plan['maximum_actual_tokens'] == 3110 < config['max_seq_length'])
        check('bounded_reported_mlx_peak', 0 < receipt['peak_memory_bytes'] < protocol['memory_limit_bytes'] == 36 * 1024**3)
        for name, expected in read(ROOT / 'course010-cpu-audit.json')['files_sha256'].items():
            check('preserved:' + name, digest(ROOT / name) == expected)
        profile = read(ROOT / 'base-profile-32b.json')
        check('pinned_base_profile', digest(ROOT / 'base-profile-32b.json') == plan['base_profile_sha256'])
        base = ROOT / profile['model_directory']
        check('nine_base_files_only', {p.name for p in base.iterdir()} == set(profile['model_files_sha256']) and
              len(profile['model_files_sha256']) == 9)
        for name, expected in profile['model_files_sha256'].items():
            check('base:' + name, digest(base / name) == expected)
        check('runtime_base_binding', protocol['base_weights_sha256'] == plan['base_weights_sha256'] ==
              profile['model_files_sha256']['model.safetensors'])
        spec = importlib.util.spec_from_file_location('course016_policy', ROOT / 'evaluation/policy_v2.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        check('frozen_checker', policy.verify_checker_profile()['checker_profile_sha256'] ==
              plan['checker_profile_sha256'] == '7f6394323b81867faa37aef39db444ba0d0afe833c213baceb0cadc55fbf7c45')
        for key, name in [('train_source_sha256', 'train.py'), ('infer_source_sha256', 'infer_v2.py'),
                          ('base_runtime_source_sha256', 'base_runtime.py')]:
            check('source:' + name, digest(ROOT / name) == plan[key])
        check('matched_baseline', digest(ROOT / 'baseline-scores-32b-v2/report.json') ==
              plan['matched_baseline_score_sha256'])
        adapter = RUN / 'adapter/adapters.safetensors'
        check('adapter_receipt_binding', digest(adapter) == receipt['adapter_sha256'])
        tensors = load_file(str(adapter))
        expected_shapes = {}
        dimensions = {'self_attn.q_proj': (5120, 5120), 'self_attn.k_proj': (5120, 1024),
            'self_attn.v_proj': (5120, 1024), 'self_attn.o_proj': (5120, 5120),
            'mlp.gate_proj': (5120, 27648), 'mlp.up_proj': (5120, 27648),
            'mlp.down_proj': (27648, 5120)}
        for layer in range(48, 64):
            for module, (inputs, outputs) in dimensions.items():
                name = f'model.layers.{layer}.{module}'
                expected_shapes[name + '.lora_a'] = (inputs, 8)
                expected_shapes[name + '.lora_b'] = (8, outputs)
        check('exact_224_lora_keys_shapes', len(tensors) == receipt['trainable_arrays'] == 224 and
              {k: v.shape for k, v in tensors.items()} == expected_shapes)
        check('cpu_finite_float32', all(v.dtype == np.float32 and np.isfinite(v).all() for v in tensors.values())
              and receipt['all_tensors_finite'] is True)
        check('expected_parameter_count', sum(v.size for v in tensors.values()) == 16777216)
        checkpoints = sorted((RUN / 'adapter').glob('*_adapters.safetensors'))
        check('nine_registered_checkpoints', [p.name for p in checkpoints] ==
              [f'{i:07d}_adapters.safetensors' for i in (60, 120, 180, 240, 300, 360, 420, 480, 540)])
        for path in checkpoints:
            digest(path)
        digest(RUN / 'adapter/adapter_config.json')
        digest(RUN / 'training-receipt.json')
        result = dict(schema='picogk.am.completed-course-cpu-audit@1', status='passed',
            created_at_utc=datetime.now(timezone.utc).isoformat(), run=plan['course'], checks=checks,
            adapter_sha256=digest(adapter), adapter_config_sha256=digest(RUN / 'adapter/adapter_config.json'),
            training_receipt_sha256=digest(RUN / 'training-receipt.json'),
            checker_profile_sha256=plan['checker_profile_sha256'], trainable_arrays=224,
            trainable_parameters=16777216, peak_memory_bytes=receipt['peak_memory_bytes'],
            elapsed_training_seconds=receipt['elapsed_seconds'],
            files_sha256={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): h
                          for p, h in FILES.items()},
            gpu_used=False, mlx_imported=False, final_contents_read=False,
            qualification='training artifact integrity only; native qualification pending',
            manufacturing_authorized=False)
        output = ROOT / 'course016-cpu-audit.json'
        with output.open('x') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
        print(json.dumps(dict(status='passed', checks=len(checks), receipt_sha256=digest(output))))


if __name__ == '__main__':
    main()
