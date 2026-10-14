#!/usr/bin/env python3
"""Diversify task bodies only; retain 80 validated teacher cases and exact answers."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
STYLES = ('intent_first', 'pipeline_ownership', 'geometry_specification', 'repair_or_refusal_contrast')
HEADER = ROOT.parent / 'corrective-002/headers/development_generic.txt'
EXPECTED_HEADER = '7f60b77ff9f921795ccfdc951754a09d2bf53d6dd521eeebdbb87f761813b1a7'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def number(value):
    return f'{value:.5f}'.rstrip('0').rstrip('.')


def vector(value):
    return '(' + ', '.join(number(x) for x in value) + ')'


def specification(case, code, fixture):
    """Read geometric values from the existing oracle/source; no benchmark input is used."""
    o = case['oracle']; family = case['family']; shape = o['shape']
    centre = o.get('centre'); facts = []; steps = []; contract = ''
    dynamic = ''
    expected = o.get('expected_report', {'status': 'geometric_candidate', 'qualification': 'geometry_only', 'manufacturing_authorized': False})
    report_name = o.get('report_name', 'report.json')
    if family in ('initialize', 'offset-sign', 'shell'):
        radius = float(re.search(r'AddSphere\(new Vector3\([^)]*\),([.0-9]+)f\)', code)[1])
        facts = [f'Sphere centre C={vector(centre)} mm; original radius R={number(radius)} mm.']
        steps = ['Own a Lattice in the Library, add exactly one sphere at C with radius R, then construct Voxels from that Lattice.']
        if family == 'offset-sign':
            erosion = float(re.search(r'part.Offset\(-([.0-9]+)f\)', code)[1])
            facts += [f'Erosion distance E={number(erosion)} mm; resulting radius R-E={number(o["radius"])} mm.']
            steps += ['Apply Offset(-E) to the sphere Voxels; a positive offset would enlarge the object.']
        if family == 'shell':
            facts += [f'Nominal skin W={number(o["wall"])} mm; inner radius R-W={number(radius-o["wall"])} mm; the centre is void.']
            steps += ['Copy the outer Voxels, erode the copy with Offset(-W), and BoolSubtract the copy from the unchanged outer volume.']
        goal = {'initialize': 'a solid sphere with explicit native lifetime', 'offset-sign': 'an eroded sphere, not an enlarged sphere', 'shell': 'a hollow spherical teaching skin, not a filled ball'}[family]
        repair = 'A draft uses an implicit global context or puts AddSphere on Voxels; move the primitive to Lattice and keep the intended offset sign and outer envelope.'
    elif family == 'closing':
        match = re.search(r'new Crack\(new Vector3\([^)]*\),([.0-9]+)f,([.0-9]+)f\)', code)
        half, gap = map(float, match.groups())
        closing = float(re.search(r'part.Offset\(([.0-9]+)f\)', code)[1])
        facts = [f'Centre C={vector(centre)} mm; cube half-side H={number(half)} mm; X fissure width G={number(gap)} mm; closing radius D={number(closing)} mm.',
                 'For q=abs(p-C), render F=max(max(q.X,q.Y,q.Z)-H, G/2-q.X), with F<=0 occupied and sampling bounds (-8,-8,-8) to (8,8,8) mm.']
        steps = ['Define the complete Crack : IImplicit helper with fSignedDistance(in Vector3), then render it directly as Voxels.',
                 'Close that same field with Offset(+D) followed by Offset(-D); export the repaired field, without substituting a beam.']
        goal = 'closure of a central X fissure in an implicit cube'
        repair = 'A draft replaces the specified cube with a cylinder or reverses opening and closing; use the stated implicit max expression and dilation-then-erosion order.'
    elif family in ('vent', 'stl-roundtrip', 'stl-skin-vent'):
        facts = [f'Synthetic box centre C={vector(centre)} mm; half-extents H={vector(o["half"])} mm.']
        if family == 'vent':
            facts += ['The outer box SDF is q=abs(p-C)-H; F=length(max(q,0))+min(max(q.X,q.Y,q.Z),0), with F<=0 occupied; use sampling bounds (-8,-8,-8) to (8,8,8) mm.']
            steps = ['Define Box : IImplicit in the answer and render the stated outer box as Voxels; do not replace it with a sphere.']
        else:
            contract = 'args[0] is an actual nonempty closed outward binary STL in millimetres. Read Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib) and new Voxels(mesh); preserve its world pose. The supplied file may be replaced by another valid surveyed box, so the displayed C/H are reference fixture values, not hardcoded replacement geometry.'
            steps = ['Import the supplied Mesh and voxelize that Mesh; do not generate a box from the reference dimensions.']
        if family != 'stl-roundtrip':
            facts += [f'Nominal inward wall W={number(o["wall"])} mm; cylindrical low-point vent radius V={number(o["vent_radius"])} mm.',
                      'Take the outer bounds after hollowing; let M=(min+max)/2. The drill cap centres are (M.X,M.Y,min.Z-0.6) and (M.X,M.Y,M.Z) mm.']
            steps += ['Copy the outer volume, Offset(-W) the copy, and BoolSubtract it.',
                      'Read part.oCalculateBoundingBox(); construct the drill on a separate Lattice with radius V at both endpoints and false for flat caps. Convert the drill to Voxels before BoolSubtract.']
            goal = 'a box skin with a floor-connected void and cylindrical evacuation opening'
            repair = 'A draft moves the drain to a side face, uses a guessed mesh diagonal as radius, or subtracts a Lattice directly; use the -Z bounds and voxelized flat cylindrical cutter.'
        else:
            goal = 'the imported solid envelope with unchanged pose and dimensions within voxel uncertainty'
            repair = 'A draft recentres the scan, substitutes a hardcoded primitive, or exports the input surface instead of the voxelized final field; perform a direct Mesh-to-Voxels-to-Mesh round trip.'
    elif family == 'cone-roof':
        facts = [f'Outer box centre C={vector(centre)} mm; half-extents H={vector(o["half"])} mm; chamber origin O={vector(o["origin"])} mm.',
                 f'Chamber radius R={number(o["radius"])} mm; floor Z={number(o["floor"])} mm; shoulder Z={number(o["shoulder"])} mm; conical rise U={number(o["rise"])} mm; floor-port radius V={number(o["port"])} mm.',
                 'For q=p-O, rho=sqrt(q.X*q.X+q.Y*q.Y), roofRadius=R*min(1,1-(q.Z-shoulder)/U), chamber F=max(rho-roofRadius,floor-q.Z,q.Z-shoulder-U). Occupied chamber samples have F<=0.',
                 'Outer Box uses its exact SDF q=abs(p-C)-H; F=length(max(q,0))+min(max(q.X,q.Y,q.Z),0). Sample both fields in (-8,-8,-8) to (8.8,8.8,8.8) mm.',
                 f'The floor drill is flat-ended from {vector([o["origin"][0],o["origin"][1],-.6])} to {vector([o["origin"][0],o["origin"][1],o["shoulder"]+.2])} mm, radius V at both ends.']
        steps = ['Define complete Box : IImplicit and Roof : IImplicit helpers, including fSignedDistance(in Vector3). Subtract the rendered Roof chamber Voxels from the outer Box Voxels.',
                 'Create the port on Lattice, voxelize it, then subtract its Voxels. The chamber roof is the analytic taper, not a stack of arbitrary beams.']
        goal = 'an analytic conical-roof chamber and a floor-connected port inside the stated block'
        repair = 'A draft assumes unavailable Cylinder/Box classes or builds a beam roof; supply your own complete implicit helpers and the stated max/taper formula.'
    elif shape == 'tpms':
        names = ('Gyroid', 'Diamond', 'Schwarz P'); formulas = (
            'sin(X)*cos(Y)+sin(Y)*cos(Z)+sin(Z)*cos(X)',
            'sin(X)*sin(Y)*sin(Z)+sin(X)*cos(Y)*cos(Z)+cos(X)*sin(Y)*cos(Z)+cos(X)*cos(Y)*sin(Z)',
            'cos(X)+cos(Y)+cos(Z)')
        facts = [f'Family={names[o["kind"]]}; selected mode={o["kind"]}; phase origin O={vector(o["origin"])} mm; period A={number(o["cell"])} mm; nominal sheet width W={number(o["wall"])} mm.',
                 f'Clip centre C={vector(centre)} mm; clip half-side H={number(o["extent"])} mm. This A is a unit-cell period, not a sphere/beam radius.',
                 f'Phase coordinates (X,Y,Z)=(p-O)*2*pi/A; the requested dimensionless nodal function is F={formulas[o["kind"]]}. The scalar carrier is F*A/(2*pi), negative on the occupied phase side, and is not an exact signed distance.',
                 'Render the phase in (-8,-8,-8) to (8,8,8) mm. Schwarz P uses the listed quarter-period shifted origin; do not substitute a Gyroid mode.']
        steps = ['Define a complete Phase : IImplicit class implementing fSignedDistance(in Vector3), and evaluate the requested nodal function. No finite primitive beam can stand in for this periodic field.',
                 'Render phase Voxels, extract Mesh(phase), then create Voxels from that zero-set Mesh to reconstruct distances. Copy it twice: Offset(+W/2) outside, Offset(-W/2) inside, then BoolSubtract inner from outer.',
                 'Trim to C-H through C+H; perform Offset(+0.05f) then Offset(-0.05f), and export that final sheet field.']
        goal = f'a {names[o["kind"]]} periodic Fourier sheet with physical millimetre width'
        repair = 'A draft treats the period as an AddBeam radius, omits : IImplicit, or selects a different nodal family; implement the scalar formula, interface, phase origin, re-distancing and symmetric offsets explicitly.'
    elif family == 'scan-normals':
        facts = [f'Reference survey centre C={vector(centre)} mm; half-extents H={vector(o["half"])} mm. Infer the envelope from input plane records rather than C/H constants.',
                 'For each normalized outward plane (point_i,normal_i), F(p)=max_i dot(p-point_i,normal_i); F<=0 is the intersection of all half-spaces. Sample in (-8,-8,-8) to (8,8,8) mm.']
        contract = ('args[0] is a semicolon CSV. Ignore blank/# lines. Require one named header plus six records (seven retained lines); the header has x,y,z,nx,ny,nz each once, and this fixture order is '+','.join(o['header'])+'. Map by names, not positions. Require six values per row, invariant-culture finite floats, |point coordinates|<=8 mm, nonzero normals, and six distinct normalized unit axis directions +/-X,+/-Y,+/-Z. Reject malformed, duplicate-header, duplicate-direction, nonfinite and zero-normal input before exporting geometry.')
        steps = ['Read the actual semicolon header and six plane rows; normalize and validate each normal.',
                 'Define Hull : IImplicit and evaluate the max-dot intersection. Render its Voxels and export the actual input-derived hull.']
        goal = 'the convex intersection of six registered outward tangent half-spaces'
        repair = 'A draft expects six total lines, discards the named header, leaves Hull undefined, or accepts only one opposed axis pair; consume seven retained lines and all six distinct axis directions.'
    elif family in ('debug-api', 'numeric-flat-beam'):
        if family == 'debug-api':
            a = [centre[0],centre[1],centre[2]-o['half_height']];b = [centre[0],centre[1],centre[2]+o['half_height']]
        else:
            a,b = o['a'],o['b']
        facts = [f'Flat-cylinder cap centre A={vector(a)} mm and cap centre B={vector(b)} mm; radius R={number(o["radius"])} mm at both ends.',
                 'R is a radius, not a diameter; A/B are endpoints, not bounds or half-extents. Use false for flat caps; add no endpoint spheres or attachment flanges.']
        steps = ['Create one Lattice, call AddBeam(A,R,B,R,false) exactly once, then construct the final Voxels from that Lattice.',
                 'Use that Voxels for VDB and Mesh(Voxels) for STL; do not invoke AddBeam on Voxels or SaveToVdbFile on Mesh.']
        goal = 'one finite flat-ended cylinder with the literal requested cap centres and radius'
        repair = 'A draft halves the stated radius, changes endpoint coordinates, uses rounded caps, or routes primitive/export methods to the wrong type; preserve the numeric roles and correct the receivers.'
    elif family == 'xyz-occupancy':
        facts = [f'One sphere per input point, radius R={number(o["radius"])} mm; reference fixture points='+json.dumps(o['points'],separators=(',',':'))+' mm. The record set can change: never hardcode these reference points.',
                 'Union only the requested balls. Retain disconnected occupancy; add no bridges, convex hull, inferred interior, phase or smoothing.']
        steps = ['Implement ReadXYZ(string path), read its actual triples, and create an owned Lattice.',
                 'For every returned Vector3 call lattice.AddSphere(point,R); construct one Voxels from the completed Lattice and export this field. A List<Vector3> cannot be passed directly to Voxels.']
        goal = 'an input-driven disconnected sphere-splat occupancy proxy'
        repair = 'A draft writes the pathname into a new file, invents SetUnit, or voxelizes List<Vector3> directly; parse args[0], add its balls to Lattice, then convert that Lattice to Voxels.'
    elif family == 'missing-interfaces':
        supplied = json.loads(fixture.read_text())
        facts = ['The reference synthetic JSON is '+json.dumps(supplied,separators=(',',':'))+'. Required measurement names and values come from the actual file, not constants in the program.']
        contract = 'args[0] is JSON with required_measurements (a nonempty ordered array of distinct nonblank strings) and measurements (an object). Read via File.ReadLines and JsonDocument.Parse. Use checked TryGetProperty. A required value counts as recorded only when it is a JSON number convertible to a finite double; absent, null, string, or overflow number remains missing. Reject a malformed top-level contract; do not infer measurements.'
        steps = ['Without Library or native objects, read the contract and iterate the supplied required names in their order.',
                 'Write the missing list dynamically. If any field is missing, status is needs_measurement; if every field is finite, status is needs_engineering_review. Never generate geometry in either branch.']
        expected = {'status':'needs_measurement','manufacturing_authorized':False,'missing':o['missing']};report_name='refused.json'
        dynamic = 'The displayed JSON is the expected primary-fixture result only. Other valid requirement lists must produce their own ordered missing names; all-fields-present must switch status to needs_engineering_review and missing to [].'
        goal = 'a measurement-evidence report, with no part invented from missing quantities'
        repair = 'A draft emits a guessed part or hardcodes one missing list. Correct both paths: consume the actual JSON contract but produce only a refusal/review report and no native context.'
    elif family == 'signed-range-refusal':
        facts = ['Missing signed-range evidence IDs, copied exactly in this order: '+json.dumps(o['missing'])+'. No unsigned XYZ syntax can supply their orientation, visibility or sensor registration.']
        steps = ['Implement the bounded ReadXYZ reader and check the actual file without initializing Library or any native object.',
                 'Catch FormatException/InvalidDataException from bad triples and mark input_valid=false; syntactically valid nonempty unsigned points give true. Regardless of validity, emit only the measurement refusal.']
        expected = {'status':'needs_measurement','manufacturing_authorized':False,'input_valid':True,'missing':o['missing']};report_name='refused.json'
        dynamic = 'The displayed true input_valid is for this valid primary fixture. Malformed, nonfinite or empty row data must set input_valid=false; the same missing IDs/status and no-geometry rule apply in both branches.'
        goal = 'a syntax-aware refusal of unsupported signed-distance reconstruction'
        repair = 'A draft mistakes valid unsigned rows for signed-range evidence, skips syntax checks, or changes requested evidence IDs. Keep input validity separate from reconstruction authorization.'
    elif family == 'prompt-refusal':
        facts = ['The prompt itself supplies the absent evidence IDs: '+json.dumps(next(v for v in expected.values() if isinstance(v,list)))+'. They must remain exact ordered strings.',
                 'No measurements have been provided for the synthetic component; do not invent interfaces, loads, shapes, or qualified process parameters.']
        steps = ['Use managed Main only; do not reference PicoGK, initialize Library, allocate native objects or construct geometry.',
                 'Ignore args[0] entirely, even if it names junk, valid XYZ, overflow JSON, empty content or a nonexistent file. Write the stated fixed prompt-only refusal.']
        goal = 'a prompt-only engineering-evidence refusal that overrides the generic geometry-export instructions'
        repair = 'A draft writes a needs_measurement object after exporting invented geometry, or unnecessarily parses an unused fixture. Delete the geometry/native/input-reading path; JSON-only means only the requested refusal file.'
    else:
        raise ValueError('Uncovered teacher family: '+family)
    if family in ('xyz-occupancy','signed-range-refusal'):
        contract = 'args[0] is an unsigned XYZ text file. Ignore blank/# lines; accept an optional case-insensitive x,y,z header and comma/semicolon/space/tab separators. Require exactly three invariant-culture finite values per record, each absolute coordinate <=8 mm, a nonempty set and at most 10000 points. Malformed/nonfinite/empty content fails ReadXYZ; never treat the pathname as coordinates.'
    if not contract:
        contract = 'The input-path argument is unused in this task; its contents are not measurements to parse or additional geometry to infer.'
    if case['kind']=='geometry':
        steps += ['Export the FINAL transformed Voxels with voxels.SaveToVdbFile. Construct Mesh(finalVoxels), copy nonzero-area triangles into a new Mesh(lib) using exact double-precision cross products, and save the cleaned mesh with Mesh.EStlUnit.MM.']
        ownership = 'Use Library(0.2f) headlessly and dispose native Lattice/Voxels/Mesh objects before that Library. VDB and STL must represent the same final field; no intermediate or input surface is the final export.'
        files = 'Only part.vdb, part.stl and report.json belong in the initially empty output directory.'
    else:
        ownership = 'There is no native Library, geometry allocation, STL or VDB in any refusal/review branch. Input parsing occurs only when this specific task explicitly requires it.'
        files = 'Only refused.json belongs in the initially empty output directory.'
    report = 'For the primary fixture, '+report_name+' must be exactly '+json.dumps(expected,separators=(',',':'))+'. Match keys and values, with JSON strings, Boolean false, and ordered string arrays where shown; no nested qualification object, string authorization flag, extra process_status or other extra key. '+dynamic
    return {'goal':goal,'facts':facts,'operations':steps,'input_contract':contract,'ownership':ownership,'output_contract':files,'report_contract':report,'repair_diagnosis':repair,'expected_primary_report':expected,'report_name':report_name}


def body(spec, style):
    facts=spec['facts'];steps=spec['operations'];inp=spec['input_contract'];report=spec['report_contract']
    if style=='intent_first':
        return ('Implement '+spec['goal']+' as a complete C# PicoGK program. The intended result is governed by these values and definitions: '+ ' '.join(facts)
                +' Read/ignore input according to this contract: '+inp+' To obtain the result, '+' Then '.join(steps)
                +' Finish with the exact task report: '+report+' '+spec['ownership']+' '+spec['output_contract'])
    if style=='pipeline_ownership':
        return ('Build a self-contained Main and include every referenced helper class, interface implementation and reader; no unseen Box, Roof, Hull or Phase library class is assumed. '
                +'First establish input handling: '+inp+' Next follow this owned-object pipeline:\n'
                +'\n'.join(str(i+1)+'. '+step for i,step in enumerate(steps))
                +'\nThe pipeline parameters are fixed by:\n'+'\n'.join('- '+fact for fact in facts)
                +'\nLifetime and outputs: '+spec['ownership']+' '+spec['output_contract']+' The output schema is part of the implementation contract: '+report)
    if style=='geometry_specification':
        return ('Specification for a synthetic millimetre teaching case:\n'+'\n'.join('- '+fact for fact in facts)
                +'\nInput grammar and source of evidence:\n'+inp+'\nRequired behavior: return '+spec['goal']+'. '
                +'An acceptable implementation realizes the mathematical/conditional specification as follows: '+'; '.join(steps)
                +'\nResource ownership: '+spec['ownership']+'\nExport inventory: '+spec['output_contract']+'\nExact JSON schema and branch semantics: '+report)
    if style=='repair_or_refusal_contrast':
        return ('Repair a conceptually broken standalone program rather than adding a plausible replacement shape. '+spec['repair_diagnosis']
                +' The corrected program must instead implement '+spec['goal']+'. Its complete specification is '+' '.join(facts)
                +' Separate input evidence from prompt constants: '+inp+' Replace the broken sequence with '+' -> '.join(steps)
                +' Even if the common API header suggests general geometry exports, this task owns its output decision: '+spec['output_contract']+' '+report
                +' Keep the lifetime rule explicit: '+spec['ownership'])
    raise ValueError(style)


def main():
    if (ROOT/'train.jsonl').exists():
        raise FileExistsError('Preserve a previously authored corpus.')
    assert sha(HEADER)==EXPECTED_HEADER
    shutil.copyfile(HEADER,ROOT/'generic-header.txt');header=HEADER.read_text()
    teachers=[];rows=[];bindings=[];source_bindings=[]
    for dataset,expected_count in (('corrective-001',64),('corrective-003',16)):
        parent=ROOT.parent/dataset;manifest=json.loads((parent/'cases.json').read_text());original=[json.loads(line) for line in (parent/'train.jsonl').read_text().splitlines()]
        assert len(manifest['cases'])==expected_count and sha(parent/'train.jsonl')==manifest['train_sha256']
        source_bindings.append({'dataset':dataset,'corpus':str((parent/'train.jsonl').relative_to(WORK)),'corpus_sha256':sha(parent/'train.jsonl'),'cases_sha256':sha(parent/'cases.json')})
        for index,case in enumerate(manifest['cases']):
            original_line=index+1 if dataset=='corrective-001' else case['row_indices'][0]+1
            answer=original[original_line-1]['messages'][1]['content'];source=parent/case['source'];fixture=parent/case['input'];native=parent/'native-review-002'/case['id']/'result.json'
            assert answer.count('```')==2 and answer.split('```csharp\n',1)[1].rsplit('```',1)[0]==source.read_text()
            assert sha(source)==case['source_sha256'] and sha(fixture)==case['input_sha256']
            proof=json.loads(native.read_text());assert proof['status']=='passed' and proof['native_exit_code']==0 and proof['source_sha256']==case['source_sha256'] and all(type(v) is bool and v for v in proof['checks'].values())
            spec=specification(case,source.read_text(),fixture)
            teacher={'original_teacher_id':case['id'],'original_dataset':dataset,'original_corpus_line_1based':original_line,'family':case['family'],'kind':case['kind'],'source':str(source.relative_to(WORK)),'source_sha256':sha(source),'input':str(fixture.relative_to(WORK)),'input_sha256':sha(fixture),'assistant_sha256':text_sha(answer),'native_result':str(native.relative_to(WORK)),'native_result_sha256':sha(native),'oracle':case['oracle'],'semantic_specification':spec}
            teachers.append(teacher)
            bodies=[]
            for style in STYLES:
                text=body(spec,style);assert text.isascii() and case['id'] not in text
                prompt=header+'\n'+text;assert prompt.isascii()
                bodies.append(text);rows.append({'messages':[{'role':'user','content':prompt},{'role':'assistant','content':answer}]})
                bindings.append({'line_1based':len(rows),'original_teacher_id':case['id'],'original_dataset':dataset,'paraphrase_style':style,'prompt_sha256':text_sha(prompt),'task_body_sha256':text_sha(text),'assistant_sha256':text_sha(answer),'source_sha256':sha(source),'input_sha256':sha(fixture),'native_result_sha256':sha(native)})
            assert len(set(bodies))==4
    assert len(teachers)==80 and len(rows)==320 and len({r['messages'][0]['content'] for r in rows})==320
    data=''.join(json.dumps(row,ensure_ascii=True,separators=(',',':'))+'\n' for row in rows)
    assert data.isascii()
    (ROOT/'train.jsonl').write_text(data)
    parsed=[json.loads(line) for line in data.splitlines()]
    for row,binding in zip(parsed,bindings):
        assert list(row)==['messages'] and [m['role'] for m in row['messages']]==['user','assistant']
        assert text_sha(row['messages'][1]['content'])==binding['assistant_sha256']
        assert row['messages'][1]['content'].count('```')==2
    manifest={'schema':'picogk.am.task-body-augmentation@1','status':'authored_pending_independent_semantic_and_token_review','teacher_cases':80,'distinct_source_programs':len({t['source_sha256'] for t in teachers}),'distinct_assistant_answers':len({t['assistant_sha256'] for t in teachers}),'rows':320,'styles':list(STYLES),'family_counts':dict(Counter(t['family'] for t in teachers)),'train_sha256':sha(ROOT/'train.jsonl'),'author_source_sha256':sha(Path(__file__)),'generic_header_source':'data/corrective-002/headers/development_generic.txt','generic_header_sha256':sha(HEADER),'original_corpora':source_bindings,'teacher_bindings':teachers,'row_bindings':bindings,'all_assistant_source_fixture_bytes_unchanged':True,'new_native_programs':0,'native_execution_repeated':False,'serialization_ascii':True,'prompt_text_ascii':True,'source_of_task_parameters':'Existing validated teacher oracle/source/input only; no development/final task bodies, captured answers or new geometry parameters.','final_contents_read':False,'evaluation_gold_used':False,'model_loaded':False,'gpu_used':False,'training_started':False,'manufacturing_authorized':False}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=True,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('teacher_cases','distinct_source_programs','distinct_assistant_answers','rows','train_sha256')},indent=2))


if __name__=='__main__':
    main()
