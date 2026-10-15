#!/usr/bin/env python3
"""Prove the fresh numeric oracles reject wrong radii and rounded caps; never train these."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('corrective003_checker', ROOT / 'validate.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    cases = json.loads((ROOT / 'cases.json').read_text())['cases']
    beam = next(case for case in cases if case['id'] == 'fresh-numeric-flat-beam-01')
    original = (ROOT / beam['source']).read_text()
    assert checker.digest(ROOT / beam['source']) == beam['source_sha256']
    probe_binary, probe_env = checker.core.build(checker.previous.PROBE, run_dir / 'trusted-probe')
    mutations = [('halved-radius', original.replace('0.55000f', '0.27500f')),
                 ('rounded-caps', original.replace(', false);', ', true);'))]
    results = []
    for label, code in mutations:
        assert code != original
        folder = run_dir / label
        folder.mkdir()
        checker.core.static_gate(code)
        binary, env = checker.core.build(code, folder)
        (folder / 'tmp').mkdir(exist_ok=True)
        output = folder / 'output'
        rc = checker.execute(binary, env, ROOT / beam['input'], output, folder, 'run.log')
        assert rc == 0
        checks, details = checker.check_geometry(output, folder, beam['oracle'], probe_binary, probe_env)
        failing = [name for name, value in checks.items() if not value]
        assert 'independent_vdb_numeric_radius_endpoint_probes' in failing
        assert 'independent_direct_stl_numeric_probes' in failing
        result = {'fault': label, 'rejected': True, 'native_exit_code': rc,
                  'teacher_source_sha256': beam['source_sha256'],
                  'mutant_source_sha256': hashlib.sha256(code.encode()).hexdigest(),
                  'failed_checks': failing, 'checks': checks, 'details': details}
        (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
    report = {'schema': 'picogk.am.corrective-fault-check@1', 'rejected': len(results), 'total': 2,
              'train_sha256': checker.digest(ROOT / 'train.jsonl'),
              'cases_sha256': checker.digest(ROOT / 'cases.json'),
              'checker_sha256': checker.digest(ROOT / 'validate.py'),
              'fault_checker_sha256': checker.digest(Path(__file__)),
              'cases': results, 'training_data': False, 'manufacturing_authorized': False}
    (run_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('2/2 deliberately incorrect beam programs rejected by native and direct STL probes.')


if __name__ == '__main__':
    main()
