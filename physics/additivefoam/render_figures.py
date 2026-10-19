"""Render the Phase 2 process figures from AdditiveFOAM evidence, with receipts.

    python physics/additivefoam/render_figures.py \
        --smoke20 evidence/process/additivefoam-smoke-amb2018-02-b-20um.json \
        --smoke10 evidence/process/additivefoam-smoke-amb2018-02-b-10um.json \
        --sweep evidence/process/additivefoam-316l-single-track-sweep.json \
        --case work/process/smoke-final-20261015/amb2018-02-b --out docs/visuals/process

The GIF reads the ASCII temperature fields of the reconstructed 20 um smoke
case (uniform 150 x 25 x 15 blockMesh grid, x fastest). Existing figures are
never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from PIL import Image, __version__ as pillow_version  # noqa: E402

BG, INK, MUTED, GRID = '#f6f8fa', '#193341', '#486270', '#dde3e8'
SERIES = ['#2a78d6', '#eb6834']          # validated categorical slots 1-2 on BG
BLUES = LinearSegmentedColormap.from_list('blue-ramp', ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5',
                                                        '#256abf', '#184f95', '#0d366b'])
GRID_SHAPE = (15, 25, 150)               # z, y, x cells of the tutorial blockMesh
X_MM, Y_MM, Z_MM = (-0.5, 2.5), (-0.25, 0.25), (-0.3, 0.0)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh(path):
    if path.exists() or path.with_suffix('.json').exists():
        raise SystemExit(f'{path} exists; never overwrite published figures')
    return path


def receipt(path, sources, **extra):
    record = {'image': path.name, 'image_sha256': sha(path), 'sources_sha256': sources,
              'render_source_sha256': sha(__file__),
              'renderer': f'matplotlib {matplotlib.__version__}, Pillow {pillow_version}, numpy {np.__version__}',
              'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False, **extra}
    path.with_suffix('.json').write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')


def style(axis):
    axis.set_facecolor(BG)
    for side in ('top', 'right'):
        axis.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=MUTED, labelsize=8.5)


def length_check(smoke20, smoke10, out):
    """Dot plot: simulated steady length per isotherm and mesh against NIST's band."""
    path = fresh(out / 'amb2018-length-check.png')
    runs = [('20 um cells', json.loads(Path(smoke20).read_text())),
            ('10 um cells', json.loads(Path(smoke10).read_text()))]
    ref = runs[0][1]['comparison']
    rows = [('1563.15', '1290 degC\n(NIST threshold)'), ('1410', '1410 K\n(model solidus)'),
            ('1620', '1620 K\n(model liquidus)')]
    figure, axis = plt.subplots(figsize=(7.6, 3.6), dpi=128, facecolor=BG)
    style(axis)
    mean, sd = ref['measured_length_um'], ref['measured_sd_um']
    axis.axvspan(mean - 2 * sd, mean + 2 * sd, color='#e4e9ed', zorder=0, label='NIST mean +/- 2 SD')
    axis.axvline(mean, color=MUTED, lw=1.2, zorder=1)
    axis.text(mean, len(rows) - 0.35, f'NIST case B: {mean:.0f} +/- {sd:.0f} um (n = {ref["n"]})',
              ha='center', va='bottom', color=MUTED, fontsize=8.5)
    for s, (label, run) in enumerate(runs):
        ys = [len(rows) - 1 - i + (0.12 if s else -0.12) for i in range(len(rows))]
        xs = [run['melt_pool'][key]['length_um'] for key, _ in rows]
        axis.scatter(xs, ys, s=64, color=SERIES[s], edgecolor=BG, linewidth=2, zorder=3, label=label)
        axis.text(xs[0] + 6, ys[0], f'{xs[0]:.0f}', va='center', color=INK, fontsize=8.5)
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels([lab for _, lab in rows][::-1], color=INK, fontsize=8.5)
    axis.set_ylim(-0.6, len(rows) - 0.1)
    axis.set_xlim(220, 420)
    axis.set_xlabel('steady melt-pool length (um), IN625, 179.2 W, 800 mm/s', color=MUTED, fontsize=9)
    axis.grid(axis='x', color=GRID, lw=0.6)
    axis.legend(loc='lower right', frameon=False, fontsize=8.5)
    axis.set_title('Smoke test: AdditiveFOAM vs NIST AM-Bench length (fails at the NIST isotherm)',
                   color=INK, fontsize=10.5, loc='left')
    figure.tight_layout()
    figure.savefig(path, facecolor=BG)
    plt.close(figure)
    receipt(path, {Path(smoke20).name: sha(smoke20), Path(smoke10).name: sha(smoke10)},
            reference_url=ref['reference_url'])


