#!/usr/bin/env python3
"""Author fresh prompt-only refusals and exact numeric flat-beam teaching cases."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / 'corrective-001'
HEADERS = ROOT.parent / 'corrective-002' / 'headers'
spec = importlib.util.spec_from_file_location('previous_teacher_boilerplate', PREVIOUS / 'author.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)

# These are new engineering scenarios and literal prompt IDs, not benchmark evidence.
REFUSALS = [
    ('A flange is sketched from a silhouette; no contact survey or operating load record exists.',
     ['contact_plane_pose', 'fastener_seat_normals', 'service_load_envelope'],
     ('status', 'missing', 'manufacturing_authorized')),
    ('A heater mount is proposed from an oblique photograph with no registered dimensions.',
     ['datum_reference_frame', 'hole_axis_locations', 'mating_stack_limits'],
     ('decision', 'missing_measurements', 'fabrication_authorized')),
    ('A robot guard bracket has only an estimated mass and an unscaled concept drawing.',
     ['mounting_pitch_mm', 'thread_specification', 'fastener_preload_targets'],
     ('outcome', 'required_evidence', 'can_release')),
    ('A cooling duct socket has unordered unsigned XYZ samples and no seal or pressure specification.',
     ['seal_land_profile', 'port_axis_alignment', 'pressure_test_conditions'],
     ('assessment', 'unverified_inputs', 'print_release_authorized')),
    ('A replacement lug has a visual envelope but no inspected pin interface or fatigue loading.',
     ['pin_bore_tolerance', 'bearing_contact_width_mm', 'cyclic_load_spectrum'],
     ('status', 'measurement_gaps', 'fabrication_authorized')),
    ('A titanium LPBF tab is a concept only; alloy certification, orientation and acceptance criteria are absent.',
     ['alloy_certificate', 'build_orientation_datum', 'inspection_acceptance_limits'],
     ('decision', 'missing_ids', 'manufacturing_authorized')),
    ('A carrier has a closed envelope mesh but no registered mounting interfaces or temperature limits.',
     ['mount_datum_transform', 'bolt_clearance_stack', 'thermal_mismatch_limits'],
     ('outcome', 'measurement_gaps', 'print_release_authorized')),
    ('An orphan point cloud is labelled as a connector without a mating datum or clocking reference.',
     ['connector_mating_frame', 'keyway_clock_angle', 'assembly_clearance_band'],
     ('assessment', 'required_evidence', 'can_release')),
]

# Synthetic mm coordinates and radii differ from all prior teaching beam dimensions.
BEAMS = [
    ([-3.21, .47, -1.13], [3.49, .47, -1.13], .55, ('status', 'qualification', 'manufacturing_authorized')),
    ([.39, -3.43, .91], [.39, 3.07, .91], .61, ('result_kind', 'scope', 'fabrication_authorized')),
    ([-.67, 1.19, -3.57], [-.67, 1.19, 2.83], .67, ('decision', 'evidence_scope', 'print_release_authorized')),
    ([-2.71, -1.93, -1.17], [2.09, 2.47, 1.83], .73, ('outcome', 'qualification', 'can_release')),
    ([-3.03, 1.73, .59], [2.77, -1.07, 2.19], .83, ('status', 'scope', 'fabrication_authorized')),
    ([1.37, -2.83, 2.63], [-1.83, 2.37, -1.97], .91, ('result_kind', 'evidence_scope', 'manufacturing_authorized')),
    ([-2.39, -2.17, 1.41], [2.81, 1.63, -2.39], .97, ('decision', 'qualification', 'can_release')),
    ([2.43, -1.37, -2.87], [-2.17, 2.83, 2.13], 1.07, ('outcome', 'scope', 'print_release_authorized')),
]
INTENTS = [
    'Construct one calibration beam from the given numeric endpoints and radius.',
    'Debug code that treated the specified radius as a diameter: use the number directly as both end radii.',
    'Repair code that invoked AddBeam on Voxels: add it to an owned Lattice before voxelization.',
    'Correct an oblique beam whose draft passed true and consequently added rounded end caps.',
    'Preserve the literal radius and endpoint coordinates rather than rounding them to nominal catalogue sizes.',
    'Repair a draft that halved the radius before AddBeam and invented an attachment flange.',
    'Make the requested flat beam alone; an extra sphere at either endpoint would change the numeric intent.',
    'Correct a draft that reconstructed the endpoints from a guessed centre and length instead of using these vectors.',
]

REFUSAL_HEADER = '''using System;
using System.IO;
using System.Linq;
using System.Text.Json;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        // Preserve earlier evidence rather than overwriting an existing output.
        if (Directory.Exists(args[1]) && Directory.EnumerateFileSystemEntries(args[1]).Any())
            throw new IOException("Use an empty output directory.");
        Directory.CreateDirectory(args[1]);
        // The prompt supplies the missing evidence IDs. No input file is read.
        // No PicoGK context, native object or geometry is justified for this refusal.
__WRITE__
    }
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_prompt(expected):
    return ('The task-specific report overrides the generic header report. Write exactly '
            + json.dumps(expected, separators=(',', ':'))
            + '. Use exactly these keys and literal values: strings remain strings, the authorization flag is a JSON Boolean, '
            'and any missing-ID list is an ordered array of strings. No extra keys, nested evidence object, or process_status field. ')


def main():
    if (ROOT / 'train.jsonl').exists():
        raise ValueError('Create an immutable new corpus; do not overwrite a prior one.')
    (ROOT / 'headers').mkdir()
    for name in ('compact', 'development_generic'):
        shutil.copyfile(HEADERS / (name + '.txt'), ROOT / 'headers' / (name + '.txt'))
    cases = []
    rows = []
    for family, items in (('prompt-refusal', REFUSALS), ('numeric-flat-beam', BEAMS)):
        for index, item in enumerate(items, 1):
            case_id = f'fresh-{family}-{index:02d}'
            folder = ROOT / 'cases' / case_id
            folder.mkdir(parents=True)
            fixture = folder / 'ignored-input.dat'
            fixture.write_text('not JSON, not XYZ, and not engineering evidence\n')
            if family == 'prompt-refusal':
                scenario, missing, keys = item
                expected = {keys[0]: 'needs_measurement', keys[1]: missing, keys[2]: False}
                write = ('        File.WriteAllText(Path.Combine(args[1], "refused.json"), JsonSerializer.Serialize(new {\n'
                         f'            {keys[0]}="needs_measurement", {keys[1]}=new[]{{'
                         + ','.join(json.dumps(name) for name in missing) + '}, '
                         + f'{keys[2]}=false }}));')
                code = REFUSAL_HEADER.replace('__WRITE__', write)
                body = (scenario + ' Treat the listed evidence as absent, not as quantities to infer from a fixture. '
                        'Write a prompt-only needs_measurement refusal with the missing IDs copied exactly in the listed order. '
                        'Do not initialize Library or any native object, create geometry, open or parse the input path, or validate its contents. '
                        'The result must be identical even if the unused input argument names junk, valid XYZ, an empty file, or a nonexistent file. '
                        'Write only refused.json in the empty output directory. ' + schema_prompt(expected))
                explanation = ('The prompt lacks the named engineering evidence; preserve its exact ordered identifiers and JSON types without reading the input or initializing PicoGK. '
                               'A reconstructed or closed surface cannot establish interfaces, loads, or LPBF qualification (Curless & Levoy, 1996; Mercelis & Kruth, 2006).')
                oracle = {'shape': 'prompt-refusal', 'expected_report': expected, 'report_name': 'refused.json'}
            else:
                a, b, radius, keys = item
                assert .55 <= radius <= 1.1
                expected = {keys[0]: 'geometric_candidate', keys[1]: 'geometry_only', keys[2]: False}
                beam = ('        // Numeric intent: radius is in mm at both ends; false requests flat end caps.\n'
                        '        // A lattice owns AddBeam; no extra spheres, flanges or inferred scan geometry are added.\n'
                        '        using Lattice beam = new(lib);\n'
                        f'        beam.AddBeam({previous.vec(a)}, {previous.f(radius)}, {previous.vec(b)}, {previous.f(radius)}, false);\n'
                        '        using Voxels part = new(beam);')
                finish = previous.EXPORT[:previous.EXPORT.index('        File.WriteAllText')]
                finish += ('        // Match the task-specific schema exactly; geometry does not authorize manufacture.\n'
                           '        File.WriteAllText(Path.Combine(args[1], "report.json"), JsonSerializer.Serialize(new {\n'
                           f'            {keys[0]}="geometric_candidate", {keys[1]}="geometry_only", {keys[2]}=false }}));')
                code = previous.HEADER.replace('__BODY__', beam).replace('__FINISH__', finish).replace('__HELPERS__', '').replace('__CLASSES__', '')
                body = (INTENTS[index - 1] + f' Endpoint A={json.dumps(a)}, endpoint B={json.dumps(b)}, radius={radius:.2f} mm at both ends. '
                        'These vectors are the cap-centre endpoints; the solid is a finite circular cylinder with flat ends. '
                        'Pass false to Lattice.AddBeam, keep the stated radius unchanged, and add no other geometry. '
                        'The unused input argument is not a scan to parse. Export part.vdb and part.stl from that same Voxels object, '
                        'remove exactly zero-area triangles, and write only those two exports plus report.json. ' + schema_prompt(expected))
                explanation = ('Use the stated radius directly on Lattice.AddBeam and false for flat caps, then export the same voxel solid with exactly the requested JSON schema. '
                               'This synthetic coupon is a geometric check; its diameter does not prove LPBF support strategy or residual-stress control (Cloots et al., 2013; Mercelis & Kruth, 2006).')
                oracle = {'shape': 'flat-cylinder', 'a': a, 'b': b, 'radius': radius,
                          'expected_report': expected, 'report_name': 'report.json'}
            source = folder / 'Program.cs'
            source.write_text(code)
            answer = explanation + '\n\n```csharp\n' + code + '```'
            row_indices = []
            for style in ('compact', 'development_generic'):
                prompt = (ROOT / 'headers' / (style + '.txt')).read_text() + '\n' + body
                row_indices.append(len(rows))
                rows.append({'messages': [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': answer}]})
            cases.append({'id': case_id, 'family': family, 'kind': 'refusal' if family == 'prompt-refusal' else 'geometry',
                          'source': str(source.relative_to(ROOT)), 'input': str(fixture.relative_to(ROOT)),
                          'source_sha256': digest(source), 'input_sha256': digest(fixture),
                          'assistant_sha256': hashlib.sha256(answer.encode()).hexdigest(),
                          'task_body': body, 'oracle': oracle, 'row_indices': row_indices})
    train = ROOT / 'train.jsonl'
    train.write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows))
    manifest = {'schema': 'picogk.am.corrective-teachers@1', 'programs': 16, 'message_rows': 32,
                'train_sha256': digest(train), 'author_sha256': digest(Path(__file__)),
                'reused_boilerplate_sha256': digest(PREVIOUS / 'author.py'),
                'headers': {name: {'source': 'corrective-002/headers/' + name + '.txt',
                                   'sha256': digest(ROOT / 'headers' / (name + '.txt'))}
                            for name in ('compact', 'development_generic')},
                'cases': cases, 'training_started': False, 'manufacturing_authorized': False,
                'scope': '16 new programs, each presented with two previously verified generic prompt headers; no frozen task bodies or captured answers.'}
    (ROOT / 'cases.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('programs', 'message_rows', 'train_sha256')}, indent=2))


if __name__ == '__main__':
    main()
