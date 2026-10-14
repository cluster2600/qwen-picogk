#!/usr/bin/env python3
"""Stage redacted experiment evidence without changing local originals or uploading it."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

SKIP_PARTS = {'bin', 'obj', '__pycache__', '.git', 'venv', '.venv', 'runtime', 'sdk',
              'packages', 'model', 'model7b', 'cache', '.cache'}
SKIP_SUFFIXES = {'.dll', '.dylib', '.pdb', '.pyc', '.nupkg', '.so', '.exe'}
TEXT_SUFFIXES = {'.json', '.jsonl', '.txt', '.log', '.md', '.py', '.csproj', '.xml', '.config'}


def is_text_member(name, data):
    """Share the text boundary across archive export and checkout privacy checks."""
    return (Path(name).suffix in TEXT_SUFFIXES | {'.cs'}
            or Path(name).name == 'qwen-picogk-am' or data.startswith(b'#!'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def safe_files(root):
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_PARTS or part == 'final.json' or part.startswith('final-')
               for part in relative.parts):
            continue
        if path.suffix in SKIP_SUFFIXES or path.name.startswith(('.env', 'credentials')):
            continue
        if path.suffix == '.safetensors' and not path.name.endswith('adapters.safetensors'):
            continue
        if path.name == 'picogk-am-150.zip':
            continue  # Its content is included directly, avoiding a duplicate nested archive.
        yield path


def scrub(text, replacements):
    for source, label in replacements:
        text = text.replace(source, label)
    # Remaining local home paths retain a unique label to prevent JSON-key collisions.
    return re.sub(r'/Users/[^\s"\x27,;<>\]\)]+',
                  lambda m: 'redacted-local-path-'+digest(m.group().encode())[:12], text)


def archive(path, roots, replacements):
    records = []
    with path.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, compresslevel=1) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|', format=tarfile.PAX_FORMAT) as output:
            for prefix, source in roots:
                files = [source] if source.is_file() else safe_files(source)
                for file in files:
                    relative = file.name if source.is_file() else str(file.relative_to(source))
                    public_name = prefix+'/'+relative
                    original = file.read_bytes()
                    public = original
                    if file.suffix == '.cs' or file.name.endswith('.jsonl') and 'responses' not in file.name:
                        assert b'/Users/' not in original, 'Private path in exact code/dataset: '+public_name
                    elif is_text_member(file.name, original):
                        public = scrub(original.decode('utf-8'), replacements).encode('utf-8')
                    info = tarfile.TarInfo(public_name)
                    info.size = len(public);info.mode = 0o644;info.mtime = 0
                    info.uid = info.gid = 0;info.uname = info.gname = ''
                    output.addfile(info, io.BytesIO(public))
                    records.append({'path': public_name, 'original_bytes': len(original),
                                    'public_bytes': len(public), 'original_sha256': digest(original),
                                    'public_sha256': digest(public), 'local_paths_redacted': public != original})
            index = json.dumps({'schema': 'picogk.am.full-evidence-export@1',
                'originals_immutable': True, 'final_contents_included': False,
                'path_redaction_only': True, 'csharp_dataset_geometry_adapter_tensor_bytes_exact': True,
                'files': records}, indent=2).encode()+b'\n'
            info = tarfile.TarInfo('export-index.json');info.size = len(index);info.mode = 0o644
            output.addfile(info, io.BytesIO(index))
    return {'asset': path.name, 'bytes': path.stat().st_size,
            'sha256': file_digest(path),
            'files': len(records), 'raw_payload_bytes': sum(r['original_bytes'] for r in records),
            'redacted_files': sum(r['local_paths_redacted'] for r in records),
            'export_index_sha256': digest(index), 'qualified_adapter': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--original150', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve();original = args.original150.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    replacements = [(str(original), 'original150'), (str(source), 'am-code'),
                    (str(source.parent), 'runtime'),
                    (str(source.parent.parent/'PicoGK'), 'picogk-runtime')]
    # No task/reference generator from evaluation is copied: it can reveal the sealed final.
    development = json.loads((source/'evaluation/development.json').read_text())['tasks']
    gold = [('evaluation/reference-validation/'+task['id'], source/'evaluation/reference-validation'/task['id'])
            for task in development]
    scan_roots = [('end-to-end', source/'end-to-end')]
    # This whole subtree contains development-only tasks, including preserved rejected registrations.
    teacher_roots = [('data/corrective-001', source/'data/corrective-001'),
                     ('data/corrective-002', source/'data/corrective-002')]
    # This snapshot publishes only explicitly identified completed, ineligible/rejected courses.
    rejected = ['smoke-003', 'original150-epoch2', 'corrective001-epoch3', 'header002-epoch1']
    completed = [('runs/'+name, source/'runs'/name) for name in rejected
                 if (source/'runs'/name/'training-receipt.json').is_file()]
    names = ['baseline-development', 'baseline-development-matched', 'baseline-scores-matched',
             'baseline-scores-matched-absolute', 'candidate-development-300', 'candidate-scan-300',
             'candidate-scores-300', 'scan-scores-300', 'candidate-development-corrective192',
             'candidate-scan-corrective192', 'candidate-scores-corrective192',
             'scan-scores-corrective192', 'candidate-development-header192',
             'candidate-scan-header192', 'candidate-scores-header192', 'scan-scores-header192',
             'baseline-development-7b', 'baseline-scores-7b', 'diagnostics']
    completed += [(name, source/name) for name in names if (source/name).exists()]
    logs = ['smoke-003', 'original150-epoch2', 'corrective001-epoch3', 'header002-epoch1',
            'baseline-development', 'baseline-development-matched', 'baseline-scores-matched',
            'baseline-scores-matched-absolute', 'candidate-development-300', 'candidate-scan-300',
            'candidate-scores-300', 'scan-scores-300', 'candidate-development-corrective192',
            'candidate-scan-corrective192', 'candidate-scores-corrective192', 'scan-scores-corrective192',
            'candidate-development-header192', 'candidate-scan-header192', 'candidate-scores-header192',
            'scan-scores-header192', 'baseline-development-7b', 'baseline-scores-7b',
            'qualification-rejected-300', 'qualification-rejected-corrective192', 'qualification-rejected-header192']
    completed += [('top-level-logs', source/(name+'.log')) for name in logs
                  if (source/(name+'.log')).is_file()]
    groups = [('original150-full-evidence.tar.gz', [('original150', original)]),
              ('corrective-teachers-full-evidence.tar.gz', teacher_roots),
              ('development-reference-full-evidence.tar.gz', gold+scan_roots),
              ('rejected-completed-courses-full-evidence.tar.gz', completed)]
    results = []
    for name, roots in groups:
        result = archive(args.output/name, roots, replacements)
        results.append(result);print(json.dumps(result), flush=True)
    manifest = {'schema': 'picogk.am.release-assets-staged@1',
        'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'staged_not_uploaded',
        'assets': results, 'ongoing_training_weights_copied': False,
        'final_task_contents_included': False, 'upstream_base_or_native_binaries_included': False,
        'all_adapter_assets_unqualified': True, 'manufacturing_authorized': False,
        'omitted': ['Upstream model payloads and binaries/SDK/packages/caches/compiler products.',
                    'Sealed final prompts, references, gold results and their author module.',
                    'Incomplete training course weights and its live log.']}
    (args.output/'assets.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
