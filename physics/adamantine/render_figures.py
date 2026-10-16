"""Render the Phase 3 adamantine figures from pipeline runs, with receipts.

    python physics/adamantine/render_figures.py \
        --coarse evidence/process/adamantine-pipeline-dfam-001-1.0mm.json \
        --fine evidence/process/adamantine-pipeline-dfam-001-0.5mm.json \
        --case work/adamantine/pipe-dfam001-0.5-TAG --out docs/visuals/process

Reads the deal.II VTU outputs of the fine run (zlib-compressed base64 arrays,
one vertex set per hexahedron). Existing figures are never overwritten.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, __version__ as pillow_version  # noqa: E402

BG, INK, MUTED, GRID = '#f6f8fa', '#193341', '#486270', '#dde3e8'
SERIES = ['#2a78d6', '#eb6834']          # validated categorical slots 1-2 on BG


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


def decode(encoded):
    blocks = int(np.frombuffer(base64.b64decode(encoded[:8])[:4], '<u4')[0])
    header_chars = 4 * -(-(4 * (3 + blocks)) // 3)
    header = np.frombuffer(base64.b64decode(encoded[:header_chars])[:4 * (3 + blocks)], '<u4')
    payload, offset, parts = base64.b64decode(encoded[header_chars:]), 0, []
    import zlib
    for size in header[3:]:
        parts.append(zlib.decompress(payload[offset:offset + int(size)]))
        offset += int(size)
    return np.frombuffer(b''.join(parts), '<f4')


def read_vtu(path):
    text = Path(path).read_text()
    points = re.search(r'<Points>\s*<DataArray type="Float32" NumberOfComponents="3" format="binary">\s*'
                       r'([A-Za-z0-9+/=]+)', text).group(1)
    temp = re.search(r'Name="temperature" format="binary">\s*([A-Za-z0-9+/=]+)', text).group(1)
    time = float(re.search(r'Name="TIME"[^>]*>\s*([0-9.eE+-]+)', text).group(1))
    # adamantine writes SI coordinates even when the mesh was read in millimetres.
    return decode(points).reshape(-1, 3) * 1000.0, decode(temp), time


def style(axis):
    axis.set_facecolor(BG)
    for side in ('top', 'right'):
        axis.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=MUTED, labelsize=8.5)


def energy_convergence(coarse, fine, out):
    path = fresh(out / 'adamantine-energy-convergence.png')
    runs = [json.loads(Path(p).read_text()) for p in (coarse, fine)]
    figure, axis = plt.subplots(figsize=(6.4, 3.0), dpi=128, facecolor=BG)
    style(axis)
    axis.axvspan(0.95, 1.05, color='#e4e9ed', zorder=0, label='acceptance +/- 5 %')
    axis.axvline(1.0, color=MUTED, lw=1)
    for y, run in enumerate(runs):
        ratio = run['energy_ratio']
        axis.scatter(ratio, y, s=70, color=SERIES[0], edgecolor=BG, linewidth=2, zorder=3)
        axis.text(ratio + 0.006, y, f"{ratio:.3f}  ({run['mesh']['hexahedra']:,} hexahedra, "
                  f"{run['solver_seconds']:.0f} s)", va='center', color=INK, fontsize=8.5)
    axis.set_yticks([0, 1], [f"{r['mesh']['cell_mm']} mm cells" for r in runs])
    axis.set_ylim(-0.6, 1.6)
    axis.set_xlim(0.94, 1.32)
    axis.set_xlabel('deposited heat / (absorption x power x scan time)', color=MUTED, fontsize=9)
    axis.legend(loc='upper right', frameon=False, fontsize=8)
    axis.set_title('dfam-001 laser line: the heat balance closes only at 0.5 mm cells', color=INK, fontsize=10.5,
                   loc='left')
    figure.tight_layout()
    figure.savefig(path, facecolor=BG)
    plt.close(figure)
    receipt(path, {Path(coarse).name: sha(coarse), Path(fine).name: sha(fine)})


def load_run(case):
    files = sorted(Path(case).glob('output.*.0.vtu'), key=lambda p: int(p.name.split('.')[1]))
    frames = [read_vtu(f) for f in files]
    return files, frames


def raster(u, v, values, extent, cell=0.5):
    """Maximum per pixel on the mesh-resolution grid; pixels with no material stay empty."""
    u0, u1, v0, v1 = extent
    nu, nv = int(round((u1 - u0) / cell)), int(round((v1 - v0) / cell))
    iu = np.clip(((u - u0) / cell).astype(int), 0, nu - 1)
    iv = np.clip(((v - v0) / cell).astype(int), 0, nv - 1)
    grid = np.full((nv, nu), np.nan)
    np.fmax.at(grid, (iv, iu), values)
    return grid


TOP = (-36.0, 36.0, -23.0, 23.0)          # x, y extent of the slab top (mm)
SECTION = (-24.0, -6.0, 0.0, 17.0)        # y, z extent of the section through the channel (mm)


def top_layer(points):
    return np.abs(points[:, 2] - 16.0) < 0.26


def peak_map(case, fine, out, files, frames):
    """Peak temperature over time: top surface of the slab and the section at x = 0."""
    path = fresh(out / 'adamantine-dfam-001-peak.png')
    points = frames[0][0]
    peak = np.max(np.stack([t for _, t, _ in frames]), axis=0)
    run = json.loads(Path(fine).read_text())
    (a, b) = run['scan_line_mm']
    top, section = top_layer(points), np.abs(points[:, 0]) < 0.26
    figure, (left, right) = plt.subplots(1, 2, figsize=(10.2, 4.0), dpi=128, facecolor=BG,
                                         gridspec_kw={'width_ratios': [1.55, 1]})
    image = left.imshow(raster(points[top, 0], points[top, 1], peak[top], TOP), origin='lower', extent=TOP,
                        cmap='magma', vmin=300, vmax=400, interpolation='nearest')
    left.plot([a[0], b[0]], [a[1] - 2.2, b[1] - 2.2], color=SERIES[0], lw=1.2)
    left.text(a[0], a[1] - 4.2, 'laser line, 400 W, 500 mm/s', color=SERIES[0], fontsize=8)
    left.set_title('Peak temperature on the slab top (z = 16 mm)', color=INK, fontsize=10, loc='left')
    right.imshow(raster(points[section, 1], points[section, 2], peak[section], SECTION), origin='lower',
                 extent=SECTION, cmap='magma', vmin=300, vmax=400, interpolation='nearest')
    right.set_title('Section x = 0 through the channel', color=INK, fontsize=10, loc='left')
    for axis, (xl, yl) in ((left, ('x (mm)', 'y (mm)')), (right, ('y (mm)', 'z (mm)'))):
        axis.set_facecolor(BG)
        axis.tick_params(colors=MUTED, labelsize=8)
        axis.set_xlabel(xl, color=MUTED, fontsize=8.5)
        axis.set_ylabel(yl, color=MUTED, fontsize=8.5)
        for side in axis.spines.values():
            side.set_color(GRID)
    bar = figure.colorbar(image, ax=[left, right], fraction=0.025, pad=0.02)
    bar.set_label('peak temperature (K)', color=MUTED, fontsize=8.5)
    bar.ax.tick_params(colors=MUTED, labelsize=7.5)
    figure.text(0.01, 0.01, 'adamantine 1.1, thermal only, 400 W x 0.3 absorbed, 500 mm/s, Goldak 2 mm x 0.5 mm, '
                '0.5 mm hexahedra from the verified STL; pipeline check, not a calibrated prediction',
                color=MUTED, fontsize=7.5)
    figure.savefig(path, facecolor=BG, bbox_inches='tight')
    plt.close(figure)
    receipt(path, {Path(fine).name: sha(fine), 'vtu (concatenated)': hashlib.sha256(
        b''.join(sha(f).encode() for f in files)).hexdigest()}, outputs=len(files), raster_cell_mm=0.5)


def heat_gif(case, fine, out, files, frames):
    path = fresh(out / 'adamantine-dfam-001-heat.gif')
    points = frames[0][0]
    top = top_layer(points)
    images = []
    for _, temp, time in frames:
        figure, axis = plt.subplots(figsize=(7.0, 4.0), dpi=100, facecolor=BG)
        axis.set_facecolor(BG)
        image = axis.imshow(raster(points[top, 0], points[top, 1], temp[top], TOP), origin='lower', extent=TOP,
                            cmap='magma', vmin=300, vmax=400, interpolation='nearest')
        axis.tick_params(colors=MUTED, labelsize=7.5)
        for side in axis.spines.values():
            side.set_color(GRID)
        axis.set_xlabel('x (mm)', color=MUTED, fontsize=8)
        axis.set_ylabel('y (mm)', color=MUTED, fontsize=8)
        axis.set_title(f'dfam-001 slab top, t = {time * 1000:.0f} ms (laser along y = -15 mm)', color=INK,
                       fontsize=10, loc='left')
        bar = figure.colorbar(image, ax=axis, fraction=0.03, pad=0.02)
        bar.set_label('T (K)', color=MUTED, fontsize=8)
        bar.ax.tick_params(colors=MUTED, labelsize=7)
        figure.tight_layout()
        figure.canvas.draw()
        images.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
        plt.close(figure)
    images[0].save(path, save_all=True, append_images=images[1:], duration=140, loop=0, optimize=True, disposal=2)
    receipt(path, {Path(fine).name: sha(fine), 'vtu (concatenated)': hashlib.sha256(
        b''.join(sha(f).encode() for f in files)).hexdigest()}, frames=len(images), frame_ms=140, raster_cell_mm=0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('coarse', 'fine', 'case', 'out'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    energy_convergence(args.coarse, args.fine, args.out)
    files, frames = load_run(args.case)
    peak_map(args.case, args.fine, args.out, files, frames)
    heat_gif(args.case, args.fine, args.out, files, frames)


if __name__ == '__main__':
    main()
