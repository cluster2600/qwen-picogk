#!/usr/bin/env python3
"""Download one anonymous, pinned public model copy; never load its tensors."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
DESTINATION = ROOT / 'model7b'
REPOSITORY = 'mlx-community/Qwen2.5-Coder-7B-Instruct-4bit'
REVISION = '019cc73c45c770444708a6dd8690c66243cc5c80'
WEIGHT_SHA256 = '56a3d94706833f753e6c6b47ea57af8ef638cd8cc1d74eca1142ba640b26060e'
NAMES = ('added_tokens.json', 'config.json', 'merges.txt', 'model.safetensors.index.json',
         'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json',
         'model.safetensors')


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git_blob_digest(path, size):
    result = hashlib.sha1(('blob ' + str(size) + '\0').encode())
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main():
    assert not DESTINATION.exists(), 'Preserve the existing destination; review a failed attempt explicitly.'
    assert not (ROOT / 'model7b-manifest.json').exists(), 'Preserve the existing manifest.'
    # These are public requests only. token=False takes precedence over saved tokens.
    os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1',
                      HF_HUB_DISABLE_XET='1', HF_HUB_OFFLINE='0')
    from huggingface_hub import get_hf_file_metadata, hf_hub_url
    from huggingface_hub.utils import build_hf_headers
    headers = build_hf_headers(token=False, library_name='picogk-pinned-model-audit')
    assert not any(name.lower() == 'authorization' for name in headers)
    api = 'https://huggingface.co/api/models/' + REPOSITORY + '/revision/' + REVISION + '?blobs=true'
    with urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=30) as response:
        source_bytes = response.read(250000)
    source = json.loads(source_bytes)
    assert source['sha'] == REVISION and source['private'] is False and source['gated'] is False
    assert source['cardData']['license'] == 'apache-2.0'
    remote = {entry['rfilename']: entry for entry in source['siblings'] if entry['rfilename'] in NAMES}
    assert set(remote) == set(NAMES)
    assert remote['model.safetensors']['lfs']['sha256'] == WEIGHT_SHA256
    total = sum(remote[name]['size'] for name in NAMES)
    free = shutil.disk_usage(ROOT).free
    assert free >= total + 2 * 1024**3, 'Need payload space plus 2 GiB reserve.'
    DESTINATION.mkdir()
    metadata = DESTINATION / '.download-metadata'
    metadata.mkdir()
    (metadata / 'source-api.json').write_bytes(source_bytes)
    protocol = {'schema': 'picogk.am.public-model-download@1', 'started_at_utc': now(),
                'repository': REPOSITORY, 'revision': REVISION, 'license': 'apache-2.0',
                'anonymous': True, 'token_argument': False, 'implicit_tokens_disabled': True,
                'weight_loading': False, 'gpu_used': False, 'single_payload_copy': True,
                'expected_payload_bytes': total, 'free_bytes_before': free,
                'download_script_sha256': file_digest(Path(__file__))}
    save(metadata / 'protocol.json', protocol)
    files = {}
    current_name = None
    start = time.monotonic()
    try:
        for current_name in NAMES:
            entry = remote[current_name]
            url = hf_hub_url(REPOSITORY, current_name, revision=REVISION)
            head = get_hf_file_metadata(url, token=False)
            expected_etag = entry.get('lfs', {}).get('sha256', entry['blobId'])
            assert head.commit_hash == REVISION and head.etag == expected_etag
            assert head.size == entry['size']
            save(metadata / (current_name + '.remote.json'), {
                'repository': REPOSITORY, 'revision': REVISION, 'filename': current_name,
                'size_bytes': entry['size'], 'git_blob_sha1': entry['blobId'],
                'lfs_sha256': entry.get('lfs', {}).get('sha256'),
                'head_etag': head.etag, 'head_commit_hash': head.commit_hash,
                'anonymous': True, 'token_argument': False})
            partial = DESTINATION / (current_name + '.partial')
            destination = DESTINATION / current_name
            assert not partial.exists() and not destination.exists()
            print(json.dumps({'file': current_name, 'status': 'downloading', 'expected_bytes': entry['size']}), flush=True)
            downloaded = 0
            last_progress = time.monotonic()
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response, partial.open('xb') as stream:
                while block := response.read(4 * 1024 * 1024):
                    stream.write(block)
                    downloaded += len(block)
                    if downloaded > entry['size']:
                        raise ValueError('Remote file exceeds its registered size.')
                    if time.monotonic() - last_progress >= 15:
                        print(json.dumps({'file': current_name, 'downloaded_bytes': downloaded,
                                          'expected_bytes': entry['size']}), flush=True)
                        last_progress = time.monotonic()
                stream.flush()
                os.fsync(stream.fileno())
            assert downloaded == entry['size'] and partial.stat().st_size == entry['size']
            local_sha256 = file_digest(partial)
            if entry.get('lfs'):
                assert local_sha256 == entry['lfs']['sha256'] == WEIGHT_SHA256
                # Verify the remote LFS pointer's Git identity separately from payload SHA.
                pointer = ('version https://git-lfs.github.com/spec/v1\n'
                           + 'oid sha256:' + local_sha256 + '\n'
                           + 'size ' + str(downloaded) + '\n').encode()
                assert len(pointer) == entry['lfs']['pointerSize']
                pointer_sha1 = hashlib.sha1(('blob ' + str(len(pointer)) + '\0').encode() + pointer).hexdigest()
                assert pointer_sha1 == entry['blobId']
                actual_git = pointer_sha1
                identity = 'lfs_sha256_and_git_pointer_sha1'
            else:
                actual_git = git_blob_digest(partial, downloaded)
                assert actual_git == entry['blobId']
                identity = 'git_blob_sha1'
            partial.rename(destination)  # Same-volume rename; no second weight copy.
            files[current_name] = {'size_bytes': downloaded, 'sha256': local_sha256,
                                   'remote_git_blob_sha1': entry['blobId'],
                                   'verified_git_blob_sha1': actual_git,
                                   'remote_lfs_sha256': entry.get('lfs', {}).get('sha256'),
                                   'verified_identity': identity}
            save(metadata / 'verified-files.json', files)
            print(json.dumps({'file': current_name, 'status': 'verified', 'sha256': local_sha256,
                              'size_bytes': downloaded}), flush=True)
        assert set(files) == set(NAMES)
        assert not list(DESTINATION.glob('*.partial'))
        manifest = {'schema': 'picogk.am.base-model-manifest@1', 'status': 'verified',
                    'created_at_utc': now(), 'repository': REPOSITORY, 'revision': REVISION,
                    'license': 'apache-2.0', 'license_source': 'https://huggingface.co/' + REPOSITORY + '/tree/' + REVISION,
                    'upstream_repository': 'Qwen/Qwen2.5-Coder-7B-Instruct',
                    'model_directory': 'model7b', 'total_payload_bytes': total,
                    'model_files_sha256': {name: entry['sha256'] for name, entry in files.items()},
                    'files': files, 'source_metadata_sha256': file_digest(metadata / 'source-api.json'),
                    'download_protocol_sha256': file_digest(metadata / 'protocol.json'),
                    'weight_loading': False, 'gpu_used': False,
                    'manufacturing_authorized': False}
        path = ROOT / 'model7b-manifest.json'
        save(path, manifest)
        receipt = {'schema': 'picogk.am.public-model-download-receipt@1', 'status': 'completed',
                   'completed_at_utc': now(), 'files': len(files), 'payload_bytes': total,
                   'elapsed_seconds': time.monotonic() - start,
                   'manifest_sha256': file_digest(path), 'free_bytes_after': shutil.disk_usage(ROOT).free,
                   'weight_loading': False, 'gpu_used': False, 'anonymous': True}
        save(metadata / 'receipt.json', receipt)
        print(json.dumps(receipt), flush=True)
        return 0
    except Exception as error:
        # Preserve partial bytes and verified files; do not expose signed redirect URLs.
        failure = {'status': 'failed', 'failed_at_utc': now(), 'file': current_name,
                   'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None),
                   'verified_files': len(files), 'partial_files_preserved': [p.name for p in DESTINATION.glob('*.partial')]}
        save(metadata / 'failure.json', failure)
        print(json.dumps(failure), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
