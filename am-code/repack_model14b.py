#!/usr/bin/env python3
"""Repack pinned safetensors shards by copying bytes; never load or convert tensors."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile

ROOT = Path(__file__).resolve().parent
REPOSITORY = 'mlx-community/Qwen2.5-Coder-14B-Instruct-4bit'
REVISION = '29efdbab55a161237ab1e432a3abaf6c7ae2b477'
SHARDS = {
    'model-00001-of-00002.safetensors': (5353840273, '784b0c89d3e006f49cb8547aba1f2f4e99b365ab4380cf202655ca04c87d7ac3'),
    'model-00002-of-00002.safetensors': (2955653960, 'a1b7516f1926070177601698661494dfc68c2de1d98e7c43ba910a0d1d7dfbbe'),
}
SMALL = ('added_tokens.json', 'config.json', 'merges.txt', 'special_tokens_map.json',
         'tokenizer.json', 'tokenizer_config.json', 'vocab.json')
WIDTH = {'BOOL':1, 'I8':1, 'U8':1, 'I16':2, 'U16':2, 'F16':2, 'BF16':2,
         'I32':4, 'U32':4, 'F32':4, 'I64':8, 'U64':8, 'F64':8,
         'F8_E4M3':1, 'F8_E5M2':1, 'F8_E4M3FN':1}
CHUNK = 16 * 1024 * 1024


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key: ' + key)
        value[key] = item
    return value


def load_json(data):
    return json.loads(data, object_pairs_hook=unique_object)


def header(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('A regular source file is required.')
    size = path.stat().st_size
    with path.open('rb') as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise ValueError('Truncated safetensors prefix.')
        length = struct.unpack('<Q', prefix)[0]
        if length == 0 or length > 64 * 1024 * 1024 or 8 + length > size:
            raise ValueError('Invalid bounded safetensors header size.')
        raw = handle.read(length)
    fields = load_json(raw)
    if not isinstance(fields, dict):
        raise ValueError('A safetensors header must be an object.')
    metadata = fields.get('__metadata__', {})
    if not isinstance(metadata, dict) or any(not isinstance(v, str) for v in metadata.values()):
        raise ValueError('Invalid string metadata.')
    base = 8 + length
    tensors = {}
    for name, field in fields.items():
        if name == '__metadata__':
            continue
        if not name or not isinstance(field, dict) or set(field) != {'dtype', 'shape', 'data_offsets'}:
            raise ValueError('Invalid tensor header fields.')
        dtype, shape, offsets = field['dtype'], field['shape'], field['data_offsets']
        if not isinstance(dtype, str) or dtype not in WIDTH or not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
            raise ValueError('Invalid tensor dtype or shape.')
        if not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets):
            raise ValueError('Invalid tensor offsets.')
        start, end = offsets
        if not 0 <= start <= end <= size - base or end - start != math.prod(shape) * WIDTH[dtype]:
            raise ValueError('Tensor byte count/range disagrees with dtype and shape.')
        tensors[name] = {'dtype':dtype, 'shape':shape, 'start':start, 'end':end}
    cursor = 0
    for field in sorted(tensors.values(), key=lambda f: (f['start'], f['end'])):
        if field['start'] != cursor:
            raise ValueError('Overlapping or uncovered source tensor payload.')
        cursor = field['end']
    if not tensors or cursor != size - base:
        raise ValueError('Empty tensors or unclaimed payload bytes.')
    return base, tensors, metadata


def range_digest(path, position, count):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        handle.seek(position)
        while count:
            data = handle.read(min(count, CHUNK))
            if not data:
                raise ValueError('Truncated tensor payload.')
            result.update(data);count -= len(data)
    return result.hexdigest()


def semantic_digest(records):
    canonical = [{'name':name, 'dtype':r['dtype'], 'shape':r['shape'],
                  'bytes':r['bytes'], 'payload_sha256':r['payload_sha256']}
                 for name, r in sorted(records.items())]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def merge(shards, output):
    records = {};common_metadata = None
    for path in shards:
        base, tensors, metadata = header(path)
        if common_metadata is None:
            common_metadata = metadata
        elif metadata != common_metadata:
            raise ValueError('Conflicting shard metadata.')
        for name, tensor in tensors.items():
            if name in records:
                raise ValueError('Tensor-name collision between shards: ' + name)
            records[name] = {**tensor, 'path':path, 'source_base':base}
    merged = {'__metadata__':common_metadata};cursor = 0
    for name, tensor in sorted(records.items()):
        count = tensor['end'] - tensor['start']
        merged[name] = {'dtype':tensor['dtype'], 'shape':tensor['shape'], 'data_offsets':[cursor,cursor+count]}
        tensor['merged_start'] = cursor;cursor += count
    encoded = json.dumps(merged, ensure_ascii=True, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 8)
    copied = {}
    with output.open('xb') as destination:
        destination.write(struct.pack('<Q', len(encoded)));destination.write(encoded)
        for name, tensor in sorted(records.items()):
            remaining = tensor['end'] - tensor['start'];hasher = hashlib.sha256()
            with tensor['path'].open('rb') as source:
                source.seek(tensor['source_base'] + tensor['start'])
                while remaining:
                    data = source.read(min(remaining, CHUNK))
                    if not data:
                        raise ValueError('Truncated source while copying.')
                    destination.write(data);hasher.update(data);remaining -= len(data)
            copied[name] = {'dtype':tensor['dtype'], 'shape':tensor['shape'],
                            'bytes':tensor['end']-tensor['start'], 'payload_sha256':hasher.hexdigest(),
                            'upstream_file':tensor['path'].name, 'upstream_data_offsets':[tensor['start'],tensor['end']],
                            'merged_data_offsets':merged[name]['data_offsets']}
    base, actual, metadata = header(output)
    if set(actual) != set(records) or metadata != common_metadata:
        raise ValueError('Merged tensor/header identity changed.')
    checked = {}
    for name, field in actual.items():
        checksum = range_digest(output, base+field['start'], field['end']-field['start'])
        record = copied[name]
        if field['dtype'] != record['dtype'] or field['shape'] != record['shape'] or checksum != record['payload_sha256']:
            raise ValueError('Merged tensor semantic payload changed.')
        checked[name] = {**record, 'payload_sha256':checksum}
    if semantic_digest(copied) != semantic_digest(checked):
        raise ValueError('Canonical tensor semantic digest changed.')
    return copied, semantic_digest(copied)


def self_check():
    def fake(path, fields, payload, padded=True):
        encoded = json.dumps(fields, separators=(',', ':')).encode()
        if padded:encoded += b' ' * (-len(encoded) % 8)
        path.write_bytes(struct.pack('<Q',len(encoded))+encoded+payload)
    def rejects(call):
        try:call()
        except (ValueError, FileExistsError):return
        raise AssertionError('Malformed fixture was accepted.')
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp);a=folder/'a.safetensors';b=folder/'b.safetensors'
        fake(a,{'__metadata__':{'format':'mlx'},'left':{'dtype':'BF16','shape':[2],'data_offsets':[0,4]}},b'\x00\x00\x01\x00')
        fake(b,{'__metadata__':{'format':'mlx'},'right':{'dtype':'U32','shape':[1],'data_offsets':[0,4]}},b'\x01\x02\x03\x04')
        records, canonical=merge([a,b],folder/'merged.safetensors')
        assert len(records)==2 and canonical==semantic_digest(records)
        assert records['left']['payload_sha256']==hashlib.sha256(b'\x00\x00\x01\x00').hexdigest()
        unpadded=folder/'unpadded.safetensors'
        fake(unpadded,{'z':{'dtype':'U32','shape':[1],'data_offsets':[0,4]}},b'1234',padded=False)
        base,fields,_=header(unpadded)
        assert (base-8)%8 != 0 and fields['z']['end']==4
        rejects(lambda:load_json('{"x":1,"x":2}'))
        rejects(lambda:merge([a,a],folder/'collision.safetensors'))
        rejects(lambda:merge([a,b],folder/'merged.safetensors'))
        for name,field,payload in [('dtype',{'dtype':'FANTASY','shape':[1],'data_offsets':[0,4]},b'1234'),
                                   ('shape',{'dtype':'U32','shape':[True],'data_offsets':[0,4]},b'1234'),
                                   ('range',{'dtype':'U32','shape':[1],'data_offsets':[0,8]},b'1234'),
                                   ('hole',{'dtype':'U32','shape':[1],'data_offsets':[4,8]},b'12345678')]:
            path=folder/(name+'.safetensors');fake(path,{'bad':field},payload);rejects(lambda:header(path))
        bad=folder/'overlap.safetensors';fake(bad,{'a':{'dtype':'U32','shape':[1],'data_offsets':[0,4]},'b':{'dtype':'U32','shape':[1],'data_offsets':[0,4]}},b'1234');rejects(lambda:header(bad))
    print('11 lossless-copy and malformed-header assertions passed; no model/MLX/GPU used.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'model14b-upstream')
    parser.add_argument('--output',type=Path,default=ROOT/'model14b')
    parser.add_argument('--receipt',type=Path,default=ROOT/'diagnostics/model14b-preparation/repack-receipt.json')
    parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    if args.self_check:
        self_check();return
    source=args.source.resolve();output=args.output.resolve();receipt=args.receipt.resolve()
    download_path=ROOT/'diagnostics/model14b-preparation/download-receipt.json'
    downloaded=load_json(download_path.read_bytes())
    if downloaded['status']!='verified' or downloaded['repository']!=REPOSITORY or downloaded['revision']!=REVISION or downloaded['license']!='apache-2.0':
        raise ValueError('Pinned upstream download metadata mismatch.')
    inputs={}
    for name in (*SMALL,'model.safetensors.index.json',*SHARDS):
        path=source/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('A regular upstream source file is required.')
        checksum=digest(path)
        if path.stat().st_size!=downloaded['files'][name]['bytes'] or checksum!=downloaded['files'][name]['sha256']:
            raise ValueError('Upstream source differs from verified download.')
        if name in SHARDS and (path.stat().st_size,checksum)!=SHARDS[name]:
            raise ValueError('Pinned shard size or LFS SHA mismatch.')
        inputs[name]={'bytes':path.stat().st_size,'sha256':checksum}
    index=load_json((source/'model.safetensors.index.json').read_bytes())
    if set(index)!= {'metadata','weight_map'} or not isinstance(index['weight_map'],dict):
        raise ValueError('Unexpected safetensors index schema.')
    tensors={}
    for name in SHARDS:
        _,fields,_=header(source/name)
        for tensor in fields:
            if tensor in tensors or index['weight_map'].get(tensor)!=name:
                raise ValueError('Duplicate tensor or shard/index mismatch.')
            tensors[tensor]=name
    if set(index['weight_map'])!=set(tensors):
        raise ValueError('Index has missing/extra tensors.')
    if output.exists() or receipt.exists() or (ROOT/'base-profile-14b.json').exists():
        raise FileExistsError('Preserve prior output, receipt and profile.')
    output.mkdir(parents=True)
    records,canonical=merge([source/name for name in SHARDS],output/'model.safetensors')
    for name in SMALL:shutil.copyfile(source/name,output/name)
    remapped={'metadata':index['metadata'],'weight_map':{name:'model.safetensors' for name in index['weight_map']}}
    (output/'model.safetensors.index.json').write_text(json.dumps(remapped,indent=2)+'\n')
    names=(*SMALL,'model.safetensors.index.json','model.safetensors')
    if {p.name for p in output.iterdir()}!=set(names) or any(p.is_symlink() for p in output.iterdir()):
        raise ValueError('Runtime output must contain exactly nine regular files.')
    for name in SMALL:
        if digest(output/name)!=inputs[name]['sha256']:raise ValueError('Small upstream file changed.')
    hashes={name:digest(output/name) for name in names}
    profile={'schema':'picogk.am.base-profile@1','model_directory':str(output.relative_to(ROOT)),
             'repository':REPOSITORY,'revision':REVISION,'model_files_sha256':hashes}
    result={'schema':'picogk.am.lossless-model-repack@1','status':'verified','completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'repository':REPOSITORY,'revision':REVISION,'license':'apache-2.0','upstream_files':inputs,'output_files_sha256':hashes,
            'tensor_count':len(records),'tensor_records':records,'canonical_tensor_semantic_sha256':canonical,
            'all_tensor_dtypes_shapes_payloads_exact':True,'config_tokenizer_files_unchanged':True,'index_change':'Only shard filenames remapped to model.safetensors; tensor keys and metadata preserved.',
            'download_receipt_sha256':digest(download_path),'repacker_source_sha256':digest(Path(__file__)),
            'profile_sha256':hashlib.sha256((json.dumps(profile,indent=2)+'\n').encode()).hexdigest(),
            'model_loaded':False,'mlx_imported':False,'gpu_used':False,'dtype_conversion':False,'dequantization':False,
            'manufacturing_authorized':False,'upstream_preserved':True}
    with receipt.open('x') as handle:handle.write(json.dumps(result,indent=2)+'\n')
    with (ROOT/'base-profile-14b.json').open('x') as handle:handle.write(json.dumps(profile,indent=2)+'\n')
    print(json.dumps({'status':'verified','tensor_count':len(records),'canonical_tensor_semantic_sha256':canonical,
                      'merged_weights_sha256':hashes['model.safetensors'],'receipt_sha256':digest(receipt),
                      'profile_sha256':digest(ROOT/'base-profile-14b.json'),'model_gpu_used':False},indent=2))


if __name__=='__main__':
    main()