def process_map(sweep, out):
    """Small multiples: width and depth over speed and power, with the lack-of-fusion boundary."""
    path = fresh(out / '316l-process-map.png')
    record = json.loads(Path(sweep).read_text())
    iso = f"{record['isotherm_k']:g}"
    powers = sorted({c['parameters']['power_w'] for c in record['cases']})
    speeds = sorted({c['parameters']['speed_m_s'] for c in record['cases']})
    grid = {k: np.zeros((len(powers), len(speeds))) for k in ('width_um', 'depth_um', 'lof')}
    for c in record['cases']:
        i, j = powers.index(c['parameters']['power_w']), speeds.index(c['parameters']['speed_m_s'])
        grid['width_um'][i, j] = c['melt_pool'][iso]['width_um']
        grid['depth_um'][i, j] = c['melt_pool'][iso]['depth_um']
        grid['lof'][i, j] = c['indicators']['lack_of_fusion_criterion']
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.4), dpi=128, facecolor=BG)
    for axis, key, label in zip(axes, ('width_um', 'depth_um'), ('melt-pool width (um)', 'melt-pool depth (um)')):
        image = axis.imshow(grid[key], origin='lower', cmap=BLUES, aspect='auto')
        axis.contour(grid['lof'], levels=[1.0], colors=INK, linewidths=1.6)
        ok = np.argwhere(grid['lof'] <= 1.0)
        axis.scatter(ok[:, 1], ok[:, 0], marker='o', s=26, color=BG, edgecolor=INK, linewidth=1.2,
                     label='full overlap: criterion <= 1')
        axis.set_xticks(range(len(speeds)), [f'{v * 1000:.0f}' for v in speeds])
        axis.set_yticks(range(len(powers)), [f'{p:.0f}' for p in powers])
        axis.set_xlabel('scan speed (mm/s)', color=MUTED, fontsize=9)
        axis.set_ylabel('laser power (W)', color=MUTED, fontsize=9)
        axis.tick_params(colors=MUTED, labelsize=8.5)
        bar = figure.colorbar(image, ax=axis, fraction=0.05, pad=0.03)
        bar.set_label(label, color=MUTED, fontsize=9)
        bar.ax.tick_params(colors=MUTED, labelsize=8)
        bar.outline.set_visible(False)
        axis.set_title(label.split(' (')[0].capitalize(), color=INK, fontsize=10.5, loc='left')
    axes[0].legend(loc='lower right', frameon=True, fontsize=8, facecolor=BG, edgecolor=GRID)
    figure.suptitle('316L single tracks, AdditiveFOAM (uncalibrated): black line = lack-of-fusion criterion 1 '
                    f'(layer {record["layer_m"] * 1e6:.0f} um, hatch {record["hatch_m"] * 1e6:.0f} um)',
                    color=INK, fontsize=10.5)
    figure.text(0.5, 0.01, 'Heat source transferred from the IN625 AM-Bench calibration (beam D4sigma 170 um); '
                'trends only, not a process window for any machine', ha='center', color=MUTED, fontsize=8.5)
    figure.tight_layout(rect=(0, 0.04, 1, 0.94))
    figure.savefig(path, facecolor=BG)
    plt.close(figure)
    receipt(path, {Path(sweep).name: sha(sweep)}, isotherm_k=record['isotherm_k'])


