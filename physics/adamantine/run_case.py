"""Run adamantine in the pinned release image and record evidence.

Phase 3 of docs/PHYSICS_EVIDENCE_PLAN.md.

    run_case.py smoke --out work/adamantine/smoke-TAG --receipt evidence/process/NAME.json
    run_case.py pipeline STL --out work/adamantine/pipe-TAG --receipt evidence/process/NAME.json

`smoke` runs the image's own demo_316_short example and compares the final
temperature field with the regression data shipped in the same image.
`pipeline` turns a verified corpus STL into a hexahedral mesh (hexmesh.py),
then runs a short thermal simulation with one laser line on the part. It
checks that the chain works and that the absorbed heat matches the input
energy. It is not a calibrated prediction.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import zlib

IMAGE = 'rombur/adamantine:1.1@sha256:ac735f9b6fec7626e79e91061cbd03b6274478fbafcaf2dcbe078c042affc9fa'
BINARY = '/home/adamantine/bin/adamantine'
DEMO = '/home/adamantine/tests/data'
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def container(case, command, cpus=1, timeout=7200):
    cmd = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges', '--memory', '12g', '--memory-swap', '12g', '--cpus', str(cpus),
           '--pids-limit', '512', '--user', f'{os.getuid()}:{os.getgid()}',
           '-v', f'{Path(case).resolve()}:/case', '-w', '/case', IMAGE, 'bash', '-c', command]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def read_vtu_array(path, name):
    """One Float32 DataArray from a deal.II VTU: zlib-compressed, base64, UInt32 header."""
    text = Path(path).read_text()
    match = re.search(r'<DataArray type="Float32"[^>]*Name="%s"[^>]*format="binary">\s*([A-Za-z0-9+/=]+)' % name, text)
    if not match:
        raise ValueError(f'{path}: no binary Float32 array {name}')
    return decode_block(match.group(1))


def read_vtu_points(path):
    text = Path(path).read_text()
    match = re.search(r'<Points>\s*<DataArray type="Float32" NumberOfComponents="3" format="binary">\s*([A-Za-z0-9+/=]+)',
                      text)
    values = decode_block(match.group(1))
    return [tuple(values[i:i + 3]) for i in range(0, len(values), 3)]


def decode_block(encoded):
    first = base64.b64decode(encoded[:8])
    blocks = struct.unpack('<I', first[:4])[0]
    header_chars = 4 * -(-(4 * (3 + blocks)) // 3)
    header = struct.unpack(f'<{3 + blocks}I', base64.b64decode(encoded[:header_chars])[:4 * (3 + blocks)])
    payload = base64.b64decode(encoded[header_chars:])
    raw, offset = b'', 0
    for size in header[3:]:
        raw += zlib.decompress(payload[offset:offset + size])
        offset += size
    return struct.unpack(f'<{len(raw) // 4}f', raw)


def final_vtu(case):
    steps = sorted(Path(case).glob('output.*.0.vtu'), key=lambda p: int(p.name.split('.')[1]))
    if not steps:
        raise RuntimeError('adamantine wrote no output')
    return steps


def stats(values):
    return {'n': len(values), 'min': round(min(values), 3), 'max': round(max(values), 3),
            'mean': round(sum(values) / len(values), 3)}


def smoke(out):
    """demo_316_short as shipped, output at every step so the final state is written."""
    out.mkdir(parents=True)
    copy = container(out, f'cp {DEMO}/demo_316_short.info {DEMO}/demo_316_short_scan_path.txt '
                          f'{DEMO}/integration_3d_gold_short.txt /case/')
    if copy.returncode:
        raise RuntimeError(copy.stderr)
    info = out / 'demo_316_short.info'
    text = info.read_text()
    if text.count('time_steps_between_output 10') != 1:
        raise RuntimeError('unexpected demo input')
    info.write_text(text.replace('time_steps_between_output 10', 'time_steps_between_output 1'))
    started = time.time()
    run = container(out, f'{BINARY} -i demo_316_short.info > log.adamantine 2>&1')
    if run.returncode:
        raise RuntimeError((out / 'log.adamantine').read_text()[-800:])
    last = final_vtu(out)[-1]
    # Cells above the material height (not yet deposited) are written with T = 0 K
    # and a default solid state; the gold vector holds only active degrees of freedom.
    temperature = read_vtu_array(last, 'temperature')
    simulated = [t for t in temperature if t > 0]
    gold = [float(v) for v in (out / 'integration_3d_gold_short.txt').read_text().split()]
    s, g = stats(simulated), stats(gold)
    # The upstream test checks every value lies in (285, 580) K and, on 1 or 2 ranks,
    # each degree of freedom against the gold file at 10 % relative tolerance. Output
    # files hold vertex values in a different order, so only range statistics compare.
    checks = {'all_in_285_580': 285 < s['min'] and s['max'] < 580,
              'max_within_10pct_of_gold': abs(s['max'] - g['max']) <= 0.1 * g['max'],
              'mean_within_10pct_of_gold': abs(s['mean'] - g['mean']) <= 0.1 * g['mean']}
    return {'case': 'demo_316_short', 'solver_seconds': round(time.time() - started, 1), 'cpus': 1,
            'final_output': last.name, 'final_output_sha256': sha(last),
            'inputs_sha256': {p.name: sha(p) for p in (info, out / 'demo_316_short_scan_path.txt')},
            'gold_sha256': sha(out / 'integration_3d_gold_short.txt'),
            'active_vertices_of': len(temperature),
            'temperature_vertices': s, 'gold_dofs': g, 'checks': checks, 'passed': all(checks.values())}


PIPELINE_INFO = """geometry
{{
  dim 3
  import_mesh true
  mesh_file part.msh
  mesh_format gmsh
  reset_material_id true
}}
units
{{
  mesh millimeter
  heat_source
  {{
    dimension millimeter
    scan_path millimeter
    velocity millimeter/second
  }}
}}
boundary {{ type convective,radiative }}
physics {{ thermal true mechanical false }}
refinement {{ n_refinements 0 time_steps_between_refinement 2000000000 }}
materials
{{
  n_materials 1
  property_format polynomial
  material_0
  {{
    solid {{ density 7904 specific_heat 714 thermal_conductivity_x 31.4 thermal_conductivity_y 31.4
            thermal_conductivity_z 31.4 convection_heat_transfer_coef 100 emissivity 0.15 }}
    powder {{ density 7904 specific_heat 714 thermal_conductivity_x 0.314 thermal_conductivity_y 0.314
             thermal_conductivity_z 0.314 convection_heat_transfer_coef 100 emissivity 0.15 }}
    liquid {{ density 7904 specific_heat 847 thermal_conductivity_x 37.3 thermal_conductivity_y 37.3
             thermal_conductivity_z 37.3 convection_heat_transfer_coef 100 emissivity 0.15 }}
    solidus 1675
    liquidus 1708
    latent_heat 290000
    radiation_temperature_infty 300
    convection_temperature_infty 300
  }}
}}
sources
{{
  n_beams 1
  print_heat_input true
  beam_0
  {{
    type goldak
    depth {depth_mm}
    diameter {diameter_mm}
    scan_path_file scan_path.txt
    scan_path_file_format segment
    absorption_efficiency {eta}
    max_power {power_w}
  }}
}}
time_stepping {{ method forward_euler duration {duration_s} time_step {dt_s} }}
post_processor {{ filename_prefix output time_steps_between_output {output_every} }}
discretization {{ thermal {{ fe_degree 1 quadrature gauss }} }}
memory_space host
"""


def pipeline(stl, out, cell_mm=1.0, power_w=400.0, eta=0.3, speed=500.0, line=((-30, -15, 16), (30, -15, 16)),
             diameter_mm=2.0, depth_mm=0.5, dt_s=2e-4):
    # print_heat_input logs the power the solver actually deposits each step; its
    # integral against eta * P * t exposes how well the mesh resolves the source.
    """Corpus STL -> hex mesh -> one laser line along x on the slab top, thermal only."""
    out.mkdir(parents=True)
    mesh = subprocess.run([sys.executable, str(HERE / 'hexmesh.py'), str(stl), str(out / 'part.msh'),
                           '--cell-mm', str(cell_mm)], capture_output=True, text=True, check=True)
    mesh_summary = json.loads(mesh.stdout.strip().splitlines()[-1])
    (a, b) = line
    length = sum((q - p) ** 2 for p, q in zip(a, b)) ** 0.5
    scan_time = length / speed
    duration = scan_time + 0.05
    (out / 'scan_path.txt').write_text('Number of path segments\n2\nMode x y z pmod param\n'
                                       f'1 {a[0]} {a[1]} {a[2]} 0 1e-6\n'
                                       f'0 {b[0]} {b[1]} {b[2]} 1 {speed}\n')
    steps = round(duration / dt_s)
    (out / 'part.info').write_text(PIPELINE_INFO.format(depth_mm=depth_mm, diameter_mm=diameter_mm, eta=eta,
                                                        power_w=power_w, duration_s=duration, dt_s=dt_s,
                                                        output_every=max(1, steps // 30)))
    started = time.time()
    run = container(out, f'{BINARY} -i part.info > log.adamantine 2>&1', cpus=4)
    if run.returncode:
        raise RuntimeError((out / 'log.adamantine').read_text()[-1200:])
    log = (out / 'log.adamantine').read_text()
    heat = [float(x) for x in re.findall(r'Global Heat Input:\s*([0-9.eE+-]+)\s*W', log)]
    outputs = final_vtu(out)
    peak = 0.0
    for vtu in outputs:
        peak = max(peak, max(read_vtu_array(vtu, 'temperature')))
    final = read_vtu_array(outputs[-1], 'temperature')
    expected_j = eta * power_w * scan_time
    record = {'stl_sha256': sha(stl), 'mesh': mesh_summary, 'scan_line_mm': [list(a), list(b)],
              'power_w': power_w, 'absorption_efficiency': eta, 'speed_mm_s': speed, 'beam_diameter_mm': diameter_mm,
              'beam_depth_mm': depth_mm, 'time_step_s': dt_s, 'duration_s': round(duration, 6),
              'solver_seconds': round(time.time() - started, 1), 'cpus': 4,
              'inputs_sha256': {p.name: sha(p) for p in (out / 'part.info', out / 'scan_path.txt', out / 'part.msh')},
              'outputs': len(outputs), 'peak_temperature_k': round(peak, 1), 'final_temperature': stats(final),
              'expected_absorbed_energy_j': round(expected_j, 4), 'heat_input_log_entries': len(heat)}
    if heat:
        # print_heat_input reports the absorbed power each step; integrate it.
        record['logged_absorbed_energy_j'] = round(sum(heat) * dt_s, 4)
        record['energy_ratio'] = round(record['logged_absorbed_energy_j'] / expected_j, 4)
    record['checks'] = {'completed': True, 'heated_above_ambient': peak > 350.0,
                        'energy_within_5pct': abs(record.get('energy_ratio', 0) - 1) <= 0.05}
    record['passed'] = all(record['checks'].values())
    return record


# Workaround for adamantine 1.1 (still on master 5aca53e; reported as adamantine #503): validate_input_database.cc
# checks database.count("geometry.material_deposition_file") on the root tree, and
# ptree::count matches only direct child keys, so file-based deposition is always
# rejected. A root key with that literal name satisfies the check; the deposition
# reader still takes the value from the geometry block.
LAYERS_INFO = """geometry.material_deposition_file layers.txt
geometry
{{
  dim 3
  import_mesh true
  mesh_file part.msh
  mesh_format gmsh
  reset_material_id true
  material_height {material_height_m}
  material_deposition true
  material_deposition_method file
  material_deposition_file layers.txt
}}
units {{ mesh millimeter }}
boundary
{{
  type convective,radiative,traction_free
  boundary_1 {{ type convective,radiative,clamped }}
}}
physics {{ thermal true mechanical true }}
refinement {{ n_refinements 0 time_steps_between_refinement 2000000000 }}
materials
{{
  n_materials 1
  property_format polynomial
  initial_temperature 300
  new_material_temperature {new_material_temperature_k}
  material_0
  {{
    solid {{ density 7904 specific_heat 714 thermal_conductivity_x 31.4 thermal_conductivity_y 31.4
            thermal_conductivity_z 31.4 convection_heat_transfer_coef 100 emissivity 0.15
            lame_first_parameter 92.0e9 lame_second_parameter 79.0e9 thermal_expansion_coef 17.2e-6 }}
    powder {{ density 7904 specific_heat 714 thermal_conductivity_x 0.314 thermal_conductivity_y 0.314
             thermal_conductivity_z 0.314 convection_heat_transfer_coef 100 emissivity 0.15
             lame_first_parameter 92.0e9 lame_second_parameter 79.0e9 thermal_expansion_coef 17.2e-6 }}
    liquid {{ density 7904 specific_heat 847 thermal_conductivity_x 37.3 thermal_conductivity_y 37.3
             thermal_conductivity_z 37.3 convection_heat_transfer_coef 100 emissivity 0.15
             lame_first_parameter 92.0e9 lame_second_parameter 79.0e9 thermal_expansion_coef 17.2e-6 }}
    solidus 1675
    liquidus 1708
    latent_heat 290000
    radiation_temperature_infty 300
    convection_temperature_infty 300
  }}
}}
sources
{{
  n_beams 1
  beam_0
  {{
    type goldak
    depth 1e-3
    diameter 1e-3
    scan_path_file scan_path.txt
    scan_path_file_format segment
    absorption_efficiency 0
    max_power 0
  }}
}}
time_stepping {{ method forward_euler duration {duration_s} time_step {dt_s} mechanical_time_step_factor {mech_factor} }}
post_processor {{ filename_prefix output time_steps_between_output {output_every} }}
discretization {{ thermal {{ fe_degree 1 quadrature gauss }} mechanical {{ fe_degree 1 }} }}
memory_space host
"""


def layers(stl, out, cell_mm=1.0, plate_mm=5.0, layer_mm=1.0, interval_s=2.0, cool_s=60.0, dt_s=0.02,
           mech_factor=50, new_material_temperature_k=1720.0, max_layers=None, offset_mm=0.0):
    """Lumped-layer build on a clamped plate, linear thermo-elastic, as a comparison between variants.

    Each layer of the part is activated at new_material_temperature_k, above the liquidus, so its
    stress-free reference is the solidus; the plate starts at 300 K. No heat source is used."""
    out.mkdir(parents=True)
    mesh = subprocess.run([sys.executable, str(HERE / 'hexmesh.py'), str(stl), str(out / 'part.msh'),
                           '--cell-mm', str(cell_mm), '--plate-mm', str(plate_mm), '--offset-mm', str(offset_mm)],
                          capture_output=True, text=True, check=True)
    summary = json.loads(mesh.stdout.strip().splitlines()[-1])
    z0, z1 = summary['plate_top_mm'], summary['top_mm']
    nx, ny, _ = summary['grid']
    # The deposition boxes cover the grid footprint; only cells of the imported mesh activate.
    lo_x, lo_y = None, None
    nodes = []
    with open(out / 'part.msh') as stream:
        for line in stream:
            if line.startswith('$Nodes'):
                count = int(next(stream))
                for _ in range(count):
                    _, x, y, z = next(stream).split()
                    nodes.append((float(x), float(y)))
                break
    xs, ys = [n[0] for n in nodes], [n[1] for n in nodes]
    cx, cy, sx, sy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    count = int(round((z1 - z0) / layer_mm))
    if max_layers:
        count = min(count, max_layers)
    rows = ['3']
    for k in range(count):
        zc = z0 + (k + 0.5) * layer_mm
        # Boxes touching the next cell layer would activate it too, so keep 1 % clear at each face.
        rows.append(' '.join(f'{v:.6g}' for v in (cx * 1e-3, cy * 1e-3, zc * 1e-3, sx * 1e-3, sy * 1e-3,
                                                     (layer_mm - 0.02 * cell_mm) * 1e-3, (k + 1) * interval_s, 0.0)))
    (out / 'layers.txt').write_text('\n'.join(rows) + '\n')
    duration = count * interval_s + cool_s
    (out / 'scan_path.txt').write_text(f'Number of path segments\n2\nMode x y z pmod param\n'
                                       f'1 {cx} {cy} {z1} 0 {duration}\n')
    steps = round(duration / dt_s)
    (out / 'part.info').write_text(LAYERS_INFO.format(
        material_height_m=z0 * 1e-3, new_material_temperature_k=new_material_temperature_k,
        duration_s=duration, dt_s=dt_s, mech_factor=mech_factor, output_every=max(mech_factor, steps // 20)))
    started = time.time()
    run = container(out, f'{BINARY} -i part.info > log.adamantine 2>&1', cpus=4, timeout=6 * 3600)
    log = (out / 'log.adamantine').read_text()
    outputs = sorted(Path(out).glob('output.*.0.vtu'), key=lambda p: int(p.name.split('.')[1]))
    if run.returncode or not outputs:
        raise RuntimeError(log[-1500:])
    return {'stl_sha256': sha(stl), 'mesh': summary, 'layers': count, 'layer_mm': layer_mm,
            'interval_s': interval_s, 'cool_s': cool_s, 'duration_s': duration, 'time_step_s': dt_s,
            'mechanical_time_step_factor': mech_factor, 'new_material_temperature_k': new_material_temperature_k,
            'solver_seconds': round(time.time() - started, 1), 'cpus': 4, 'outputs': len(outputs),
            'inputs_sha256': {p.name: sha(p) for p in (out / 'part.info', out / 'layers.txt', out / 'part.msh')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('smoke', 'pipeline', 'layers'))
    parser.add_argument('stl', nargs='?', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--cell-mm', type=float, default=1.0, help='hex cell size for pipeline and layers')
    parser.add_argument('--max-layers', type=int, help='layers: stop after this many layers (trials)')
    parser.add_argument('--cool-s', type=float, default=60.0, help='layers: cooling time after the last layer')
    parser.add_argument('--offset-mm', type=float, default=0.0, help='layers: shift the hex grid in x and y')
    args = parser.parse_args()
    if args.out.exists() or args.receipt.exists():
        parser.error('use a new output directory and receipt path')
    if args.mode == 'smoke':
        body = smoke(args.out)
    elif args.mode == 'pipeline':
        body = pipeline(args.stl, args.out, cell_mm=args.cell_mm)
    else:
        body = layers(args.stl, args.out, cell_mm=args.cell_mm, max_layers=args.max_layers, cool_s=args.cool_s,
                      offset_mm=args.offset_mm)
    record = {'schema': 'qwen-picogk.process.adamantine@1', 'mode': args.mode, 'image': IMAGE,
              'harness_sha256': sha(__file__), 'hexmesh_sha256': sha(HERE / 'hexmesh.py'),
              'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False, **body}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: record.get(k) for k in ('checks', 'passed', 'solver_seconds', 'outputs')}, indent=1))


if __name__ == '__main__':
    main()
