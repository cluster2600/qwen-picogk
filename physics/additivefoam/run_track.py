"""Run AdditiveFOAM single tracks in the pinned container and record evidence.

Phase 2 of docs/PHYSICS_EVIDENCE_PLAN.md. Every case starts from the upstream
AMB2018-02-B tutorial inside the image (it is copied into an ignored work
directory, never into the repository), is edited with OpenFOAM's
foamDictionary, and runs offline with capped memory, CPUs and processes.

    run_track.py smoke --out work/process/smoke-TAG --receipt evidence/process/NAME.json
    run_track.py sweep --out work/process/sweep-TAG --receipt evidence/process/NAME.json

Results are uncalibrated simulation trends, not process qualification.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

IMAGE = 'qwen-picogk/additivefoam:2.0.0-9c05c5e'
ADDITIVEFOAM_COMMIT = '9c05c5eb54db03faa342b14b0806efe740de8c44'
TUTORIAL = '/opt/AdditiveFOAM/tutorials/AMB2018-02-B'
RANKS = 8
TRACK_M = 0.002                 # 2 mm single track along +x, as in the tutorial
STEADY_FRACTION = (0.4, 0.9)    # beam between 0.8 and 1.8 mm: past start-up, before the end

# NIST AM-Bench AMB2018-02, AMMT case B: true power 179.2 W, 800 mm/s, melt-pool
# length 359 +/- 20 um (n = 10), in-situ thermography at a 1290 degC solidus.
# https://www.nist.gov/ambench/chal-amb2018-02-mp-length
AMB_B = {'power_w': 179.2, 'speed_m_s': 0.8, 'length_um': 359.0, 'length_sd_um': 20.0, 'n': 10,
         'isotherm_k': 1290 + 273.15}

# Assumed process for the 316L indicators (not machine data).
LAYER_M, HATCH_M = 40e-6, 100e-6


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_sha(folder):
    """One hash over every file below folder, by relative path and content."""
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(folder).rglob('*') if p.is_file()):
        digest.update(str(path.relative_to(folder)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def container(case, command, timeout=3600):
    """Run one shell command in the case directory, offline and capped."""
    cmd = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp:exec,size=2g',
           '--shm-size', '2g', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
           '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '12g', '--memory-swap', '12g',
           '--cpus', str(RANKS), '--pids-limit', '1024', '-v', f'{Path(case).resolve()}:/case', '-w', '/case',
           IMAGE, 'bash', '-c', command]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def image_id():
    out = subprocess.run(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def prepare(case, material, power_w, speed_m_s, isotherms_k, write_interval_s=None, eta=None, radius_m=None,
            refine=1):
    """Copy the tutorial and set the case parameters with foamDictionary. refine
    divides the tutorial's uniform 20 um cells, for mesh-convergence checks."""
    case.mkdir(parents=True)
    run = container(case, f'cp -r {TUTORIAL}/. /case/')
    if run.returncode:
        raise RuntimeError('tutorial copy failed: ' + run.stderr[-400:])
    scan_time = TRACK_M / speed_m_s
    end_time = scan_time + 0.0015                      # cooling after the beam stops
    (case / 'constant/scanPath').write_text(
        'Mode    X       Y       Z   Power   Param\n'
        '1       0.000   0.000   0   0       0\n'
        f'0       {TRACK_M:.3f}   0.000   0   {power_w:g}   {speed_m_s:g}\n')
    props = case / 'constant/transportProperties'
    text = props.read_text()
    if 'materials/IN625.cfg' not in text:
        raise RuntimeError('unexpected tutorial transportProperties')
    props.write_text(text.replace('materials/IN625.cfg', f'materials/{material}.cfg'))
    mesh = case / 'system/blockMeshDict'
    text = mesh.read_text()
    if text.count('(150 25 15)') != 1:
        raise RuntimeError('unexpected tutorial blockMeshDict')
    mesh.write_text(text.replace('(150 25 15)', f'({150 * refine} {25 * refine} {15 * refine})'))
    sets = [('system/controlDict', 'endTime', f'{end_time:.6g}'),
            ('system/controlDict', 'writeFormat', 'ascii'),
            ('system/controlDict', 'writeInterval', f'{write_interval_s or end_time:.6g}'),
            ('system/controlDict', 'functions/meltPoolDimensions/enabled', 'true'),
            ('system/controlDict', 'functions/meltPoolDimensions/isoValues',
             '(' + ' '.join(f'{t:g}' for t in isotherms_k) + ')'),
            ('system/decomposeParDict', 'numberOfSubdomains', str(RANKS))]
    if eta is not None:
        sets.append(('constant/heatSourceDict', 'sources/beam/absorption/eta', f'{eta:g}'))
    if radius_m is not None:
        sets.append(('constant/heatSourceDict', 'sources/beam/heatSource/radius', f'({radius_m:g} {radius_m:g})'))
    script = ' && '.join(f'foamDictionary {f} -entry {e} -set "{v}" > /dev/null' for f, e, v in sets)
    run = container(case, script)
    if run.returncode:
        raise RuntimeError('foamDictionary failed: ' + (run.stderr or run.stdout)[-600:])
    return {'material': material, 'power_w': power_w, 'speed_m_s': speed_m_s, 'track_m': TRACK_M,
            'end_time_s': round(end_time, 9), 'isotherms_k': list(isotherms_k),
            'eta': eta, 'radius_m': radius_m, 'cell_um': 20.0 / refine}


