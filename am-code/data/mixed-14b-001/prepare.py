#!/usr/bin/env python3
"""Exact 150+160 byte concatenation; preserve original ChatML and teacher proofs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[1]
SOURCES = (
    ('data/train-chat.jsonl',150,'1ac93688653ea7aa26b1e93b739eaac21717e11af4f9996972b6735bb20fe684'),
    ('data/corrective-005/train.jsonl',160,'b59755b51c94a559030863fc5ba164b28cdd338ea2c33704825995bc43f083c7'),
)
RAW_SHA = 'ed3247fb4c8ecacc013eb95f16fb6ac6d822680e40d32ae95cafb130893108d7'
MANIFEST_SHA = '079d5db4a9584430255b8a715f49e6d8fe7239d37fcd4c091dd13100e734d9ea'
PROFILE_SHA = 'ae1b81ddd239197ac4f470e6d01173dfc0132d05215ac09ea6a31946625cf89e'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def strict(payload):
    assert payload.endswith(b'\n'), 'Concatenation must not invent a row separator.'
    rows=[json.loads(line) for line in payload.decode('utf-8').splitlines()]
    for row in rows:
        assert type(row) is dict and set(row)=={'messages'} and len(row['messages'])==2
        for message,role in zip(row['messages'],('user','assistant')):
            assert type(message) is dict and set(message)=={'role','content'}
            assert message['role']==role and type(message['content']) is str and message['content'].strip()
    return rows


def main():
    assert not (OUTPUT/'train.jsonl').exists() and not (OUTPUT/'provenance.json').exists(), 'Preserve prior derivative evidence.'
    payloads=[];records=[]
    for path,count,expected in SOURCES:
        payload=(ROOT/path).read_bytes()
        assert sha(payload)==expected and len(strict(payload))==count
        payloads.append(payload);records.append({'path':path,'rows':count,'bytes':len(payload),'sha256':expected})
    payload=b''.join(payloads);rows=strict(payload)
    assert len(rows)==310 and payload[:len(payloads[0])]==payloads[0] and payload[len(payloads[0]):]==payloads[1]
    raw=(ROOT/'data/train.jsonl').read_bytes();assert sha(raw)==RAW_SHA
    original_manifest=json.loads((ROOT/'data/manifest.json').read_text())
    raw_rows=[json.loads(line) for line in raw.decode().splitlines()];assert len(raw_rows)==150
    original_bindings=[]
    for index,(original,chat,binding) in enumerate(zip(raw_rows,rows[:150],original_manifest['rows']),1):
        user,assistant=(m['content'] for m in chat['messages'])
        rebuilt='<|im_start|>user\n'+user+'\n<|im_end|>\n<|im_start|>assistant\n'+assistant+'\n<|im_end|>'
        assert rebuilt==original['text'] and sha(rebuilt.encode())==binding['chatml_text_sha256']
        assert sha(user.encode())==binding['user_content_sha256'] and sha(assistant.encode())==binding['assistant_content_sha256']
        original_bindings.append({'line_1based':index,**binding})
    teacher_path=ROOT/'data/corrective-005/manifest.json';assert sha(teacher_path.read_bytes())==MANIFEST_SHA
    teacher=json.loads(teacher_path.read_text());supplemental_bindings=[]
    sources={t['original_teacher_id']:t for t in teacher['teacher_bindings']}
    for index,(row,binding) in enumerate(zip(rows[150:],teacher['row_bindings']),151):
        user,assistant=(m['content'] for m in row['messages'])
        assert sha(user.encode())==binding['prompt_sha256'] and sha(assistant.encode())==binding['assistant_sha256']
        source=sources[binding['original_teacher_id']]
        assert re.fullmatch(r'.*?```csharp\n(.*?)```\s*',assistant,re.S)[1]==(ROOT/source['source']).read_text()
        for path_key,hash_key in (('source','source_sha256'),('input','input_sha256'),('native_result','native_result_sha256')):
            assert sha((ROOT/source[path_key]).read_bytes())==binding[hash_key]
        supplemental_bindings.append({'combined_line_1based':index,**binding})
    assert len(original_bindings)==150 and len(supplemental_bindings)==160
    profile=ROOT/'base-profile-14b.json';assert sha(profile.read_bytes())==PROFILE_SHA
    for path,_,expected in SOURCES:assert sha((ROOT/path).read_bytes())==expected
    with (OUTPUT/'train.jsonl').open('xb') as handle:handle.write(payload)
    assert (OUTPUT/'train.jsonl').read_bytes()==payload
    proof_paths=('data/corrective-005/independent-semantic-review.json','data/corrective-005/tokenization-receipt.json','diagnostics/corrective005-independent-semantic-source-review.json')
    provenance={'schema':'picogk.am.mixed-corpus@1','status':'frozen_pending_independent_actual14b_token_review','created_at_utc':datetime.now(timezone.utc).isoformat(),'operation':'exact byte concatenation in declared source order; no reserialization','sources':records,'rows':310,'bytes':len(payload),'train_sha256':sha(payload),'raw150_sha256':RAW_SHA,'chat150_sha256':SOURCES[0][2],'raw150_manifest_sha256':sha((ROOT/'data/manifest.json').read_bytes()),'all150_original_chatml_and_user_assistant_content_hashes_exact':True,'all160_teacher_source_assistant_fixture_native_bindings_exact':True,'original150_content_bindings':original_bindings,'supplemental160_row_bindings':supplemental_bindings,'supplemental80_teacher_bindings':teacher['teacher_bindings'],'supplemental_authored_manifest_sha256':MANIFEST_SHA,'supplemental_review_files_sha256':{path:sha((ROOT/path).read_bytes()) for path in proof_paths},'base_profile_sha256':PROFILE_SHA,'preparation_source_sha256':sha(Path(__file__).read_bytes()),'new_teaching_rows':0,'new_native_programs':0,'native_execution_repeated':False,'original_sources_modified':False,'training_started':False,'model_loaded':False,'mlx_imported':False,'gpu_used':False,'final_contents_read':False,'manufacturing_authorized':False}
    with (OUTPUT/'provenance.json').open('x') as handle:handle.write(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'rows':310,'train_sha256':sha(payload),'provenance_sha256':sha((OUTPUT/'provenance.json').read_bytes()),'raw150_sha256':RAW_SHA,'chat150_sha256':SOURCES[0][2],'source_bytes_unchanged':True},indent=2))


if __name__=='__main__':main()
