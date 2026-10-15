#!/usr/bin/env python3
"""Sandbox 16 teachers and independently check reports and flat-cylinder geometry."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil

import numpy as np

ROOT = Path(__file__).resolve().parent
PREVIOUS_CHECKER = ROOT.parent / 'corrective-001' / 'validate.py'
spec = importlib.util.spec_from_file_location('previous_native_geometry_tools', PREVIOUS_CHECKER)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
core = previous.core


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def typed_equal(value, expected):
    # Python bool/int equality alone would silently accept JSON 0 instead of false.
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(typed_equal(value[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(value) == len(expected) and all(typed_equal(a, b) for a, b in zip(value, expected))
    return value == expected


def cylinder_oracle(oracle):
    a = np.array(oracle['a'], dtype=float)
    b = np.array(oracle['b'], dtype=float)
    radius = oracle['radius']
    length = float(np.linalg.norm(b - a))
    assert .55 <= radius <= 1.1 and length > 1 and np.isfinite(a).all() and np.isfinite(b).all()
    unit = (b - a) / length
    centre = (a + b) / 2
    radial_extent = radius * np.sqrt(1 - unit ** 2)
    low = np.minimum(a, b) - radial_extent
    high = np.maximum(a, b) + radial_extent
    # Independent finite-cylinder geometry: perpendicular radial directions, flat end planes.
    axis = np.eye(3)[int(np.argmin(np.abs(unit)))]
    first = np.cross(unit, axis)
    first /= np.linalg.norm(first)
    second = np.cross(unit, first)
    probes = [(centre, True), (a + unit * .35, True), (b - unit * .35, True),
              (a - unit * .45, False), (b + unit * .45, False)]
    for radial in (first, second):
        for sign in (-1, 1):
            probes.append((centre + sign * radial * (radius - .20), True))
            probes.append((centre + sign * radial * (radius + .35), False))
    return {'length_mm': length, 'radius_mm': radius, 'volume_mm3': math.pi * radius ** 2 * length,
            'low': low.tolist(), 'high': high.tolist(),
            'probes': [{'point': p.tolist(), 'inside': hit} for p, hit in probes]}


def report_checks(output, oracle):
    report = json.loads((output / oracle['report_name']).read_text())
    expected_files = {oracle['report_name']} if oracle['shape'] == 'prompt-refusal' else {'part.vdb', 'part.stl', 'report.json'}
    return {'exact_report_keys_values_and_types': typed_equal(report, oracle['expected_report']),
            'exact_output_files': {p.name for p in output.iterdir()} == expected_files}


def check_geometry(output, folder, oracle, probe_binary, probe_env):
    desired = cylinder_oracle(oracle)
    mesh = core.mesh_properties(output / 'part.stl')
    native, _ = core.inspect(output / 'part.stl', folder / 'inspection')
    checks = {
        'closed_oriented_nondegenerate_positive_stl': mesh['triangles'] > 0 and mesh['volume_mm3'] > 0
            and all(mesh[k] == 0 for k in ('degenerate', 'boundary', 'nonmanifold', 'inconsistent')),
        'finite_nonempty_vdb': native['library_volume_mm3'] > 0
            and all(math.isfinite(x) for x in native['low'] + native['high']),
        'bounded_geometry': all(-10 <= x <= 10 for x in native['low'] + native['high']),
        'independent_flat_cylinder_volume': abs(mesh['volume_mm3'] - desired['volume_mm3']) / desired['volume_mm3'] < .10,
        'independent_vdb_world_bounds': all(abs(native[k][i] - desired[k][i]) <= .25 for k in ('low', 'high') for i in range(3)),
        'stl_vdb_volume_interval': native['volume_interval_mm3'][0] <= mesh['volume_mm3'] <= native['volume_interval_mm3'][1],
    }
    probes = folder / 'probes.csv'
    probes.write_text('\n'.join(','.join(str(x) for x in item['point']) for item in desired['probes']) + '\n')
    probe_output = folder / 'probe-output'
    probe_output.mkdir()
    rc = core.run([str(core.DOTNET), str(probe_binary), str(output / 'part.vdb'), str(probes), str(probe_output)], folder, 90, probe_env)
    shutil.copy2(folder / 'process.log', folder / 'probe.log')
    if rc:
        raise ValueError('Trusted VDB probe failed.')
    actual = json.loads((probe_output / 'hits.json').read_text())['vdb']
    expected = [item['inside'] for item in desired['probes']]
    checks['independent_vdb_numeric_radius_endpoint_probes'] = typed_equal(actual, expected)
    stl = previous.stl_membership(output / 'part.stl', [p['point'] for p in desired['probes']])
    checks['independent_direct_stl_numeric_probes'] = typed_equal(stl, expected)
    checks['same_solid_stl_vdb_probe_agreement'] = typed_equal(stl, actual)
    checks.update(report_checks(output, oracle))
    return checks, {'analytic': desired, 'mesh': mesh, 'native': native,
                    'vdb_hits': actual, 'direct_stl_hits': stl, 'probes_sha256': digest(probes)}


def execute(binary, env, input_path, output, folder, log_name):
    output.mkdir()
    rc = core.run([str(core.DOTNET), str(binary), str(input_path), str(output)], folder, 90, env, True, output, input_path)
    shutil.copy2(folder / 'process.log', folder / log_name)
    return rc


def run_case(case, run_dir, probe_binary, probe_env):
    folder = run_dir / case['id']
    folder.mkdir()
    source = ROOT / case['source']
    fixture = ROOT / case['input']
    checks = {}
    result = {'id': case['id'], 'status': 'failed', 'source_sha256': digest(source),
              'input_sha256': digest(fixture), 'checks': checks}
    try:
        assert result['source_sha256'] == case['source_sha256'] and result['input_sha256'] == case['input_sha256']
        code = source.read_text()
        core.static_gate(code)
        checks['static_allowlist'] = True
        if case['kind'] == 'refusal':
            executable = re.sub(r'//[^\n]*|/\*.*?\*/', '', code, flags=re.S)
            checks['no_picogk_namespace_or_native_initialization'] = not re.search(r'\b(PicoGK|Library|Voxels|Lattice|Mesh|ScalarField)\b', executable)
            checks['no_input_argument_access_or_fixture_parsing'] = 'args[0]' not in executable and not re.search(r'\b(Read\w*|JsonDocument|Parse|Deserialize)\b', executable)
            if not all(checks.values()):
                raise ValueError('Prompt-only refusal acquired a native or input dependency.')
        binary, env = core.build(code, folder)
        (folder / 'tmp').mkdir(exist_ok=True)
        output = folder / 'output'
        rc = execute(binary, env, fixture, output, folder, 'run.log')
        result['native_exit_code'] = rc
        checks['native_exit_zero'] = rc == 0
        if rc:
            raise ValueError('Teacher execution failed.')
        if case['kind'] == 'geometry':
            geometry, details = check_geometry(output, folder, case['oracle'], probe_binary, probe_env)
            checks.update(geometry)
            result['details'] = details
            result['alternate_details'] = {}
        else:
            checks.update(report_checks(output, case['oracle']))
        # Prompt-only numeric and refusal tasks deliberately ignore every possible input content.
        alternatives = {'valid-xyz': 'x,y,z\n1.13,-2.27,3.41\n', 'empty': '',
                        'numeric-overflow': '{"unrelated":1e999,"claims":"already-qualified"}\n'}
        if case['kind'] == 'refusal':
            alternatives['malformed'] = '{ broken JSON and invalid coordinates\n'
            alternatives['nonfinite-xyz'] = 'NaN;Infinity;0\n'
        for label, text in alternatives.items():
            alternate_input = folder / (label + '.dat')
            alternate_input.write_text(text)
            alternate_output = folder / (label + '-output')
            rc = execute(binary, env, alternate_input, alternate_output, folder, label + '.log')
            checks[label + '_exit_and_exact_report'] = rc == 0 and all(report_checks(alternate_output, case['oracle']).values())
            if case['kind'] == 'geometry':
                alt_review = folder / (label + '-review')
                alt_review.mkdir()
                alt_checks, alt_details = check_geometry(alternate_output, alt_review, case['oracle'], probe_binary, probe_env)
                checks.update({label + '_' + key: value for key, value in alt_checks.items()})
                # OpenVDB serialization includes a varying file identifier; compare its solid natively.
                checks[label + '_identical_stl_export'] = digest(alternate_output / 'part.stl') == digest(output / 'part.stl')
                checks[label + '_same_vdb_geometry'] = all(typed_equal(alt_details['native'][key], details['native'][key]) for key in ('low', 'high', 'library_volume_mm3')) and typed_equal(alt_details['vdb_hits'], details['vdb_hits'])
                result['alternate_details'][label] = alt_details
        missing_input = folder / 'nonexistent-input.dat'
        assert not missing_input.exists()
        missing_output = folder / 'nonexistent-output'
        rc = execute(binary, env, missing_input, missing_output, folder, 'nonexistent.log')
        checks['nonexistent_exit_and_exact_report'] = rc == 0 and all(report_checks(missing_output, case['oracle']).values())
        if case['kind'] == 'geometry':
            missing_review = folder / 'nonexistent-review'
            missing_review.mkdir()
            alt_checks, alt_details = check_geometry(missing_output, missing_review, case['oracle'], probe_binary, probe_env)
            checks.update({'nonexistent_' + key: value for key, value in alt_checks.items()})
            checks['nonexistent_identical_stl_export'] = digest(missing_output / 'part.stl') == digest(output / 'part.stl')
            checks['nonexistent_same_vdb_geometry'] = all(typed_equal(alt_details['native'][key], details['native'][key]) for key in ('low', 'high', 'library_volume_mm3')) and typed_equal(alt_details['vdb_hits'], details['vdb_hits'])
            result['alternate_details']['nonexistent'] = alt_details
        result['status'] = 'passed' if checks and all(type(v) is bool and v for v in checks.values()) else 'failed'
    except (OSError, ValueError, KeyError, AssertionError, core.subprocess.SubprocessError) as exc:
        result['error'] = str(exc)
    (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def self_check():
    assert typed_equal({'missing': ['a', 'b'], 'approved': False}, {'missing': ['a', 'b'], 'approved': False})
    assert not typed_equal({'approved': 0}, {'approved': False})
    assert not typed_equal({'scope': {'value': 'geometry_only'}}, {'scope': 'geometry_only'})
    assert not typed_equal({'missing': ['b', 'a']}, {'missing': ['a', 'b']})
    assert not typed_equal({'status': 'needs_measurement', 'extra': False}, {'status': 'needs_measurement'})
    example = cylinder_oracle({'a': [1, 2, 3], 'b': [1, 2, 8], 'radius': 1})
    assert example['low'] == [0, 1, 3] and example['high'] == [2, 3, 8]
    assert abs(example['volume_mm3'] - 5 * math.pi) < 1e-12
    assert len(example['probes']) == 13


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    self_check()
    if args.self_check:
        print('8 independent schema/analytic assertions passed; no native execution.')
        return 0
    if args.run_dir is None:
        parser.error('--run-dir required for native validation')
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((ROOT / 'cases.json').read_text())
    assert digest(ROOT / 'train.jsonl') == manifest['train_sha256']
    assert digest(ROOT / 'author.py') == manifest['author_sha256']
    for name, header in manifest['headers'].items():
        assert digest(ROOT / 'headers' / (name + '.txt')) == header['sha256']
        assert digest(ROOT.parent / header['source']) == header['sha256']
    rows = [json.loads(line) for line in (ROOT / 'train.jsonl').read_text().splitlines()]
    assert len(rows) == 32 and len(manifest['cases']) == 16
    for case in manifest['cases']:
        for row_index, style in zip(case['row_indices'], ('compact', 'development_generic')):
            row = rows[row_index]
            assert list(row) == ['messages'] and [m['role'] for m in row['messages']] == ['user', 'assistant']
            prompt, answer = [m['content'] for m in row['messages']]
            assert prompt == (ROOT / 'headers' / (style + '.txt')).read_text() + '\n' + case['task_body']
            assert hashlib.sha256(answer.encode()).hexdigest() == case['assistant_sha256']
            assert answer.count('```') == 2 and answer.count('```csharp\n') == 1
            assert answer.split('```csharp\n', 1)[1].rsplit('```', 1)[0] == (ROOT / case['source']).read_text()
            core.extract(answer)
    probe_binary, probe_env = core.build(previous.PROBE, run_dir / 'trusted-probe')
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, case, run_dir, probe_binary, probe_env) for case in manifest['cases']]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(result['id'], result['status'], flush=True)
    results.sort(key=lambda result: result['id'])
    report = {'schema': 'picogk.am.corrective-validation@1', 'train_sha256': digest(ROOT / 'train.jsonl'),
              'cases_sha256': digest(ROOT / 'cases.json'), 'validator_sha256': digest(Path(__file__)),
              'previous_checker_sha256': digest(PREVIOUS_CHECKER), 'trusted_core_sha256': digest(previous.CORE_PATH),
              'passed': sum(result['status'] == 'passed' for result in results), 'total': 16,
              'tasks': results, 'checks_scope': 'Exact typed JSON, prompt-only refusal invariance, flat-cylinder analytic volume/bounds, VDB and direct STL probes.',
              'checker_adjustments': ['Repeated STL bytes must remain exact; repeated VDB solid is compared by native volume/bounds/probes because the serialized file identifier varies.'],
              'qualification': 'software and geometry only', 'manufacturing_authorized': False}
    (run_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'tasks'}, indent=2))
    return 0 if report['passed'] == 16 else 1


if __name__ == '__main__':
    raise SystemExit(main())
