"""Prospective Roslyn lexical policy; immutable v1 geometry engines remain unchanged."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / 'checker-profile-v2.json'
SCHEMA = 'picogk.am.checker-profile@2'
POLICY = 'roslyn-static-allowlist@2'
SCORE_SCHEMA = 'picogk.am.native-score@2'
DOTNET = Path(os.environ.get('QWEN_PICOGK_AM_DOTNET', str(ROOT / 'work/dotnet/dotnet')))
ROSLYN = DOTNET.parent / 'sdk/9.0.317/Roslyn/bincore'
LEXER = Path('evaluation/PolicyLexer/bin/Release/net9.0/PolicyLexer.dll')
PICO = Path(os.environ.get('QWEN_PICOGK_AM_PICO', str(ROOT / 'work/picogk-runtime')))
NATIVE_NAMES = ('PicoGK.dll', 'SkiaSharp.dll', 'libboost_iostreams.dylib', 'libboost_random.dylib',
    'libboost_regex.dylib', 'libicudata.78.dylib', 'liblzma.5.dylib', 'libzstd.1.dylib',
    'picogk.26.2.dylib', 'libicui18n.78.dylib', 'libicuuc.78.dylib')

# Closed dependency set: new files require a deliberate, prospectively reviewed profile revision.
# Final checker *source* is allowed; reserved final task bodies and references never are.
REQUIRED_FILES = frozenset({
    'evaluation/evaluate.py', 'end-to-end/evaluate.py', 'evaluation/Inspector.cs',
    'qualification.py', 'final_qualification.py', 'base_runtime.py', 'infer.py',
    'evaluation/development.json', 'evaluation/freeze.json',
    'end-to-end/development.json', 'end-to-end/freeze.json',
    'evaluation/policy_v2.py', 'evaluation/evaluate_v2.py', 'end-to-end/evaluate_v2.py',
    'evaluation/PolicyLexer/Program.cs', 'evaluation/PolicyLexer/PolicyLexer.csproj',
    str(LEXER), 'evaluation/PolicyLexer/bin/Release/net9.0/PolicyLexer.deps.json',
    'evaluation/PolicyLexer/bin/Release/net9.0/PolicyLexer.runtimeconfig.json',
    'evaluation/PolicyLexer/bin/Release/net9.0/Microsoft.CodeAnalysis.dll',
    'evaluation/PolicyLexer/bin/Release/net9.0/Microsoft.CodeAnalysis.CSharp.dll',
    'qualification_v2.py', 'final_qualification_v2.py', 'infer_v2.py',
    'sealed-reference-hashes-v2.json', 'evaluation/inspector-build/Program.cs',
    'evaluation/inspector-build/bin/Release/net9.0/Inspector.dll',
    'evaluation/inspector-build/bin/Release/net9.0/Inspector.deps.json',
    'evaluation/inspector-build/bin/Release/net9.0/Inspector.runtimeconfig.json',
} | {'evaluation/inspector-build/bin/Release/net9.0/' + name for name in NATIVE_NAMES})
EXTERNAL_FILES = frozenset({str(DOTNET), str(ROSLYN / 'Microsoft.CodeAnalysis.dll'),
    str(ROSLYN / 'Microsoft.CodeAnalysis.CSharp.dll')} | {str(PICO / name) for name in NATIVE_NAMES})
NAMESPACES = frozenset({'System', 'System.IO', 'System.Linq', 'System.Numerics',
    'System.Globalization', 'System.Text.Json', 'System.Collections.Generic', 'PicoGK'})
BANNED = frozenset(('unsafe dynamic extern DllImport LibraryImport Reflection Activator AppDomain '
    'Assembly Process Environment Registry Marshal GCHandle Delegate Thread Task HttpClient WebClient '
    'Socket TcpClient UdpClient FileStream BinaryReader BinaryWriter StreamReader StreamWriter ConsoleKey '
    'GetType typeof GetMethod GetField GetProperty Delete Move Copy EnumerateFiles GetFiles GetDirectories '
    'SetCurrentDirectory ReadAllBytes WriteAllBytes OpenRead OpenWrite OpenText ReadAllText '
    'GetEnvironmentVariable Exit FailFast LoadFrom LoadFile GetService GetUninitializedObject').split())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate checker profile key')
        result[key] = value
    return result


def _regular_path(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file():
        raise ValueError('checker dependency must be an existing regular file')
    return path


def _reserved_path(path):
    return any(part == 'final' or part.startswith('final-') or part == 'final.json'
               for part in path.parts)


def verify_checker_profile(path=None):
    """Verify a closed manifest against its independent SHA anchor before any task read.

    An explicit profile path permits isolated fake fixtures: its parent is the fixture root.
    It never changes the production default or permits an unanchored manifest.
    """
    profile_path = Path(path) if path is not None else PROFILE_PATH
    profile_path = profile_path.absolute()
    if '..' in profile_path.parts or _reserved_path(profile_path):
        raise ValueError('reserved final paths cannot be checker profiles')
    _regular_path(profile_path)
    anchor = _regular_path(profile_path.with_suffix('.sha256'))
    expected = anchor.read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('checker profile SHA anchor must contain exactly one SHA256')
    profile_hash = digest(profile_path)
    if profile_hash != expected:
        raise ValueError('checker profile SHA anchor mismatch')
    profile = json.loads(profile_path.read_text(), object_pairs_hook=_no_duplicate_keys)
    if (not isinstance(profile, dict) or set(profile) != {'schema', 'policy', 'files', 'external_files'}
            or profile['schema'] != SCHEMA or profile['policy'] != POLICY
            or not isinstance(profile['files'], dict) or set(profile['files']) != REQUIRED_FILES
            or not isinstance(profile['external_files'], dict)
            or set(profile['external_files']) != EXTERNAL_FILES):
        raise ValueError('checker profile schema, policy or closed dependency set mismatch')
    base = profile_path.parent.resolve()
    for name, expected_hash in profile['files'].items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or str(relative) != name or '..' in relative.parts
                or '\\' in name or _reserved_path(relative)):
            raise ValueError('unsafe or reserved checker dependency path')
        dependency = _regular_path(base / name)
        if not dependency.resolve().is_relative_to(base):
            raise ValueError('checker dependency escapes the profile root')
        if not isinstance(expected_hash, str) or not re.fullmatch('[0-9a-f]{64}', expected_hash):
            raise ValueError('invalid checker dependency SHA256')
        if digest(dependency) != expected_hash:
            raise ValueError('checker dependency changed: ' + name)
    for name, expected_hash in profile['external_files'].items():
        dependency = _regular_path(Path(name))
        if (not dependency.is_absolute() or not isinstance(expected_hash, str)
                or not re.fullmatch('[0-9a-f]{64}', expected_hash)
                or digest(dependency) != expected_hash):
            raise ValueError('installed checker runtime changed: ' + name)
    if digest(base / 'evaluation/Inspector.cs') != digest(base / 'evaluation/inspector-build/Program.cs'):
        raise ValueError('cached Inspector source differs from frozen Inspector.cs')
    return {'checker_profile_sha256': profile_hash, 'profile': profile}


def verify_reference_artifacts(task, module, allow_final=False):
    """Blindly verify only the selected task's already validated native reference bytes.

    The final caller must validate the current development selection before setting
    allow_final. Loading this checksum manifest never loads a final task or answer.
    """
    if module not in ('evaluation', 'end-to-end'):
        raise ValueError('unknown reference module')
    task_id = task['id']
    if (not re.fullmatch(r'(?:development|final)-[A-Za-z0-9-]+', task_id)
            or (task_id.startswith('final-') and not allow_final)):
        raise ValueError('reserved or invalid reference task ID')
    manifest = json.loads((ROOT / 'sealed-reference-hashes-v2.json').read_text(),
                          object_pairs_hook=_no_duplicate_keys)
    if (set(manifest) != {'schema', 'preparation', 'files'}
            or manifest['schema'] != 'picogk.am.sealed-reference-hashes@2'
            or manifest['preparation'] != 'blind_streaming_sha256_no_semantic_final_access'
            or not isinstance(manifest['files'], dict)):
        raise ValueError('invalid sealed reference checksum manifest')
    reference = PurePosixPath(task['reference'])
    if (reference.is_absolute() or '..' in reference.parts or '\\' in str(reference)
            or len(reference.parts) != 2 or reference.parts[0] != 'references'
            or reference.name != task_id + '.cs'):
        raise ValueError('invalid frozen reference source path')
    gold = PurePosixPath(module) / 'reference-validation' / task_id
    required = [str(PurePosixPath(module) / reference), str(gold / 'result.json')]
    # Some historical evaluation caches retain only authored source + native artifacts.
    # Bind an actual compiled source copy when one was retained; never invent that proof.
    if str(gold / 'Program.cs') in manifest['files']:
        required.append(str(gold / 'Program.cs'))
    if task['kind'] != 'refusal':
        required.extend(str(gold / 'inspection' / name) for name in ('native.json', 'occupancy.bin'))
    for alternate in task['oracle'].get('additional_inputs', []):
        name = Path(alternate['input']).stem
        if not re.fullmatch('[A-Za-z0-9_-]+', name):
            raise ValueError('invalid frozen alternate input name')
        if task['kind'] != 'refusal':
            required.extend(str(gold / 'additional-inputs' / name / 'inspection' / filename)
                            for filename in ('native.json', 'occupancy.bin'))
    for name in required:
        expected = manifest['files'].get(name)
        # The retained evaluation cache intentionally aliases reviewed r9 case folders.
        # Resolve these historical aliases inside AM, then authenticate the actual bytes.
        artifact = (ROOT / name).resolve()
        if (not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)
                or not artifact.is_relative_to(ROOT.resolve())
                or digest(_regular_path(artifact)) != expected):
            raise ValueError('frozen native reference changed: ' + name)
    return True


def score_metadata(binding):
    return {'checker_profile_sha256': binding['checker_profile_sha256'], 'checker_policy': POLICY}


def lexer_facts(code):
    """Inspect source with the trusted helper; this does not compile or execute source."""
    if not isinstance(code, str) or len(code) > 180000:
        raise ValueError('bounded C# required')
    env = {**os.environ, 'DOTNET_ROOT': str(DOTNET.parent), 'DOTNET_EnableDiagnostics': '0',
           'DOTNET_CLI_TELEMETRY_OPTOUT': '1'}
    try:
        result = subprocess.run([str(DOTNET), str(ROOT / LEXER)], input=code,
            encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
            cwd=ROOT / 'evaluation/PolicyLexer', env=env, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('trusted Roslyn policy inspection failed') from exc
    if result.returncode != 0 or len(result.stdout) > 4000000:
        raise ValueError('trusted Roslyn policy inspection failed')
    try:
        facts = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError('invalid trusted Roslyn policy response') from exc
    if facts.get('schema') != 'picogk.am.policy-lexer@2':
        raise ValueError('unexpected trusted Roslyn policy schema')
    return facts


def check_facts(facts):
    """Apply the v1 API boundary to actual Roslyn code tokens and literal values."""
    if facts['parse_errors']:
        raise ValueError('C# syntax errors in trusted policy inspection')
    if facts['escaped_identifier'] or facts['preprocessor']:
        raise ValueError('escaped identifiers/preprocessor forbidden')
    if facts['non_ascii_executable']:
        raise ValueError('non-ASCII executable identifiers forbidden')
    if any(name not in NAMESPACES for name in facts['using_names']):
        raise ValueError('namespace outside static allowlist')
    if BANNED.intersection(facts['identifiers_and_keywords']):
        raise ValueError('operation/type outside static allowlist')
    for name in facts['system_qualified_names']:
        if not any(name == namespace or name.startswith(namespace + '.')
                   for namespace in NAMESPACES if namespace != 'System'):
            raise ValueError('fully qualified System type outside static allowlist')
    if facts['aliases_or_global'] or facts['namespace_system']:
        raise ValueError('aliases/global namespace escape forbidden')
    if any(re.search(r'^(?:/|~|[A-Za-z]:\\)|\.\./|\.\.\\', value)
           for value in facts['string_values']):
        raise ValueError('absolute or parent-relative paths forbidden')
    if not facts['has_main']:
        raise ValueError('complete Main(string[] args) required')
    return True


def static_gate(code, profile_path=None, expected_profile_sha256=None):
    binding = verify_checker_profile(profile_path)
    if expected_profile_sha256 is not None and binding['checker_profile_sha256'] != expected_profile_sha256:
        raise ValueError('checker profile changed during evaluation')
    return check_facts(lexer_facts(code))


def extract(response, profile_path=None, expected_profile_sha256=None):
    matches = re.findall(r'```(?:csharp|cs|C#)\s*\n(.*?)```', response, re.S)
    if len(matches) != 1:
        raise ValueError('exactly one complete C# code fence required')
    code = matches[0].strip() + '\n'
    static_gate(code, profile_path, expected_profile_sha256)
    return code