# Expanded uncertainty (k = 2) of the AMMT-20 us melt-pool lengths, Lane et al.
# (2020) Table 5; Table 4's lengths come from those measurements.
LENGTH_U_K2_UM = {'A': 11.91, 'B': 21.26, 'C': 32.57}


def validation(record_path, out):
    """Small multiples: measured vs simulated length, width and depth for cases A, B and C."""
    path = fresh(out / 'amb2018-abc-validation.png')
    record = json.loads(Path(record_path).read_text())
    iso = f"{record['isotherm_k']:g}"
    names = ['A', 'B', 'C']
    cases = {c['case'][-1].upper(): c for c in record['cases']}
    figure, axes = plt.subplots(1, 3, figsize=(10.4, 4.2), dpi=128, facecolor=BG)
    for axis, key, title in zip(axes, ('length', 'width', 'depth'), ('Length', 'Width', 'Depth')):
        style(axis)
        for i, name in enumerate(names):
            ref, pool = cases[name]['reference'], cases[name]['melt_pool'][iso]
            measured = ref[f'{key}_um']
            if key == 'length':
                band = 2 * ref['length_sd_um']
                axis.errorbar(i - 0.1, measured, yerr=LENGTH_U_K2_UM[name], fmt='none', ecolor=SERIES[0],
                              elinewidth=1.4, capsize=3, zorder=2)
            else:
                band = 0.1 * measured
            axis.add_patch(plt.Rectangle((i - 0.32, measured - band), 0.64, 2 * band, color='#e4e9ed', zorder=0,
                                         label='acceptance band' if i == 0 else None))
            axis.scatter(i - 0.1, measured, s=60, color=SERIES[0], edgecolor=BG, linewidth=2, zorder=3,
                         label='measured (NIST AMMT)' if i == 0 else None)
            axis.scatter(i + 0.1, pool[f'{key}_um'], s=60, color=SERIES[1], edgecolor=BG, linewidth=2, zorder=3,
                         label='AdditiveFOAM at 1290 degC' if i == 0 else None)
            passed = cases[name]['checks']['length_within_2sd' if key == 'length' else f'{key}_within_10pct']
            axis.text(i + 0.22, pool[f'{key}_um'], 'pass' if passed else 'fail', va='center', fontsize=8,
                      color=INK if passed else '#b3261e', fontweight='bold')
        speeds = [f"{name}\n{cases[name]['reference']['speed_m_s'] * 1000:.0f} mm/s" for name in names]
        axis.set_xticks(range(3), speeds)
        axis.set_xlim(-0.6, 2.7)
        axis.set_title(f'{title} (um)', color=INK, fontsize=10.5, loc='left')
        axis.grid(axis='y', color=GRID, lw=0.6)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc='lower center', ncol=3, frameon=False, fontsize=8.5,
                  bbox_to_anchor=(0.5, 0.045))
    figure.suptitle('AM-Bench AMB2018-02, IN625: cross-section width matches; melt-pool length does not',
                    color=INK, fontsize=11)
    figure.text(0.5, 0.01, 'Bands: length mean +/- 2 SD, width and depth +/- 10 %, fixed before cases A and C '
                'were run. Error bars: expanded length uncertainty (k = 2), Lane et al. 2020 Table 5.',
                ha='center', color=MUTED, fontsize=7.8)
    figure.tight_layout(rect=(0, 0.12, 1, 0.93))
    figure.savefig(path, facecolor=BG)
    plt.close(figure)
    receipt(path, {Path(record_path).name: sha(record_path)}, length_u_k2_um=LENGTH_U_K2_UM)


def read_field(path):
    text = Path(path).read_text()
    uniform = re.search(r'internalField\s+uniform\s+([0-9.eE+-]+)\s*;', text)
    if uniform:
        return np.full(int(np.prod(GRID_SHAPE)), float(uniform.group(1)))
    match = re.search(r'internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(', text)
    n, start = int(match.group(1)), match.end()
    values = np.array(text[start:text.index(')', start)].split(), dtype=float)
    if len(values) != n or n != int(np.prod(GRID_SHAPE)):
        raise ValueError(f'{path}: {len(values)} values, expected {np.prod(GRID_SHAPE)}')
    return values


