"""Lint, verify and assemble the PicoGK DfAM code corpus.

The corpus source of truth is data/dfam-code/cases.jsonl. Each record holds a
prompt, an explanation and a complete C# example for PicoGK 2.3.0. Commands:

  lint     schema, citation, API-convention and near-duplicate checks (no .NET)
  verify   compile every example, run it on synthetic fixtures in its own
           memory-capped process, and measure the outputs with the separate
           trusted checker in dfam-native/Checker
  assemble write length-checked MLX messages after full partition/receipt checks

`verify` executes corpus code. Run it only on a workstation with the PicoGK
native runtime (see docs/DFAM_CODE_CORPUS.md); CI only runs `lint` and the
receipt consistency tests.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/dfam-code'
WORK = ROOT / 'work'
CATEGORIES = {'scan': 'scan_repair', 'infill': 'bionic_infill', 'dfam': 'dfam', 'debug': 'troubleshooting'}
COUNTS = {'scan': 45, 'infill': 60, 'dfam': 30, 'debug': 15}
SPLITS = {  # valid, test per category; the rest is train
    'scan': (5, 4), 'infill': (6, 6), 'dfam': (3, 3), 'debug': (1, 2)}
INPUTS = {'xyz': 'scan.xyz', 'xyzn': 'scan_normals.xyz', 'csv': 'scan.csv',
          'stl': 'part.stl', 'stl_open': 'part_open.stl', 'none': ''}
VOXEL_MM = 0.3
RUN_SIGNATURE = 'public static void Run(Library lib, string strInputPath, string strOutputDir)'
# Names that do not exist in PicoGK 2.3.0 or break the headless convention.
FORBIDDEN = [
    (r'\bVoxelMatrix\b', 'VoxelMatrix is not a PicoGK type; use Voxels'),
    (r'\.Sub\s*\(', 'Voxels has no Sub(); use BoolSubtract, voxBoolSubtract or -'),
    (r'\bAddToField\b', 'AddToField does not exist; use ScalarField.SetValue'),
    (r'\bLibrary\.Go\s*\(', 'corpus examples are headless; create a scoped Library'),
    (r'\bLibrary\.Log\s*\(', 'Library.Log needs Library.Go; use Console.WriteLine'),
    (r'new\s+(Voxels|Lattice|Mesh|ScalarField|VectorField)\s*\(\s*\)', 'parameterless constructors need a global Library; pass lib'),
    (r'\bVoxels\.voxSphere\s*\(\s*new\b', 'pass the Library as first voxSphere argument'),
    # PicoGKRuntime 0f26321 passes the background in mm to an int narrow-band
    # parameter (PicoGKVdbVoxels.h:390): IntersectImplicit aborts below 1/3 mm
    # voxels and silently narrows the band above. Render into a BBox3 instead.
    (r'\b(vox)?IntersectImplicit\s*\(', 'IntersectImplicit is unreliable in the pinned runtime; use new Voxels(lib, implicit, box) and BoolIntersect'),
    (r'\bMmToVoxels\s*\(', 'Library.MmToVoxels calls the wrong native function in PicoGK 2.3.0'),
]
UNIVERSAL = {'boundary_edges': 0, 'nonmanifold_edges': 0, 'solid_components': 1,
             'inconsistent_orientation_edges': 0, 'degenerate_triangles': 0}
POLICY = 'dfam-strict-v2'
MAX_SEQ_LENGTH = 8192
# Parity rasterisation leaves sub-voxel pockets between near-touching sheets;
# a genuinely trapped lattice cell is hundreds of mm3.
MAX_ENCLOSED_VOID_MM3 = 2.0
MAX_ENCLOSED_POCKET_MM3 = 0.25
YEAR = re.compile(r'\((?:19|20)\d\d\)')


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def load_cases(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return rows


def bibliography():
    return json.loads((DATA / 'bibliography.json').read_text())


def code_lines(code):
    return [line for line in code.splitlines() if line.strip()]


def shingles(text, n):
    tokens = re.findall(r'[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|\S', text)
    return {' '.join(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))}


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def lint_case(case, bib):
    problems = []
    if not isinstance(case, dict):
        return ['case must be an object']
    need = {'id', 'category', 'input', 'title', 'user', 'explanation', 'code', 'references', 'expect'}
    allowed = need | {'split', 'family', 'broken'}
    missing, extra = need - set(case), set(case) - allowed
    if missing or extra:
        return [f'fields missing {sorted(missing)} extra {sorted(extra)}']
    for field in ('id', 'category', 'input', 'title', 'user', 'explanation', 'code'):
        if not isinstance(case[field], str):
            return [f'{field} must be a string']
    if 'family' in case and not re.fullmatch(r'[a-z][a-z0-9-]{2,79}', str(case['family'])):
        problems.append('family must be a stable lowercase identifier')
    m = re.fullmatch(r'(scan|infill|dfam|debug)-(\d{3})', case['id'])
    if not m:
        return ['id must look like scan-001, infill-001, dfam-001 or debug-001']
    prefix = m.group(1)
    if case['category'] != CATEGORIES[prefix]:
        problems.append(f"category must be {CATEGORIES[prefix]}")
    if case['input'] not in INPUTS:
        problems.append('unknown input kind')
    if case.get('split') not in (None, 'train', 'valid', 'test'):
        problems.append('bad split')
    if not 150 <= len(case['user']) <= 3000:
        problems.append(f"user prompt length {len(case['user'])} outside 150..3000")
    if not 700 <= len(case['explanation']) <= 6000:
        problems.append(f"explanation length {len(case['explanation'])} outside 700..6000")
    if '**Limits**' not in case['explanation']:
        problems.append('explanation needs a **Limits** paragraph')
    code = case['code']
    lines = code_lines(code)
    if not 50 <= len(lines) <= 420:
        problems.append(f'code has {len(lines)} non-blank lines, expected 50..420')
    commented = sum('//' in line for line in lines)
    if commented < 0.25 * len(lines):
        problems.append(f'comment density {commented}/{len(lines)} below 25%')
    if RUN_SIGNATURE not in code:
        problems.append('missing exact Run signature: ' + RUN_SIGNATURE)
    if 'public static void Main(string[] args)' not in code:
        problems.append('missing Main(string[] args)')
    if not re.search(r'^using PicoGK;', code, re.M):
        problems.append('missing using PicoGK;')
    if re.search(r'^\s*namespace\b', code, re.M):
        problems.append('do not declare a namespace; the harness adds one')
    if '```' in code or '```' in case['user']:
        problems.append('no markdown fences inside fields; assembly adds them')
    for pattern, why in FORBIDDEN:
        for field in ('code', 'explanation'):
            if re.search(pattern, case[field]):
                problems.append(f'{field}: {why}')
    # Citations: every key must exist, its short form must be quoted in the
    # explanation, and no author-year citation may appear without a key.
    refs = case['references']
    if not isinstance(refs, list) or not refs:
        problems.append('references must be a non-empty list of bibliography keys')
        refs = []
    shorts = set()
    for key in refs:
        if not isinstance(key, str):
            problems.append('reference keys must be strings')
            continue
        if key not in bib:
            problems.append(f'unknown reference key {key}')
            continue
        shorts.add(bib[key]['cite'])
        if bib[key]['cite'] not in case['explanation']:
            problems.append(f"explanation must cite {bib[key]['cite']!r} for key {key}")
    # Any "(YYYY)" must close a registered citation of this case.
    text = case['explanation'] + '\n' + code
    for found in YEAR.finditer(text):
        end = found.end()
        if not any(text[max(0, end - len(s)):end] == s for s in shorts):
            problems.append(f'unregistered citation ...{text[max(0, found.start() - 40):end]!r}')
    expect = case['expect']
    if not isinstance(expect, dict):
        problems.append('expect must be an object')
    else:
        unknown = set(expect) - {'outputs', 'volume_ratio', 'overhang_fraction_max', 'thin_fraction_max', 'min_wall_mm'}
        if unknown:
            problems.append(f'unknown expect keys {sorted(unknown)}')
        if prefix in ('infill', 'dfam') and 'volume_ratio' not in expect and 'overhang_fraction_max' not in expect:
            problems.append('infill and dfam cases must state volume_ratio or overhang_fraction_max')
        interval = expect.get('volume_ratio')
        if interval is not None and (not isinstance(interval, list) or len(interval) != 2 or
                not all(type(v) in (float, int) and math.isfinite(v) for v in interval) or
                not 0 < interval[0] <= interval[1] <= 1):
            problems.append('volume_ratio must be a finite ordered interval in (0, 1]')
        elif prefix == 'infill' and interval is not None and interval[1] > 0.9:
            problems.append('infill volume_ratio upper bound must be <= 0.9 (it must actually lighten)')
        for key in ('overhang_fraction_max', 'thin_fraction_max', 'min_wall_mm'):
            if key in expect and (type(expect[key]) not in (int, float) or not math.isfinite(expect[key]) or
                                  expect[key] < 0 or (key == 'min_wall_mm' and expect[key] == 0) or
                                  (key != 'min_wall_mm' and expect[key] > 1)):
                problems.append(f'{key} must be a fraction in [0, 1] or a positive wall size')
        if 'outputs' in expect and (not isinstance(expect['outputs'], list) or not expect['outputs'] or
                not all(isinstance(n, str) and re.fullmatch(r'[A-Za-z0-9_-]+\.stl', n) for n in expect['outputs']) or
                len(set(expect['outputs'])) != len(expect['outputs'])):
            problems.append('outputs must be unique plain STL filenames')
    broken = case.get('broken')
    if prefix == 'debug':
        if not isinstance(broken, dict) or set(broken) - {'code', 'expect', 'error'} or 'code' not in broken:
            problems.append('debug cases need broken = {code, expect, error?}')
        elif not isinstance(broken['code'], str):
            problems.append('broken.code must be a string')
        elif broken.get('expect') not in ('compile_error', 'runtime_failure'):
            problems.append('broken.expect must be compile_error or runtime_failure')
        elif broken['expect'] == 'compile_error' and not re.fullmatch(r'CS\d{4}', broken.get('error', '')):
            problems.append('compile_error cases must name the expected CS error code')
        elif RUN_SIGNATURE not in broken['code'] and broken['expect'] == 'runtime_failure':
            problems.append('runtime_failure broken code must keep the Run signature')
    elif broken is not None:
        problems.append('only debug cases may carry broken code')
    return problems


def lint(cases, full=False):
    bib = bibliography()
    report = {}
    if not cases:
        return {'corpus': ['empty corpus']}
    if any(not isinstance(c, dict) or not isinstance(c.get('id'), str) for c in cases):
        return {'corpus': ['each case needs a string id']}
    ids = [c.get('id') for c in cases]
    for dup in {i for i in ids if ids.count(i) > 1}:
        report.setdefault(dup, []).append('duplicate id')
    for case in cases:
        for p in lint_case(case, bib):
            report.setdefault(case.get('id', '?'), []).append(p)
    if report:
        return report
    code_sh = {c['id']: shingles(c['code'], 6) for c in cases}
    user_sh = {c['id']: shingles(c['user'].lower(), 4) for c in cases}
    keys = sorted(code_sh)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            jc, ju = jaccard(code_sh[a], code_sh[b]), jaccard(user_sh[a], user_sh[b])
            if jc > 0.55:
                report.setdefault(b, []).append(f'code near-duplicate of {a} (6-gram Jaccard {jc:.2f})')
            if ju > 0.45:
                report.setdefault(b, []).append(f'prompt near-duplicate of {a} (4-gram Jaccard {ju:.2f})')
    if full:
        families = {}
        for case in cases:
            if not case.get('family') or case.get('split') not in ('train', 'valid', 'test'):
                report.setdefault(case['id'], []).append('register family and split before assembly')
                continue
            families.setdefault(case['family'], set()).add(case['split'])
            if case['category'] in ('bionic_infill', 'dfam'):
                for key in ('min_wall_mm', 'thin_fraction_max', 'overhang_fraction_max'):
                    if key not in case['expect']:
                        report.setdefault(case['id'], []).append(f'declare process-screen assumption {key}')
        for family, splits in families.items():
            if len(splits) != 1:
                report.setdefault('corpus', []).append(f'family {family} crosses partitions')
        for prefix, count in COUNTS.items():
            got = sum(c['id'].startswith(prefix + '-') for c in cases)
            if got != count:
                report.setdefault('corpus', []).append(f'{prefix}: {got} cases, expected {count}')
        for prefix, (nv, nt) in SPLITS.items():
            part = [c for c in cases if c['id'].startswith(prefix + '-')]
            got = (sum(c.get('split') == 'valid' for c in part), sum(c.get('split') == 'test' for c in part))
            if got != (nv, nt):
                report.setdefault('corpus', []).append(f'{prefix}: valid/test {got}, expected {(nv, nt)}')
    return report


def wrap(code, namespace):
    """Insert a file-scoped namespace after the leading using directives."""
    lines = code.splitlines()
    insert = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('using ') and s.endswith(';') and '(' not in s:
            insert = i + 1
        elif s and not s.startswith('//'):
            break
    return '\n'.join(lines[:insert] + ['', f'namespace {namespace};', ''] + lines[insert:]) + '\n'


def ns(case_id, broken=False):
    return ('DfamCases.B_' if broken else 'DfamCases.C_') + case_id.replace('-', '_')


def dotnet_env():
    env = dict(os.environ)
    home = Path.home()
    env.setdefault('DOTNET_ROOT', str(home / '.dotnet'))
    env['PATH'] = env['DOTNET_ROOT'] + os.pathsep + env['PATH']
    env['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    native = os.environ.get('PICOGK_NATIVE', str(home / 'picogk/native'))
    env['PICOGK_NATIVE'] = native
    env['LD_LIBRARY_PATH'] = native + (os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    return env


def capped(cmd, mem):
    if sys.platform != 'linux' or not shutil.which('systemd-run'):
        raise RuntimeError('Native verification requires Linux with a working systemd user memory controller; no uncapped fallback')
    probe = ['systemd-run', '--user', '--scope', '--quiet', '-p', f'MemoryMax={mem}',
             '-p', 'MemorySwapMax=0', '-p', 'TasksMax=128']
    if subprocess.run(probe + ['true'], capture_output=True, timeout=15).returncode != 0:
        raise RuntimeError('Cannot enforce native verification resource limits')
    return probe + cmd


def sandbox_command(runner, source, out, namespace, env):
    """Only the selected input, runtime and output are exposed to corpus code."""
    if sys.platform != 'linux' or not shutil.which('bwrap') or not Path('/usr/bin/prlimit').is_file():
        raise RuntimeError('Corpus execution requires Linux bubblewrap and prlimit; no host execution fallback')
    dotnet = Path(shutil.which('dotnet', path=env['PATH']) or '').resolve()
    if not dotnet.is_file():
        raise RuntimeError('dotnet executable not found')
    cmd = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
           '--clearenv', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    readable = {Path('/usr'), Path('/lib'), Path('/lib64'), dotnet.parent,
                Path(env['DOTNET_ROOT']).resolve(), Path(env['PICOGK_NATIVE']).resolve()}
    for folder in readable - {Path('/usr'), Path('/lib'), Path('/lib64')}:
        if folder in (Path('/'), Path.home().resolve()) or ROOT.is_relative_to(folder):
            raise RuntimeError('Runtime mounts must not expose the home or repository tree')
    for folder in sorted(readable):
        if folder.exists():
            cmd += ['--ro-bind', str(folder), str(folder)]
    if Path('/etc/ld.so.cache').exists():
        cmd += ['--ro-bind', '/etc/ld.so.cache', '/etc/ld.so.cache']
    cmd += ['--ro-bind', str(runner.parent.resolve()), '/app', '--bind', str(out.resolve()), '/output',
            '--chdir', '/output', '--setenv', 'HOME', '/tmp', '--setenv', 'TMPDIR', '/tmp',
            '--setenv', 'DOTNET_ROOT', env['DOTNET_ROOT'], '--setenv', 'LD_LIBRARY_PATH', env['PICOGK_NATIVE'],
            '--setenv', 'DOTNET_CLI_TELEMETRY_OPTOUT', '1', '--setenv', 'DOTNET_PROCESSOR_COUNT', '2',
            '--setenv', 'DOTNET_GCHeapHardLimit', '80000000',
            # .NET's W^X double mapping reserves executable memory through a
            # large shared-memory file, which the 256 MiB RLIMIT_FSIZE below
            # kills with SIGXFSZ (exit 153) before Main runs. Keep the file
            # limit and turn the double mapping off instead.
            '--setenv', 'DOTNET_EnableWriteXorExecute', '0']
    input_path = '/input/' + Path(source).name if source else ''
    if source:
        cmd += ['--dir', '/input', '--ro-bind', str(Path(source).resolve()), input_path]
    cmd += ['--', '/usr/bin/prlimit', '--cpu=300:300', '--fsize=268435456:268435456', '--',
            str(dotnet), '/app/' + runner.name, namespace, input_path,
            '/output', str(VOXEL_MM)]
    return capped(cmd, '3G')


def build(project_dir, files, env):
    """Build the runner with the given {filename: source}; return (ok, errors_by_file, log)."""
    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(ROOT / 'dfam-native/Runner', project_dir)
    (project_dir / 'Cases').mkdir()
    for name, text in files.items():
        (project_dir / 'Cases' / name).write_text(text)
    proc = subprocess.run(['dotnet', 'build', '-p:RestoreLockedMode=true', '-c', 'Release', '--nologo', '-v', 'q', '-clp:NoSummary', '-o', 'out'],
                          cwd=project_dir, env=env, capture_output=True, text=True, timeout=900)
    errors = {}
    for line in proc.stdout.splitlines() + proc.stderr.splitlines():
        m = re.search(r'Cases/([^/(]+\.cs)\((\d+),(\d+)\): error (CS\d{4}): (.*?)(?: \[|$)', line)
        if m:
            errors.setdefault(m.group(1), set()).add(f'{m.group(4)} line {m.group(2)}: {m.group(5)}')
    return proc.returncode == 0, {k: sorted(v) for k, v in errors.items()}, proc.stdout[-4000:]


def ensure_trusted(env):
    checker = WORK / 'dfam-checker/Checker.dll'
    src = ROOT / 'dfam-native/Checker'
    stamp = sha(b''.join((src / n).read_bytes() for n in ('Program.cs', 'Checker.csproj', 'packages.lock.json')))
    stamp_file = WORK / 'dfam-checker/source.sha256'
    if not checker.exists() or not stamp_file.exists() or stamp_file.read_text() != stamp:
        subprocess.run(['dotnet', 'build', '-p:RestoreLockedMode=true', '-c', 'Release', '--nologo', '-v', 'q', '-o', str(WORK / 'dfam-checker')],
                       cwd=src, env=env, check=True, capture_output=True, timeout=900)
        stamp_file.write_text(stamp)
        shutil.rmtree(WORK / 'dfam-fixtures', ignore_errors=True)
    fixtures = WORK / 'dfam-fixtures'
    if not (fixtures / 'fixtures.json').exists():
        shutil.rmtree(fixtures, ignore_errors=True)
        subprocess.run(capped(['dotnet', str(checker), 'fixtures', str(fixtures), str(VOXEL_MM)], '4G'),
                       env=env, check=True, capture_output=True, timeout=600)
    return checker, fixtures, stamp


def check_stl(checker, fixtures, stl, min_wall, env):
    proc = subprocess.run(capped(['dotnet', str(checker), 'check', str(stl), str(fixtures / 'fixtures.json'),
                                  str(VOXEL_MM), str(min_wall)], '4G'),
                          env=env, capture_output=True, text=True, timeout=900)
    line = next((l for l in proc.stdout.splitlines() if l.startswith('{')), None)
    if proc.returncode != 0 or line is None:
        return {'checker_error': (proc.stderr or proc.stdout)[-800:]}
    return json.loads(line)


def evaluate(metrics, expect):
    """Return the list of failed conditions for one output STL."""
    failed = []
    if 'checker_error' in metrics:
        return ['checker error: ' + metrics['checker_error']]
    required = set(UNIVERSAL) | {'triangles', 'enclosed_void_mm3', 'enclosed_void_largest_mm3',
                               'volume_ratio_to_fixture', 'overhang_fraction', 'thin_fraction',
                               'volume_mm3', 'mesh_volume_mm3', 'parity_volume_mm3', 'surface_area_mm2', 'min_wall_mm'}
    for key in required:
        if type(metrics.get(key)) not in (int, float) or not math.isfinite(metrics[key]) or metrics[key] < 0:
            failed.append(f'missing, nonfinite or invalid metric {key}')
        elif key in UNIVERSAL or key == 'triangles':
            if metrics[key] != int(metrics[key]):
                failed.append(f'noninteger count {key}')
        elif key in ('overhang_fraction', 'thin_fraction') and metrics[key] > 1:
            failed.append(f'invalid fraction {key}')
    if failed:
        return failed
    for key in ('volume_mm3', 'mesh_volume_mm3', 'parity_volume_mm3', 'surface_area_mm2'):
        if metrics[key] <= 0:
            failed.append(f'nonpositive geometry metric {key}')
    if metrics['min_wall_mm'] != expect.get('min_wall_mm', 1.0):
        failed.append('checker minimum-wall parameter differs from case assumption')
    if metrics.get('triangles', 0) == 0:
        return ['empty mesh']
    for key, want in UNIVERSAL.items():
        if metrics[key] != want:
            failed.append(f'{key} = {metrics[key]}, required {want}')
    if metrics['enclosed_void_mm3'] > MAX_ENCLOSED_VOID_MM3 or metrics['enclosed_void_largest_mm3'] > MAX_ENCLOSED_POCKET_MM3:
        failed.append(f"trapped powder: {metrics['enclosed_void_mm3']} mm3 enclosed, largest pocket "
                      f"{metrics['enclosed_void_largest_mm3']} mm3 (allowed {MAX_ENCLOSED_VOID_MM3} / {MAX_ENCLOSED_POCKET_MM3})")
    if 'volume_ratio' in expect:
        lo, hi = expect['volume_ratio']
        if not lo <= metrics['volume_ratio_to_fixture'] <= hi:
            failed.append(f"volume_ratio_to_fixture = {metrics['volume_ratio_to_fixture']}, declared [{lo}, {hi}]")
    if 'overhang_fraction_max' in expect and metrics['overhang_fraction'] > expect['overhang_fraction_max']:
        failed.append(f"overhang_fraction = {metrics['overhang_fraction']}, declared max {expect['overhang_fraction_max']}")
    if 'thin_fraction_max' in expect and metrics['thin_fraction'] > expect['thin_fraction_max']:
        failed.append(f"thin_fraction = {metrics['thin_fraction']}, declared max {expect['thin_fraction_max']}")
    return failed


def run_case(runner, checker, fixtures, case, broken, env, run_root, timeout):
    namespace = ns(case['id'], broken)
    out = run_root / (case['id'] + ('-broken' if broken else ''))
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    source = str(fixtures / INPUTS[case['input']]) if INPUTS[case['input']] else ''
    started = time.time()
    log_path = out / 'process.log'
    try:
        with log_path.open('w') as log:
            proc = subprocess.run(sandbox_command(runner, source, out, namespace, env),
                                  env={'PATH': env['PATH'], 'HOME': str(Path.home()),
                                       'XDG_RUNTIME_DIR': env.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')},
                                  stdout=log, stderr=log, timeout=timeout, cwd=out)
        code, stderr = proc.returncode, ''
        if log_path.is_file() and not log_path.is_symlink() and log_path.resolve().is_relative_to(out.resolve()):
            with log_path.open('rb') as log:
                log.seek(max(0, log_path.stat().st_size - 800))
                stderr = log.read(800).decode('utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        code, stderr = 'timeout', ''
    record = {'exit': code, 'seconds': round(time.time() - started, 1)}
    if code != 0:
        record['error'] = (stderr.strip().splitlines() or [''])[-1][:400]
        return record
    expect = case['expect']
    names = expect.get('outputs') or sorted(p.name for p in out.glob('*.stl'))
    if not names:
        record['failed'] = ['no STL output']
        return record
    record['outputs'] = {}
    failed = []
    for name in names:
        stl = out / name
        if not stl.is_file() or stl.is_symlink() or not stl.resolve().is_relative_to(out.resolve()):
            failed.append(f'missing declared output {name}')
            continue
        metrics = check_stl(checker, fixtures, stl, expect.get('min_wall_mm', 1.0), env)
        record['outputs'][name] = dict(metrics, stl_sha256=sha(stl.read_bytes()))
        failed += [f'{name}: {f}' for f in evaluate(metrics, expect)]
    record['failed'] = failed
    return record


def verify(cases, tag, jobs, timeout):
    problems = lint(cases)
    if problems:
        raise ValueError('Corpus lint failed: ' + json.dumps(problems))
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', tag) or not 1 <= jobs <= 4 or timeout <= 0:
        raise ValueError('Use a plain tag, 1..4 jobs and a positive timeout')
    env = dotnet_env()
    # Fail before builds or fixture generation if isolation is unavailable.
    capped(['true'], '3G')
    if not shutil.which('bwrap') or not Path('/usr/bin/prlimit').is_file():
        raise RuntimeError('Corpus execution requires bubblewrap and prlimit')
    WORK.mkdir(exist_ok=True)
    lock = open(WORK / 'dfam-verify.lock', 'w')
    print(f'[{tag}] waiting for the verification lock', flush=True)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if (WORK / 'dfam-build' / tag).exists() or (WORK / 'dfam-runs' / tag).exists():
            raise ValueError('Use a new verification tag; existing run evidence is preserved')
        checker, fixtures, checker_sha = ensure_trusted(env)
        project = WORK / 'dfam-build' / tag
        files = {ns(c['id'])[10:] + '.cs': wrap(c['code'], ns(c['id'])) for c in cases}
        runtime_broken = [c for c in cases if c.get('broken', {}).get('expect') == 'runtime_failure']
        files.update({ns(c['id'], True)[10:] + '.cs': wrap(c['broken']['code'], ns(c['id'], True)) for c in runtime_broken})
        results = {c['id']: {} for c in cases}
        # Build, then drop files that fail to compile and rebuild the rest.
        for _ in range(4):
            ok, errors, log = build(project, files, env)
            if ok:
                break
            if not errors:
                raise RuntimeError('build failed without per-file errors:\n' + log)
            for name, errs in errors.items():
                files.pop(name, None)
                cid = name[2:-3].replace('_', '-')
                results[cid]['broken_compiles' if name.startswith('B_') else 'compile_errors'] = errs
        else:
            raise RuntimeError('build did not converge')
        runner = project / 'out/Runner.dll'
        run_root = WORK / 'dfam-runs' / tag
        todo = [(c, False) for c in cases if 'compile_errors' not in results[c['id']]]
        todo += [(c, True) for c in runtime_broken if 'broken_compiles' not in results[c['id']]]
        with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
            futures = {pool.submit(run_case, runner, checker, fixtures, c, b, env, run_root, timeout): (c, b) for c, b in todo}
            for f in concurrent.futures.as_completed(futures):
                c, b = futures[f]
                results[c['id']]['broken_run' if b else 'run'] = f.result()
                print(f"[{tag}] {c['id']}{' (broken)' if b else ''}: {summary(f.result())}", flush=True)
        # Compile-error demonstrations are built alone and must fail as declared.
        for c in cases:
            broken = c.get('broken')
            if not broken or broken.get('expect') != 'compile_error':
                continue
            ok, errors, log = build(WORK / 'dfam-build' / f'{tag}-broken-{c["id"]}',
                                    {'B_x.cs': wrap(broken['code'], ns(c['id'], True))}, env)
            codes = sorted({e.split(' ')[0] for e in errors.get('B_x.cs', [])})
            results[c['id']]['broken_build'] = {'compiled': ok, 'error_codes': codes}
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
    verdicts = {}
    for c in cases:
        r = results[c['id']]
        reasons = []
        if 'compile_errors' in r:
            reasons.append('does not compile: ' + '; '.join(r['compile_errors'][:3]))
        else:
            run = r.get('run', {})
            if run.get('exit') != 0:
                reasons.append(f"run exit {run.get('exit')}: {run.get('error', '')}")
            reasons += run.get('failed', [])
        broken = c.get('broken')
        if broken and broken['expect'] == 'compile_error':
            b = r.get('broken_build', {})
            if b.get('compiled') or broken['error'] not in b.get('error_codes', []):
                reasons.append(f"broken code should fail with {broken['error']}, got {b}")
        if broken and broken['expect'] == 'runtime_failure':
            if 'broken_compiles' in r:
                reasons.append('broken code must compile for a runtime_failure case: ' + '; '.join(r['broken_compiles'][:2]))
            else:
                b = r.get('broken_run', {})
                if b.get('exit') == 0 and not b.get('failed'):
                    reasons.append('broken code ran and passed every check; the demonstrated bug is not observable')
        verdicts[c['id']] = {'passed': not reasons, 'reasons': reasons, 'case_sha256': case_sha(c), **r}
    return {'policy': POLICY, 'policy_source_sha256': sha(Path(__file__).read_bytes()),
            'isolation': 'linux-bubblewrap-systemd', 'checker_source_sha256': checker_sha,
            'fixtures': json.loads((fixtures / 'fixtures.json').read_text())['files_sha256'],
            'voxel_mm': VOXEL_MM, 'picogk_package': '2.3.0', 'cases': verdicts}


def summary(run):
    if run.get('exit') != 0:
        return f"exit {run.get('exit')} {run.get('error', '')}"
    parts = []
    for name, m in run.get('outputs', {}).items():
        if 'triangles' in m and m['triangles']:
            parts.append(f"{name} vol={m['volume_ratio_to_fixture']} void={m['enclosed_void_mm3']} comp={m['solid_components']} "
                         f"open={m['boundary_edges']} ovh={m['overhang_fraction']} thin={m['thin_fraction']}")
    return f"{run['seconds']}s " + ' | '.join(parts) + (' FAIL ' + '; '.join(run['failed']) if run.get('failed') else ' ok')


def case_sha(case):
    return sha(json.dumps(case, sort_keys=True, ensure_ascii=False))


def assemble_text(case, bib):
    """Return MLX chat messages; let the pinned tokenizer apply ChatML once."""
    user = case['user'].strip()
    if case.get('broken'):
        user += '\n\n```csharp\n' + case['broken']['code'].strip() + '\n```'
    refs = '\n'.join(f"- {bib[k]['entry']}" for k in case['references'])
    assistant = (case['explanation'].strip() + '\n\n```csharp\n' + case['code'].strip() + '\n```\n\nReferences:\n' + refs)
    return {'messages': [{'role': 'user', 'content': user},
                         {'role': 'assistant', 'content': assistant}]}


def receipt_check(cases, receipt):
    if (receipt.get('policy') != POLICY or receipt.get('policy_source_sha256') != sha(Path(__file__).read_bytes()) or
            receipt.get('isolation') != 'linux-bubblewrap-systemd' or
            receipt.get('picogk_package') != '2.3.0' or receipt.get('voxel_mm') != VOXEL_MM):
        raise ValueError('A current strict-policy isolated native verification receipt is required')
    src = ROOT / 'dfam-native/Checker'
    stamp = sha(b''.join((src / n).read_bytes() for n in ('Program.cs', 'Checker.csproj', 'packages.lock.json')))
    if receipt.get('checker_source_sha256') != stamp:
        raise ValueError('Checker source binding changed')
    if set(receipt.get('cases', {})) != {c['id'] for c in cases}:
        raise ValueError('Receipt case set differs from corpus')
    for case in cases:
        record = receipt['cases'][case['id']]
        run = record.get('run', {})
        if (record.get('passed') is not True or record.get('case_sha256') != case_sha(case) or
                run.get('exit') != 0 or run.get('failed') != [] or not run.get('outputs')):
            raise ValueError('Missing or rejected native evidence: ' + case['id'])
        if 'outputs' in case['expect'] and set(run['outputs']) != set(case['expect']['outputs']):
            raise ValueError('Receipt outputs differ: ' + case['id'])
        for name, metrics in run['outputs'].items():
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.stl', name) or not re.fullmatch(r'[0-9a-f]{64}', metrics.get('stl_sha256', '')):
                raise ValueError('Missing output binding: ' + case['id'])
            if evaluate(metrics, case['expect']):
                raise ValueError('Native metrics fail current policy: ' + case['id'])


def assemble(cases, receipt, tokenizer):
    problems = lint(cases, full=True)
    if problems:
        raise ValueError('Corpus not ready for training: ' + json.dumps(problems))
    receipt_check(cases, receipt)
    bib = bibliography()
    out = {}
    for split in ('train', 'valid', 'test'):
        rows = [assemble_text(c, bib) for c in cases if c['split'] == split]
        for row in rows:
            tokens = tokenizer.apply_chat_template(row['messages'], tokenize=True, add_generation_prompt=False,
                                                   return_dict=False)
            if len(tokens) > MAX_SEQ_LENGTH:
                raise ValueError(f'Example exceeds {MAX_SEQ_LENGTH} tokens; refusing truncation')
        out[split] = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    return out


def pack(folder):
    """Read one authoring folder: meta.json, user.md, explanation.md, code.cs[, broken.cs]."""
    meta = json.loads((folder / 'meta.json').read_text())
    case = {k: meta[k] for k in ('id', 'category', 'input', 'title', 'references', 'expect') if k in meta}
    for key in ('split', 'family'):
        if key in meta:
            case[key] = meta[key]
    case['user'] = (folder / 'user.md').read_text().strip()
    case['explanation'] = (folder / 'explanation.md').read_text().strip()
    case['code'] = (folder / 'code.cs').read_text().strip() + '\n'
    if (folder / 'broken.cs').exists():
        case['broken'] = {'code': (folder / 'broken.cs').read_text().strip() + '\n', 'expect': meta.get('broken_expect')}
        if meta.get('broken_error'):
            case['broken']['error'] = meta['broken_error']
    return case


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pack'); p.add_argument('folders', nargs='+'); p.add_argument('-o', '--output', required=True)
    p = sub.add_parser('lint'); p.add_argument('cases', nargs='+'); p.add_argument('--full', action='store_true')
    p = sub.add_parser('verify'); p.add_argument('cases', nargs='+'); p.add_argument('--tag', required=True)
    p.add_argument('--ids', nargs='*'); p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--timeout', type=int, default=300); p.add_argument('--receipt')
    p = sub.add_parser('assemble'); p.add_argument('--check', action='store_true')
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--base', type=Path, required=True, help='local hash-pinned base, tokenizer only; no model loading')
    args = ap.parse_args()
    if args.cmd == 'pack':
        folders = sorted({p.parent for f in args.folders for p in Path(f).rglob('meta.json')})
        cases = [pack(f) for f in folders]
        Path(args.output).write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases))
        print(f'packed {len(cases)} cases into {args.output}')
        return 0
    if args.cmd == 'lint':
        cases = [c for f in args.cases for c in load_cases(f)]
        report = lint(cases, args.full)
        for cid, problems in sorted(report.items()):
            for p in problems:
                print(f'{cid}: {p}')
        print(f'{len(cases)} cases, {len(report)} with problems')
        return 1 if report else 0
    if args.cmd == 'verify':
        cases = [c for f in args.cases for c in load_cases(f)]
        if args.ids:
            unknown = set(args.ids) - {c['id'] for c in cases}
            if unknown:
                ap.error('unknown case ids: ' + ', '.join(sorted(unknown)))
            cases = [c for c in cases if c['id'] in set(args.ids)]
        if args.receipt and Path(args.receipt).exists():
            ap.error('Use a new receipt path; existing evidence is preserved')
        try:
            receipt = verify(cases, args.tag, args.jobs, args.timeout)
        except (ValueError, RuntimeError) as error:
            ap.error(str(error))
        bad = {k: v['reasons'] for k, v in receipt['cases'].items() if not v['passed']}
        for k, reasons in sorted(bad.items()):
            print(f'FAIL {k}: ' + ' | '.join(reasons))
        print(f"{len(cases) - len(bad)}/{len(cases)} passed")
        if args.receipt:
            with Path(args.receipt).open('x') as output:
                output.write(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
        return 1 if bad else 0
    if args.cmd == 'assemble':
        cases = load_cases(DATA / 'cases.jsonl')
        problems = lint(cases, full=True)
        if problems:
            ap.error('Corpus not ready for training: ' + json.dumps(problems))
        receipt = json.loads(args.receipt.read_text())
        receipt_check(cases, receipt)
        bindings = json.loads((ROOT / 'release.json').read_text())['base']['files']
        for name, expected in bindings.items():
            path = (args.base / name).resolve()
            if not path.is_relative_to(args.base.resolve()) or sha(path.read_bytes()) != expected:
                ap.error('Base hash mismatch: ' + name)
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(args.base, local_files_only=True, trust_remote_code=False)
        files = assemble(cases, receipt, tokenizer)
        stale = []
        if not args.check:
            for split, text in files.items():
                path = DATA / f'{split}.jsonl'
                if path.is_symlink() or (path.exists() and path.read_text() != text):
                    ap.error('Existing partition differs; preserve it and create a new corpus version: ' + path.name)
        for split, text in files.items():
            path = DATA / f'{split}.jsonl'
            if args.check:
                if not path.exists() or path.read_text() != text:
                    stale.append(path.name)
            elif not path.exists():
                with path.open('x') as output:
                    output.write(text)
        if stale:
            print('stale: ' + ', '.join(stale))
            return 1
        return 0


if __name__ == '__main__':
    sys.exit(main())
