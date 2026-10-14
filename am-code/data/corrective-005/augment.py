#!/usr/bin/env python3
"""Short task-first formulations; all 80 validated teacher answers remain exact."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
PARENT = ROOT.parent / 'corrective-004/manifest.json'
PARENT_SHA = '0ec16b8c3a3134af5642b5849119e238dac782c2b977345d43c18ad577ea534a'
HEADER = ROOT.parent / 'corrective-002/headers/development_generic.txt'
HEADER_SHA = '7f60b77ff9f921795ccfdc951754a09d2bf53d6dd521eeebdbb87f761813b1a7'
STYLES = ('natural_request', 'task_first_rephrase')
REPORT = {'status':'geometric_candidate', 'qualification':'geometry_only', 'manufacturing_authorized':False}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def number(value):
    return f'{value:.5f}'.rstrip('0').rstrip('.')


def vector(value):
    return '(' + ','.join(number(x) for x in value) + ')'


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def bodies(teacher, code, fixture):
    """Use only frozen teacher metadata, validated source and synthetic fixture."""
    family = teacher['family'];o = teacher['oracle'];c = o.get('centre')
    suffix = ' report.json exactly '+compact(o.get('expected_report', REPORT))+'.'
    if family in ('initialize', 'offset-sign', 'shell'):
        radius = number(float(re.search(r'AddSphere\(new Vector3\([^)]*\),([.0-9]+)f\)',code)[1]))
        base = f'Sphere centre {vector(c)} mm, radius {radius} mm.'
        if family == 'initialize':
            a = f'Create one solid sphere: {base} Use Lattice.AddSphere then Voxels(lattice), with explicit Library lifetime. Input is unused; export this sphere.'
            b = f'I need a solid ball at {vector(c)} mm with radius {radius} mm. Put the primitive on Lattice and voxelize it; no beam, cavity or offsets. Ignore args[0]; export the same final field.'
        elif family == 'offset-sign':
            erosion = number(float(re.search(r'part.Offset\(-([.0-9]+)f\)',code)[1]))
            a = f'Erode a sphere by {erosion} mm: {base} Build with Lattice.AddSphere, voxelize, then Offset(-{erosion}f). Final radius must be {number(o["radius"])} mm. Input unused; export the eroded field.'
            b = f'Shrink a solid ball at {vector(c)} mm from radius {radius} to {number(o["radius"])} mm using negative Offset({"-"+erosion}f). Preserve its centre; do not subtract the ball from itself or hollow it. Create it through Lattice. Input unused.'
        else:
            w = number(o['wall'])
            a = f'Create a hollow spherical skin: {base} Wall {w} mm; centre void. Keep outer Voxels unchanged, erode a separate copy with Offset(-{w}f), then subtract that copy. Input unused; export the shell.'
            b = f'I need a spherical shell centred {vector(c)} mm, outer radius {radius} mm and wall {w} mm. AddSphere on Lattice; voxelize, copy, erode the copy, BoolSubtract inner from outer. Do not erode the outer envelope. Input unused.'
    elif family == 'closing':
        match = re.search(r'new Crack\(new Vector3\([^)]*\),([.0-9]+)f,([.0-9]+)f\)',code)
        h,g = map(number,map(float,match.groups()))
        d = number(float(re.search(r'part.Offset\(([.0-9]+)f\)',code)[1]))
        formula = f'C={vector(c)}, H={h}, fissure G={g} mm; q=abs(p-C), F=max(max(q.X,q.Y,q.Z)-H,G/2-q.X).'
        a = f'Close the X fissure in this cube: {formula} Define IImplicit (F<=0 inside), render [-8,8]^3 mm, then Offset(+{d}f) followed by Offset(-{d}f). Export repaired Voxels; input unused.'
        b = f'Repair a split cube without replacing it by a beam. {formula} Render your complete IImplicit in [-8,8]^3 mm; dilate {d} mm then erode {d} mm on the same field. Input unused; export the closed cube.'
    elif family in ('vent', 'stl-roundtrip', 'stl-skin-vent'):
        if family == 'vent':
            intro = f'Create an implicit box centred {vector(c)} mm with half-extents {vector(o["half"])} mm in [-8,8]^3 mm.'
            other = f'Hollow a box at {vector(c)} mm, half-extents {vector(o["half"])} mm; define its IImplicit and render [-8,8]^3 mm.'
            unused = ' Input unused.'
        else:
            intro = 'Read the actual closed outward binary STL args[0] in MM with Mesh.mshFromStlFile(...,libSet:lib); voxelize that Mesh, keeping its pose.'
            other = 'Voxelize the supplied closed outward binary STL in millimetres. Read args[0] using Mesh.mshFromStlFile(...,libSet:lib); do not replace it by a hardcoded box or recenter it.'
            unused = ''
        if family == 'stl-roundtrip':
            reference = f' Fixture centre {vector(c)}, half-extents {vector(o["half"])} mm; replacements must use their actual geometry.'
            a = intro+' Export this voxelized field unchanged; mesh the final Voxels for STL.'+reference
            b = other+' Round-trip its envelope through Voxels and export the final field, with no hollowing or smoothing.'+reference
        else:
            w,v = number(o['wall']),number(o['vent_radius'])
            drain = f'Wall {w} mm: subtract a copy eroded by {w} mm. From final bounds let M=(min+max)/2; drill (M.X,M.Y,min.Z-0.6) to (M.X,M.Y,M.Z), radius {v} mm at both caps, flat.'
            a = intro+' '+drain+' Use Lattice->Voxels for the cutter before BoolSubtract; export final skin and port.'+unused
            b = other+f' Subtract an inward-offset copy (wall {w} mm). Use final bounds M=(min+max)/2; subtract a flat Lattice beam voxelized first, radius {v} mm, from (M.X,M.Y,min.Z-0.6) to (M.X,M.Y,M.Z).'+unused
    elif family == 'cone-roof':
        dimensions = f'Block C={vector(c)}, half={vector(o["half"])} mm; chamber O={vector(o["origin"])} mm, R={number(o["radius"])}, floor={number(o["floor"])}, shoulder={number(o["shoulder"])}, rise={number(o["rise"])} mm.'
        chamber = 'q=p-O; rho=sqrt(q.X*q.X+q.Y*q.Y); F=max(rho-R*min(1,1-(q.Z-shoulder)/rise),floor-q.Z,q.Z-shoulder-rise).'
        port = f'Drill flat radius {number(o["port"])} mm from {vector([o["origin"][0],o["origin"][1],-.6])} to {vector([o["origin"][0],o["origin"][1],o["shoulder"]+.2])} mm via Lattice->Voxels.'
        a = f'Make a conical-roof chamber. {dimensions} Define Box/Roof : IImplicit; render [-8,8.8]^3; subtract chamber F<=0. {chamber} {port} Input unused.'
        b = f'Subtract a tapered chamber and floor port from a block. {dimensions} {chamber} Implement both IImplicit helpers in [-8,8.8]^3. {port} Subtract the two cutter Voxels; input unused.'
    elif o['shape'] == 'tpms':
        name = ('Gyroid','Diamond','Schwarz P')[o['kind']]
        formula = ('sin(X)*cos(Y)+sin(Y)*cos(Z)+sin(Z)*cos(X)',
                   'sin(X)*sin(Y)*sin(Z)+sin(X)*cos(Y)*cos(Z)+cos(X)*sin(Y)*cos(Z)+cos(X)*cos(Y)*sin(Z)',
                   'cos(X)+cos(Y)+cos(Z)')[o['kind']]
        dimensions = f'period A={number(o["cell"])} mm, width W={number(o["wall"])} mm, phase origin O={vector(o["origin"])} mm; clip centre C={vector(c)} mm, half-side H={number(o["extent"])} mm.'
        field = f'(X,Y,Z)=(p-O)*2*pi/A; F={formula}; IImplicit returns F*A/(2*pi).'
        band = 'Render [-8,8]^3, re-distance through Mesh->Voxels; copy twice, outer.Offset(+W/2), inner.Offset(-W/2), outer.BoolSubtract(inner). Trim C-H to C+H; close +0.05,-0.05 mm.'
        a = f'Generate a {name} sheet, not struts: {dimensions} {field} Define the full helper. {band} Input unused; export that final sheet.'
        b = f'I need the symmetric {name} zero-set sheet with {dimensions} {field} This dimensionless nodal field is not a millimetre SDF. {band} Use this family, not a substituted phase or beam; input unused.'
    elif family == 'scan-normals':
        grammar = ('args[0] semicolon CSV: one x,y,z,nx,ny,nz header in any order, each once; six rows, six invariant finite floats each. Skip blank/# lines. |point coordinates|<=8 mm; raw n.LengthSquared()>=0.01f; normalize to six distinct +/-unit axis normals.')
        field = 'Define IImplicit F(p)=max_i dot(p-point_i,n_i), F<=0 inside; render [-8,8]^3 mm. Reject malformed input before exports.'
        order = ' Fixture header: '+';'.join(o['header'])+'.'
        a = f'Reconstruct the surveyed six-plane hull from {grammar} {field} Read actual points/normals; never hardcode a box.'+order
        b = f'Use the actual outward tangent planes, not point spheres: {grammar} {field} Preserve the input-derived envelope.'+order
    elif family in ('debug-api','numeric-flat-beam'):
        if family == 'debug-api':
            first = [c[0],c[1],c[2]-o['half_height']];last = [c[0],c[1],c[2]+o['half_height']]
        else:first,last = o['a'],o['b']
        r = number(o['radius'])
        a = f'Create one flat-ended cylinder: distinct cap centres A={vector(first)} mm, B={vector(last)} mm; float radius R={r}f mm at both ends. Call Lattice.AddBeam(A,R,B,R,false), then Voxels(lattice). R is not a diameter. No end spheres or flanges; input unused.'
        b = f'Fix a beam draft that halves its radius or repeats its endpoints. Required cap centres {vector(first)} and {vector(last)} mm, radius literal {r}f at BOTH ends. AddBeam belongs to Lattice, false gives flat caps; voxelize it. Export only this cylinder, never Mesh.SaveToVdbFile; input unused.'
    elif family == 'xyz-occupancy':
        grammar = xyz_grammar()
        r = number(o['radius'])
        a = f'Build a disconnected occupancy proxy from actual unsigned XYZ args[0]. {grammar} Add one sphere radius {r}f mm per parsed point on Lattice, then Voxels(lattice). Keep only their union; no bridges, convex fill or smoothing.'
        b = f'Implement ReadXYZ and sphere-splat the input points, radius {r}f mm per point. {grammar} Read args[0], not its pathname as coordinates. Lattice.AddSphere for every point, then Voxels; do not hardcode fixture points or infer a closed interior.'
    elif family == 'missing-interfaces':
        required = compact(o['required'])
        grammar = 'Read args[0] JSON: ordered distinct nonblank required_measurements and a measurements object. Required values count only as finite JSON numbers; absent/null/string/overflow is missing. Reject malformed contracts.'
        report = 'Only refused.json: {"status":"needs_measurement","manufacturing_authorized":false,"missing":ordered_missing_names}; if none missing use "needs_engineering_review" and []. No extra keys.'
        a = f'Refuse unmeasured engineering inputs without Library/native objects or geometry. {grammar} Primary required names {required}; derive missing names from the actual file. {report}'
        b = f'Write an evidence report, never an invented part. {grammar} The fixture requires {required}, but replacement lists must work. {report} No Library, STL or VDB.'
        return a,b
    elif family == 'signed-range-refusal':
        report = {'status':'needs_measurement','manufacturing_authorized':False,'input_valid':True,'missing':o['missing']}
        contract = 'Only refused.json, exactly '+compact(report)+'. input_valid is true for valid nonempty rows, false on FormatException/InvalidDataException; both branches keep these missing IDs. No Library/native objects or geometry.'
        a = 'Reject signed reconstruction from unsigned XYZ, but check its actual syntax first. '+xyz_grammar()+' '+contract
        b = 'Valid XYZ does not provide oriented signed-range evidence. Parse args[0] using this grammar: '+xyz_grammar()+' '+contract
        return a,b
    elif family == 'prompt-refusal':
        # Scenario prose is from the original metadata, not this deliberately unused file.
        original = json.loads((WORK/'data/corrective-003/cases.json').read_text())
        task = next(t['task_body'] for t in original['cases'] if t['id']==teacher['original_teacher_id'])
        scenario = task.split('. ',1)[0]+'.'
        report = 'Write only refused.json exactly '+compact(o['expected_report'])+'. No extra keys; JSON strings, Boolean false and ordered string arrays keep their types.'
        a = scenario+' The listed evidence is absent. Give a prompt-only refusal: no Library/native objects, geometry or input reading. Ignore args[0], including junk or nonexistent files. '+report
        b = 'The prompt already establishes missing evidence. '+scenario+' Return only the refusal below; do not parse or validate args[0] or create any native context, STL or VDB. '+report
        return a,b
    else:raise ValueError('Uncovered family: '+family)
    return a+suffix,b+suffix


def xyz_grammar():
    return ('Skip blank/# and case-insensitive x,y,z header lines; comma/semicolon/space/tab separators; exactly three invariant finite floats per record, |coordinate|<=8 mm, 1..10000 points. Reject malformed/nonfinite/empty data.')


def prepare():
    assert sha(PARENT)==PARENT_SHA and sha(HEADER)==HEADER_SHA
    parent=json.loads(PARENT.read_text());header=HEADER.read_text()
    assert parent['teacher_cases']==80 and parent['all_assistant_source_fixture_bytes_unchanged']
    corpora={item['dataset']:[json.loads(line) for line in (WORK/item['corpus']).read_text().splitlines()] for item in parent['original_corpora']}
    for item in parent['original_corpora']:
        assert sha(WORK/item['corpus'])==item['corpus_sha256']
    rows=[];bindings=[];teachers=[]
    for original in parent['teacher_bindings']:
        t={k:v for k,v in original.items() if k!='semantic_specification'}
        source=WORK/t['source'];fixture=WORK/t['input'];native=WORK/t['native_result']
        assert sha(source)==t['source_sha256'] and sha(fixture)==t['input_sha256'] and sha(native)==t['native_result_sha256']
        result=json.loads(native.read_text())
        assert result['status']=='passed' and result['native_exit_code']==0 and result['checks']
        assert all(type(value) is bool and value for value in result['checks'].values())
        answer=corpora[t['original_dataset']][t['original_corpus_line_1based']-1]['messages'][1]['content']
        assert text_sha(answer)==t['assistant_sha256'] and answer.count('```')==2
        code=re.fullmatch(r'.*?```csharp\n(.*?)```\s*',answer,re.S)[1]
        assert code==source.read_text()
        formulations=bodies(t,code,fixture)
        assert len(set(formulations))==2
        limit=1000 if t['family'] in ('gyroid','diamond','schwarz-p','signed-range-refusal') else 650
        for style,body in zip(STYLES,formulations):
            assert body.isascii() and t['original_teacher_id'] not in body and len(body)<=limit,(t['original_teacher_id'],style,len(body),limit)
            prompt=header+'\n'+body
            rows.append({'messages':[{'role':'user','content':prompt},{'role':'assistant','content':answer}]})
            bindings.append({'line_1based':len(rows),'original_teacher_id':t['original_teacher_id'],'original_dataset':t['original_dataset'],'paraphrase_style':style,'task_body_chars':len(body),'task_body_limit':limit,'prompt_sha256':text_sha(prompt),'task_body_sha256':text_sha(body),'assistant_sha256':text_sha(answer),'source_sha256':t['source_sha256'],'input_sha256':t['input_sha256'],'native_result_sha256':t['native_result_sha256']})
        teachers.append(t)
    assert len(teachers)==80 and len(rows)==160 and len({r['messages'][0]['content'] for r in rows})==160
    assert len({t['source_sha256'] for t in teachers})==71
    serialized=''.join(compact(row)+'\n' for row in rows)
    parsed=[json.loads(line) for line in serialized.splitlines()]
    assert parsed==rows and serialized.isascii()
    assert all(list(row)==['messages'] and [m['role'] for m in row['messages']]==['user','assistant'] for row in parsed)
    return serialized,teachers,bindings,parent


def main():
    data,teachers,bindings,parent=prepare()
    if sys.argv[1:]==['--self-check']:
        print('160 strict rows, 80 unchanged teacher/proof bindings, 71 sources and all short-body limits pass; no native/model/GPU execution.');return
    if sys.argv[1:]:raise ValueError('Only --self-check is supported.')
    paths=[ROOT/'train.jsonl',ROOT/'manifest.json']
    if any(p.exists() for p in paths):raise FileExistsError('Preserve prior corpus/manifest; use a new version directory.')
    with paths[0].open('x') as handle:handle.write(data)
    proof_paths=['data/corrective-001/cases.json','data/corrective-001/validate.py','data/corrective-001/native-review-002/report.json','data/corrective-003/cases.json','data/corrective-003/validate.py','data/corrective-003/native-review-002/report.json']
    lengths=[b['task_body_chars'] for b in bindings]
    manifest={'schema':'picogk.am.short-task-augmentation@1','status':'authored_pending_independent_semantic_and_token_review','teacher_cases':80,'distinct_source_programs':71,'distinct_assistant_answers':len({t['assistant_sha256'] for t in teachers}),'rows':160,'styles':list(STYLES),'family_counts':dict(Counter(t['family'] for t in teachers)),'task_body_chars':{'min':min(lengths),'max':max(lengths),'median':statistics.median(lengths)},'train_sha256':sha(paths[0]),'author_source_sha256':sha(Path(__file__)),'generic_header_source':str(HEADER.relative_to(WORK)),'generic_header_sha256':HEADER_SHA,'teacher_metadata_source':str(PARENT.relative_to(WORK)),'teacher_metadata_sha256':PARENT_SHA,'original_corpora':parent['original_corpora'],'native_proof_files_sha256':{p:sha(WORK/p) for p in proof_paths},'teacher_bindings':teachers,'row_bindings':bindings,'all_assistant_source_fixture_bytes_unchanged':True,'new_native_programs':0,'native_execution_repeated':False,'serialization_ascii':True,'prompt_text_ascii':True,'source_of_task_parameters':'Frozen 001/003 teacher oracle/source/synthetic fixture metadata only. No development/final task body, dimensions, IDs, gold or captured answer used.','final_contents_read':False,'evaluation_gold_used':False,'model_loaded':False,'gpu_used':False,'training_started':False,'manufacturing_authorized':False}
    with paths[1].open('x') as handle:handle.write(json.dumps(manifest,ensure_ascii=True,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('teacher_cases','distinct_source_programs','rows','task_body_chars','train_sha256')},indent=2))


if __name__=='__main__':main()
