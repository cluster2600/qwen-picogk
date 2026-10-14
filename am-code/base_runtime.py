"""Verify a pinned nine-file base without importing MLX or accessing final tasks."""
import hashlib
import json
from pathlib import Path
import re

BASE_NAMES = frozenset({'model.safetensors', 'added_tokens.json', 'config.json',
    'model.safetensors.index.json', 'special_tokens_map.json', 'tokenizer.json',
    'tokenizer_config.json', 'vocab.json', 'merges.txt'})
PROFILE_KEYS = frozenset({'schema', 'model_directory', 'repository', 'revision', 'model_files_sha256'})
BINDING_KEYS = frozenset({'base_profile_sha256', 'model_files_sha256'})


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate base profile field: ' + key)
        result[key] = value
    return result


def reserved(work, path):
    path = path.resolve()
    evaluation = work.resolve() / 'evaluation'
    return (path == (evaluation / 'final.json').resolve()
            or (path.is_relative_to((evaluation / 'references').resolve())
                and path.name.startswith('final-')))


def contained(root, value):
    value = Path(value)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Base model paths must be relative to their fixed root.')
    resolved = (root / value).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Base model path escaped its fixed root.')
    return resolved


def verify_base(work, profile=None, runtime=None, expected_profile_sha256=None):
    """Return directory, weight identity and optional explicit-profile receipt fields."""
    work = Path(work).resolve()
    runtime = Path(runtime).resolve() if runtime is not None else work.parent
    binding = {}
    if profile is None:
        if expected_profile_sha256 is not None:
            raise ValueError('A base profile path is required with its expected hash.')
        manifest = work / 'base-manifest.json'
        value = json.loads(manifest.read_text(), object_pairs_hook=unique)
        directory = (runtime / 'model').resolve(strict=True)
        if not directory.is_relative_to(runtime):
            raise ValueError('Default model escaped the retained runtime.')
    else:
        supplied = Path(profile)
        path = supplied.resolve(strict=True) if supplied.is_absolute() else contained(work, supplied)
        if not path.is_relative_to(work) or reserved(work, path):
            raise ValueError('Base profile must remain inside the AM root and outside reserved tasks.')
        if not path.is_file():
            raise ValueError('Base profile must be a JSON file.')
        profile_hash = digest(path)
        if expected_profile_sha256 is not None and profile_hash != expected_profile_sha256:
            raise ValueError('Base profile SHA-256 mismatch.')
        value = json.loads(path.read_text(), object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != PROFILE_KEYS
                or value['schema'] != 'picogk.am.base-profile@1'
                or not isinstance(value['repository'], str) or not value['repository'].strip()
                or not isinstance(value['revision'], str) or re.fullmatch(r'[0-9a-f]{40}', value['revision']) is None):
            raise ValueError('Complete pinned base profile required.')
        directory = contained(work, value['model_directory'])
        if reserved(work, directory) or not directory.is_dir():
            raise ValueError('Contained base model directory required.')
        binding['base_profile_sha256'] = profile_hash
    hashes = value['model_files_sha256']
    if (not isinstance(hashes, dict) or set(hashes) != BASE_NAMES
            or any(not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{64}', v) is None for v in hashes.values())):
        raise ValueError('Exactly nine valid base/tokenizer SHA-256 values required.')
    for name, expected in hashes.items():
        path = contained(directory, name)
        if reserved(work, path) or not path.is_file() or digest(path) != expected:
            raise ValueError('Pinned base/tokenizer file changed: ' + name)
    # MLX loads model*.safetensors, so unpinned additional shards must fail closed.
    if {p.name for p in directory.glob('model*.safetensors')} != {'model.safetensors'}:
        raise ValueError('Unpinned additional base weight files are forbidden.')
    config = json.loads((directory / 'config.json').read_text(), object_pairs_hook=unique)
    if not isinstance(config, dict) or config.get('model_file') is not None:
        raise ValueError('Unpinned custom model code is forbidden.')
    if binding:
        binding['model_files_sha256'] = dict(hashes)
    return {'directory': directory, 'base_weights_sha256': hashes['model.safetensors'],
            'model_files_sha256': dict(hashes), 'binding': binding}


def verify_evidence(base, *records):
    """Reject mixed default/explicit identities, even when weight hashes coincide."""
    for record in records:
        if not isinstance(record, dict) or record.get('base_weights_sha256') != base['base_weights_sha256']:
            raise ValueError('Evidence describes a different base model.')
        if base['binding']:
            if any(record.get(key) != value for key, value in base['binding'].items()):
                raise ValueError('Evidence describes a different or missing explicit base profile.')
        elif BINDING_KEYS.intersection(record):
            raise ValueError('Explicit base evidence cannot be used with the legacy default.')