def melt_pool_gif(case, smoke20, out):
    """Top view and centre section of the moving melt pool from the 20 um smoke case."""
    path = fresh(out / 'amb2018-melt-pool.gif')
    record = json.loads(Path(smoke20).read_text())
    speed = record['parameters']['speed_m_s']
    times = sorted((d for d in Path(case).iterdir() if d.is_dir() and re.fullmatch(r'[0-9.e-]+', d.name)
                    and float(d.name) > 0 and (d / 'T').exists()), key=lambda d: float(d.name))
    scan_end = record['parameters']['track_m'] / speed
    frames, digest = [], hashlib.sha256()
    for folder in times:
        digest.update((folder / 'T').read_bytes())
        T = read_field(folder / 'T').reshape(GRID_SHAPE)
        t = float(folder.name)
        figure, (top, side) = plt.subplots(2, 1, figsize=(7.2, 4.3), dpi=110, facecolor=BG,
                                           gridspec_kw={'height_ratios': [5, 7.5]})
        for axis, field, extent, ylabel, aspect in (
                (top, T[-1], (*X_MM, *Y_MM), 'y (mm)', 1.0),
                (side, T[:, GRID_SHAPE[1] // 2, :], (*X_MM, *Z_MM), 'z (mm) x2.5', 2.5)):
            image = axis.imshow(field, origin='lower', extent=extent, cmap='magma', vmin=300, vmax=2400,
                                aspect=aspect, interpolation='bilinear')
            if field.max() > 1563.15:
                xs = np.linspace(*X_MM, field.shape[1])
                ys = np.linspace(*extent[2:], field.shape[0])
                axis.contour(xs, ys, field, levels=[1563.15], colors=INK, linewidths=1.3)
                axis.contour(xs, ys, field, levels=[1620.0], colors=INK, linewidths=1.0, linestyles='--')
            axis.set_xlim(-0.2, 2.3)
            axis.set_ylabel(ylabel, color=MUTED, fontsize=8)
            axis.tick_params(colors=MUTED, labelsize=7.5)
        side.set_xlabel('x (mm), scan direction', color=MUTED, fontsize=8)
        beam = min(t, scan_end) * speed * 1000
        state = f'beam at x = {beam:.2f} mm' if t <= scan_end else 'beam off, cooling'
        top.set_title(f't = {t * 1000:.1f} ms · {state}', color=INK, fontsize=9.5, loc='left')
        figure.text(0.5, 0.005, 'solid line 1290 degC (NIST threshold) · dashed 1620 K (model liquidus) · '
                    'IN625, 179.2 W, 800 mm/s, 20 um cells', ha='center', color=MUTED, fontsize=7.5)
        cax = figure.add_axes((0.885, 0.25, 0.015, 0.55))
        bar = figure.colorbar(image, cax=cax)
        bar.set_label('T (K)', color=MUTED, fontsize=8, labelpad=2)
        bar.ax.tick_params(colors=MUTED, labelsize=7)
        figure.subplots_adjust(left=0.11, right=0.86, top=0.92, bottom=0.12, hspace=0.3)
        figure.canvas.draw()
        frames.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
        plt.close(figure)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=160, loop=0, optimize=True, disposal=2)
    receipt(path, {Path(smoke20).name: sha(smoke20), 'T fields (concatenated)': digest.hexdigest()},
            frames=len(frames), frame_ms=160, field_times_s=[float(d.name) for d in times])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--validation', type=Path, help='render only the A/B/C validation figure')
    for name in ('smoke20', 'smoke10', 'sweep', 'case'):
        parser.add_argument(f'--{name}', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.validation:
        validation(args.validation, args.out)
        return
    length_check(args.smoke20, args.smoke10, args.out)
    process_map(args.sweep, args.out)
    melt_pool_gif(args.case, args.smoke20, args.out)


if __name__ == '__main__':
    main()
