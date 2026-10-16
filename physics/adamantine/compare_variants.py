"""Compare lumped-layer thermo-elastic builds of design variants, with receipts.

    python physics/adamantine/compare_variants.py \
        --run solid=work/adamantine/layers-solid-TAG \
        --run dfam-001=work/adamantine/layers-dfam-001-TAG \
        --run debug-001=work/adamantine/layers-debug-001-TAG \
        --receipts work/adamantine --evidence evidence/process/NAME.json --out docs/visuals/process

Displacement is used, not adamantine's von Mises output, which omits the xz
shear term in release 1.1 (see docs/PART_SCALE_SIMULATION.md). Results compare
variants under one uncalibrated model; they are not predictions for a machine.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, __version__ as pillow_version  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_figures import decode, raster  # noqa: E402

BG, INK, MUTED, GRID = '#f6f8fa', '#193341', '#486270', '#dde3e8'
SERIES = ['#2a78d6', '#eb6834', '#1baf7a']          # validated categorical slots 1-3
SECTION = (-23.0, 23.0, -5.0, 32.0)                  # y, z extent of the x = 0 section (mm)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh(path):
    if path.exists() or path.with_suffix('.json').exists():
        raise SystemExit(f'{path} exists; never overwrite published figures')
    return path


def read(path):
    text = Path(path).read_text()

    def array(name):
        return decode(re.search(r'Name="%s"[^>]*format="binary">\s*([A-Za-z0-9+/=]+)' % name, text).group(1))
    points = decode(re.search(r'<Points>\s*<DataArray type="Float32" NumberOfComponents="3" format="binary">\s*'
                              r'([A-Za-z0-9+/=]+)', text).group(1)).reshape(-1, 3) * 1000.0
    time = float(re.search(r'Name="TIME"[^>]*>\s*([0-9.eE+-]+)', text).group(1))
    return {'points': points, 'temperature': array('temperature'),
            'displacement': array('displacement').reshape(-1, 3) * 1000.0, 'time': time}


def outputs(run):
    return sorted(Path(run).glob('output.*.0.vtu'), key=lambda p: int(p.name.split('.')[1]))


def metrics(run, receipt):
    files = outputs(run)
    last = read(files[-1])
    meta = json.loads(Path(receipt).read_text())
    p, T, u = last['points'], last['temperature'], last['displacement']
    active = T > 0
    magnitude = np.linalg.norm(u, axis=1)
    plate_bottom = np.abs(p[:, 2] - (meta['mesh']['plate_top_mm'] - meta['mesh']['plate_layers'] * meta['mesh']['cell_mm'])) < 1e-6
    part = active & (p[:, 2] > meta['mesh']['plate_top_mm'] + 1e-6)
    top_z = p[part, 2].max()
    top = part & (p[:, 2] > top_z - 1e-6)
    slab_top = part & (np.abs(p[:, 2] - 16.0) < 1e-6)
    peak_t = max(float(read(f)['temperature'].max()) for f in files[::max(1, len(files) // 10)])
    return {'final_time_s': last['time'], 'outputs': len(files),
            'final_temperature_active': {'min': round(float(T[active].min()), 1), 'max': round(float(T[active].max()), 1),
                                         'mean': round(float(T[active].mean()), 1)},
            'sampled_peak_temperature_k': round(peak_t, 1),
            'plate_bottom_max_displacement_mm': float(magnitude[plate_bottom].max()),
            'max_displacement_mm': round(float(magnitude[part].max()), 4),
            'max_displacement_at_mm': [round(float(v), 2) for v in p[part][np.argmax(magnitude[part])]],
            'slab_top_mean_uz_mm': round(float(u[slab_top, 2].mean()), 4) if slab_top.any() else None,
            'slab_top_uz_range_mm': (round(float(u[slab_top, 2].max() - u[slab_top, 2].min()), 4)
                                     if slab_top.any() else None),
            'top_layer_z_mm': round(float(top_z), 2),
            'solver_seconds': meta['solver_seconds'], 'stl_sha256': meta['stl_sha256'],
            'receipt_sha256': sha(receipt), 'final_output_sha256': sha(files[-1])}


def section_figure(runs, out):
    path = fresh(out / 'adamantine-layers-section.png')
    figure, axes = plt.subplots(1, len(runs), figsize=(4.0 * len(runs), 3.8), dpi=128, facecolor=BG, sharey=True)
    vmax = 0.0
    fields = []
    for name, run in runs.items():
        last = read(outputs(run)[-1])
        p, u, T = last['points'], last['displacement'], last['temperature']
        cut = (np.abs(p[:, 0]) < 0.51) & (T > 0)
        grid = raster(p[cut, 1], p[cut, 2], np.linalg.norm(u[cut], axis=1), SECTION, cell=1.0)
        fields.append((name, grid))
        vmax = max(vmax, np.nanmax(grid))
    for axis, (name, grid) in zip(axes, fields):
        image = axis.imshow(grid, origin='lower', extent=SECTION, cmap='magma', vmin=0, vmax=vmax,
                            interpolation='nearest')
        axis.set_title(name, color=INK, fontsize=10.5, loc='left')
        axis.set_xlabel('y (mm)', color=MUTED, fontsize=8.5)
        axis.tick_params(colors=MUTED, labelsize=8)
        axis.set_facecolor(BG)
        for side in axis.spines.values():
            side.set_color(GRID)
    axes[0].set_ylabel('z (mm), plate below 0', color=MUTED, fontsize=8.5)
    bar = figure.colorbar(image, ax=list(axes), fraction=0.02, pad=0.02)
    bar.set_label('displacement magnitude (mm)', color=MUTED, fontsize=8.5)
    bar.ax.tick_params(colors=MUTED, labelsize=7.5)
    figure.suptitle(f'Section x = 0 at t = {last["time"]:.0f} s, part still hot '
                    '(one model, three geometries)', color=INK, fontsize=11)
    figure.text(0.01, 0.005, 'adamantine 1.1, linear thermo-elastic, 1 mm layers at 1720 K on a clamped 5 mm plate; '
                'uncalibrated comparison, not a distortion prediction', color=MUTED, fontsize=7.5)
    figure.savefig(path, facecolor=BG, bbox_inches='tight')
    plt.close(figure)
    return path


def metric_figure(table, out):
    path = fresh(out / 'adamantine-layers-comparison.png')
    names = list(table)
    figure, axes = plt.subplots(1, 2, figsize=(9.6, 3.0), dpi=128, facecolor=BG)
    for axis, key, title in zip(axes, ('max_displacement_mm', 'slab_top_uz_range_mm'),
                                ('Maximum displacement (mm)', 'Warp of the slab top: range of u_z (mm)')):
        if any(table[n][key] is None for n in names):
            axis.set_axis_off()
            continue
        axis.set_facecolor(BG)
        for side in ('top', 'right'):
            axis.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            axis.spines[side].set_color(GRID)
        base = table[names[0]][key]
        for y, name in enumerate(names):
            value = table[name][key]
            axis.scatter(value, y, s=70, color=SERIES[y], edgecolor=BG, linewidth=2, zorder=3)
            change = '' if y == 0 else f'  ({(value - base) / base:+.1%} vs {names[0]})'
            axis.text(value, y + 0.28, f'{value:.3f}{change}', ha='center', color=INK, fontsize=8)
        axis.set_yticks(range(len(names)), names)
        axis.set_ylim(-0.6, len(names) - 0.2)
        span = max(table[n][key] for n in names) - min(table[n][key] for n in names)
        lo, hi = min(table[n][key] for n in names), max(table[n][key] for n in names)
        axis.set_xlim(lo - max(span, 0.02 * hi) * 1.5, hi + max(span, 0.02 * hi) * 1.5)
        axis.grid(axis='x', color=GRID, lw=0.6)
        axis.tick_params(colors=MUTED, labelsize=8.5)
        axis.set_title(title, color=INK, fontsize=10, loc='left')
    figure.tight_layout()
    figure.savefig(path, facecolor=BG)
    plt.close(figure)
    return path


def build_gif(run, name, out):
    path = fresh(out / f'adamantine-layers-{name}.gif')
    files = outputs(run)
    frames = []
    for f in files:
        data = read(f)
        p, T = data['points'], data['temperature']
        cut = (np.abs(p[:, 0]) < 0.51) & (T > 0)
        grid = raster(p[cut, 1], p[cut, 2], T[cut], SECTION, cell=1.0)
        figure, axis = plt.subplots(figsize=(5.4, 4.2), dpi=100, facecolor=BG)
        image = axis.imshow(grid, origin='lower', extent=SECTION, cmap='magma', vmin=300, vmax=1750,
                            interpolation='nearest')
        axis.set_facecolor(BG)
        axis.tick_params(colors=MUTED, labelsize=7.5)
        for side in axis.spines.values():
            side.set_color(GRID)
        axis.set_xlabel('y (mm)', color=MUTED, fontsize=8)
        axis.set_ylabel('z (mm)', color=MUTED, fontsize=8)
        axis.set_title(f'{name}, section x = 0, t = {data["time"]:.0f} s', color=INK, fontsize=10, loc='left')
        bar = figure.colorbar(image, ax=axis, fraction=0.04, pad=0.02)
        bar.set_label('T (K)', color=MUTED, fontsize=8)
        bar.ax.tick_params(colors=MUTED, labelsize=7)
        figure.tight_layout()
        figure.canvas.draw()
        frames.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
        plt.close(figure)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=180, loop=0, optimize=True, disposal=2)
    return path, len(frames)


def receipt(path, sources, **extra):
    record = {'image': path.name, 'image_sha256': sha(path), 'sources_sha256': sources,
              'render_source_sha256': sha(__file__),
              'renderer': f'matplotlib {matplotlib.__version__}, Pillow {pillow_version}, numpy {np.__version__}',
              'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False, **extra}
    path.with_suffix('.json').write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', action='append', required=True, help='NAME=RUN_DIRECTORY, first is the baseline')
    parser.add_argument('--receipts', type=Path, required=True, help='folder with layers-NAME.json run receipts')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--gif', default='dfam-001')
    args = parser.parse_args()
    if args.evidence.exists():
        parser.error('use a new evidence path')
    runs = dict(item.split('=', 1) for item in args.run)
    table = {name: metrics(run, args.receipts / f'layers-{name}.json') for name, run in runs.items()}
    checks = {name: {'plate_bottom_clamped': row['plate_bottom_max_displacement_mm'] == 0.0,
                     'cooled_below_600_k': row['final_temperature_active']['max'] < 600.0}
              for name, row in table.items()}
    args.out.mkdir(parents=True, exist_ok=True)
    section = section_figure(runs, args.out)
    comparison = metric_figure(table, args.out)
    gif, frames = build_gif(runs[args.gif], args.gif, args.out)
    evidence = {'schema': 'qwen-picogk.process.adamantine-layers@1', 'baseline': next(iter(runs)),
                'variants': table, 'checks': checks, 'analysis_sha256': sha(__file__),
                'displacement_not_von_mises': True, 'uncalibrated_for_any_machine': True,
                'manufacturing_qualified': False}
    args.evidence.write_text(json.dumps(evidence, indent=1, sort_keys=True) + '\n')
    for path in (section, comparison):
        receipt(path, {args.evidence.name: sha(args.evidence)})
    receipt(gif, {args.evidence.name: sha(args.evidence)}, frames=frames, frame_ms=180)
    print(json.dumps({'checks': checks, 'max_displacement_mm': {n: r['max_displacement_mm'] for n, r in table.items()},
                      'slab_top_uz_range_mm': {n: r['slab_top_uz_range_mm'] for n, r in table.items()}}, indent=1))


if __name__ == '__main__':
    main()