def solve(case):
    started = time.time()
    run = container(case, 'blockMesh > log.blockMesh 2>&1 && decomposePar > log.decomposePar 2>&1 '
                          f'&& mpirun -np {RANKS} additiveFoam -parallel > log.additiveFoam 2>&1 '
                          '&& reconstructPar > log.reconstructPar 2>&1')
    if run.returncode:
        log = case / 'log.additiveFoam'
        tail = log.read_text()[-800:] if log.exists() else run.stderr[-800:]
        raise RuntimeError(f'solver failed in {case}: {tail}')
    return round(time.time() - started, 1)


def read_dimensions(path):
    with open(path, newline='') as stream:
        rows = list(csv.DictReader(stream))
    return [{'t': float(r['time(s)']), 'length': float(r['length(m)']), 'width': float(r['width(m)']),
             'depth': float(r['depth(m)'])} for r in rows]


def steady(rows, speed_m_s):
    """Mean and spread of the dimensions while the beam is in the steady window."""
    t0, t1 = (f * TRACK_M / speed_m_s for f in STEADY_FRACTION)
    window = [r for r in rows if t0 <= r['t'] <= t1]
    if len(window) < 5:
        raise ValueError(f'only {len(window)} samples in the steady window {t0:.6f}-{t1:.6f} s')
    out = {'samples': len(window), 'window_s': [round(t0, 9), round(t1, 9)]}
    for key in ('length', 'width', 'depth'):
        values = [r[key] for r in window]
        mean = sum(values) / len(values)
        sd = (sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)) ** 0.5
        out[f'{key}_um'] = round(mean * 1e6, 2)
        out[f'{key}_sd_um'] = round(sd * 1e6, 2)
    return out


def indicators(width_um, depth_um, layer_m=LAYER_M, hatch_m=HATCH_M):
    """Geometric lack-of-fusion criterion of Tang, Pistorius and Beuth (2017):
    full overlap needs (h/W)^2 + (L/D)^2 <= 1. A depth over half the width is
    outside the conduction regime this model represents (no vapour physics)."""
    w, d = width_um * 1e-6, depth_um * 1e-6
    lof = (hatch_m / w) ** 2 + (layer_m / d) ** 2 if w > 0 and d > 0 else float('inf')
    return {'lack_of_fusion_criterion': round(lof, 3), 'lack_of_fusion_risk': lof > 1,
            'depth_over_width': round(d / w, 3) if w > 0 else None,
            'beyond_conduction_model': w > 0 and d / w > 0.5}


def provenance(case_inputs_sha=None):
    return {'image': IMAGE, 'image_id': image_id(), 'additivefoam_commit': ADDITIVEFOAM_COMMIT,
            'tutorial': 'tutorials/AMB2018-02-B', 'ranks': RANKS,
            'harness_sha256': sha(__file__), 'dockerfile_sha256': sha(Path(__file__).with_name('Dockerfile'))}


def run_case(root, name, **params):
    case = root / name
    meta = prepare(case, **params)
    inputs = {d: tree_sha(case / d) for d in ('0', 'constant', 'system')}
    seconds = solve(case)
    results = {}
    for iso in params['isotherms_k']:
        csv_path = case / 'postProcessing/meltPoolDimensions' / f'{iso:g}.csv'
        rows = read_dimensions(csv_path)
        results[f'{iso:g}'] = dict(steady(rows, params['speed_m_s']), csv_sha256=sha(csv_path))
    return {'case': name, 'parameters': meta, 'inputs_sha256': inputs, 'solver_seconds': seconds,
            'melt_pool': results}


def smoke(root, refine=1):
    """AMB2018-02-B as shipped (IN625, calibrated source), with NIST's isotherm added."""
    iso = [AMB_B['isotherm_k'], 1620.0, 1410.0]      # NIST solidus; model liquidus and solidus
    record = run_case(root, 'amb2018-02-b', material='IN625', power_w=AMB_B['power_w'],
                      speed_m_s=AMB_B['speed_m_s'], isotherms_k=iso, write_interval_s=1e-4, refine=refine)
    length = record['melt_pool'][f"{AMB_B['isotherm_k']:g}"]['length_um']
    lo, hi = AMB_B['length_um'] - 2 * AMB_B['length_sd_um'], AMB_B['length_um'] + 2 * AMB_B['length_sd_um']
    record['comparison'] = {
        'reference': 'NIST AM-Bench AMB2018-02 AMMT case B melt-pool length (in-situ thermography, 1290 degC)',
        'reference_url': 'https://www.nist.gov/ambench/chal-amb2018-02-mp-length',
        'measured_length_um': AMB_B['length_um'], 'measured_sd_um': AMB_B['length_sd_um'], 'n': AMB_B['n'],
        'simulated_length_um_at_1290C': length, 'acceptance': 'within measured mean +/- 2 SD',
        'within_2sd': lo <= length <= hi}
    return record


def sweep(root, powers=(150, 200, 250, 300, 350), speeds=(0.6, 0.8, 1.0, 1.2, 1.4)):
    """316L power-speed grid with the tutorial's IN625-calibrated source (uncalibrated for 316L)."""
    liquidus = 1709.0
    cases = []
    for p in powers:
        for v in speeds:
            name = f'ss316l-P{p}-V{int(v * 1000)}'
            record = run_case(root, name, material='SS316L', power_w=float(p), speed_m_s=v, isotherms_k=[liquidus])
            pool = record['melt_pool'][f'{liquidus:g}']
            record['indicators'] = indicators(pool['width_um'], pool['depth_um'])
            cases.append(record)
            print(f"{name}: W {pool['width_um']} um, D {pool['depth_um']} um, "
                  f"LoF {record['indicators']['lack_of_fusion_criterion']}", flush=True)
    return {'material': 'SS316L', 'isotherm_k': liquidus, 'layer_m': LAYER_M, 'hatch_m': HATCH_M,
            'heat_source': 'tutorial superGaussian k=2, second-moment radius 85 um, depth 30 um, eta 0.33 '
                           '(calibrated for IN625 on the AMMT; transferred to 316L without calibration)',
            'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('smoke', 'sweep'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--refine', type=int, default=1, help='divide the 20 um cells (smoke only)')
    args = parser.parse_args()
    if args.out.exists() or args.receipt.exists():
        parser.error('Use a new output directory and receipt path; never overwrite evidence')
    args.out.mkdir(parents=True)
    body = smoke(args.out, args.refine) if args.mode == 'smoke' else sweep(args.out)
    record = {'schema': 'qwen-picogk.process.additivefoam@1', 'mode': args.mode, 'provenance': provenance(),
              'uncalibrated_for_any_machine': args.mode == 'sweep', 'manufacturing_qualified': False, **body}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
    print(json.dumps(record.get('comparison', {}), indent=1))


if __name__ == '__main__':
    main()
