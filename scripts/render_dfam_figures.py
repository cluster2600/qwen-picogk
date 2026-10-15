"""Render the DfAM checker figures from verified outputs, with provenance receipts.

Inputs are the native output STLs of a verification run and the per-triangle
dumps written by `Checker check OUTPUT.stl FIXTURES.json VOXEL MIN_WALL DUMP`
(int32 count, then 9 vertex floats and the wall thickness per triangle).
Geometry is never edited: dense meshes are shown through a vertex-clustering
display proxy, which every receipt records. Existing figures are never
overwritten.

    python scripts/render_dfam_figures.py --dumps work/thickness \
        --fixtures work/dfam-fixtures --out docs/visuals/dfam
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from PIL import Image, __version__ as pillow_version  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BG, INK, MUTED = '#f6f8fa', '#193341', '#486270'
COS45 = np.cos(np.pi / 4)
LIGHT = np.array([0.35, -0.55, 0.76]) / np.linalg.norm([0.35, -0.55, 0.76])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dump(path):
    raw = Path(path).read_bytes()
    n = int(np.frombuffer(raw[:4], '<i4')[0])
    data = np.frombuffer(raw[4:], '<f4').reshape(n, 10)
    tris = data[:, :9].reshape(n, 3, 3).astype(np.float64)
    return tris, data[:, 9].astype(np.float64)


def outward_normals(tris):
    cross = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    signed = np.einsum('ij,ij->i', tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()
    cross *= 1 if signed >= 0 else -1
    length = np.linalg.norm(cross, axis=1)
    return cross / np.where(length > 0, length, 1)[:, None], length / 2


def proxy(tris, values, cell):
    """Vertex clustering for display: merge vertices per cell, drop collapsed faces."""
    keys = np.floor(tris.reshape(-1, 3) / cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    sums = np.zeros((inverse.max() + 1, 3))
    np.add.at(sums, inverse, tris.reshape(-1, 3))
    counts = np.bincount(inverse)[:, None]
    centres = sums / counts
    return centres[faces[keep]], values[keep]


def shaded(rgba, tris):
    normals, _ = outward_normals(tris)
    light = 0.55 + 0.45 * np.clip(normals @ LIGHT, 0, 1)
    out = rgba.copy()
    out[:, :3] *= light[:, None]
    return out


def axes3d(figure, rect, tris, zoom=1.0):
    axis = figure.add_axes(rect, projection='3d', facecolor=BG)
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    centre, span = (lo + hi) / 2, (hi - lo).max() * 0.55
    for setter, c in zip((axis.set_xlim, axis.set_ylim, axis.set_zlim), centre):
        setter(c - span, c + span)
    axis.set_box_aspect((1, 1, 1), zoom=zoom)
    axis.set_axis_off()
    return axis


def receipt(path, sources, **extra):
    record = {
        'image': path.name, 'image_sha256': sha(path),
        'sources_sha256': {k: sha(v) for k, v in sources.items()},
        'render_source_sha256': sha(__file__),
        'renderer': f'matplotlib {matplotlib.__version__}, Pillow {pillow_version}, numpy {np.__version__}',
        'native_geometry_edited_for_render': False,
        'evidence': 'evidence/dfam-code/strict-v3-20261015.json',
        'manufacturing_qualified': False, **extra}
    path.with_suffix('.json').write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')


def fresh(path):
    if path.exists() or path.with_suffix('.json').exists():
        raise SystemExit(f'{path} exists; never overwrite published figures')
    return path


def section_segments(tris, x):
    """Segments where the plane X = x cuts each triangle, as (y0, z0, y1, z1)."""
    d = tris[:, :, 0] - x
    hit = (d.min(1) < 0) & (d.max(1) > 0)
    segs, index = [], np.nonzero(hit)[0]
    for i in index:
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            da, db = d[i, a], d[i, b]
            if (da < 0) != (db < 0):
                s = da / (da - db)
                p = tris[i, a] + s * (tris[i, b] - tris[i, a])
                pts.append(p[1:])
        if len(pts) == 2:
            segs.append((*pts[0], *pts[1]))
    return np.array(segs), index


def channel_section(dumps, out):
    """Teardrop (dfam-001) versus round roof (negative control dfam-901) at x = 0."""
    path = fresh(out / 'channel-section.png')
    figure, axes = plt.subplots(1, 2, figsize=(9.6, 4.6), dpi=128, facecolor=BG)
    cases = [('dfam-901', 'Round roof (negative control)', 0.0483, 'fails'),
             ('dfam-001', 'Teardrop roof, 50 deg flanks', 0.0218, 'passes')]
    for axis, (case, title, share, verdict) in zip(axes, cases):
        tris, _ = load_dump(dumps / f'{case}.bin')
        normals, _ = outward_normals(tris)
        zmin = tris[:, :, 2].min()
        centroid_z = tris[:, :, 2].mean(1)
        overhang = (normals[:, 2] < -COS45) & (centroid_z > zmin + 0.45)
        segs, index = section_segments(tris, 0.0)
        flag = overhang[index]
        for subset, colour, width in ((~flag, '#4b6b7a', 1.4), (flag, '#d1495b', 2.6)):
            s = segs[subset]
            axis.plot(s[:, [0, 2]].T, s[:, [1, 3]].T, color=colour, lw=width, solid_capstyle='round')
        axis.set_xlim(-21, -9); axis.set_ylim(3.5, 15.5); axis.set_aspect('equal')
        axis.set_facecolor(BG); axis.grid(color='#dde3e8', lw=0.6)
        axis.set_xlabel('y (mm)', color=MUTED); axis.set_ylabel('z (mm), build direction up', color=MUTED)
        axis.set_title(title, color=INK, fontsize=11, fontweight='bold')
        axis.text(0.03, 0.04, f'part overhang share {share:.4f}\nlimit 0.035: {verdict}', transform=axis.transAxes,
                  color='#d1495b' if verdict == 'fails' else '#2a7f62', fontsize=9.5,
                  bbox=dict(facecolor='white', edgecolor='#dde3e8', boxstyle='round,pad=0.4'))
    figure.legend(handles=[plt.Line2D([], [], color='#4b6b7a', lw=1.4, label='section at x = 0'),
                           plt.Line2D([], [], color='#d1495b', lw=2.6, label='downward facing, flatter than 45 deg')],
                  loc='lower center', ncol=2, frameon=False, fontsize=9)
    figure.suptitle('Same channel, two roofs: the checker sees the difference', color=INK, fontsize=12.5)
    figure.tight_layout(rect=(0, 0.07, 1, 0.95))
    figure.savefig(path, facecolor=BG); plt.close(figure)
    receipt(path, {f'{c}.bin': dumps / f'{c}.bin' for c, *_ in cases},
            view='planar section x = 0 of the actual output meshes; facets classified by outward normal',
            overhang_rule='normal z < -cos 45 deg, above the 0.45 mm plate band, as in dfam-native/Checker')


def thickness_colours(values, lo=0.8, hi=2.4):
    norm = colors.Normalize(lo, hi, clip=True)
    return plt.get_cmap('magma')(norm(np.minimum(values, hi))), norm


def infill_thickness(dumps, out, frames=24):
    """Cut-away of the gyroid infill coloured by measured wall thickness, PNG and GIF."""
    png, gif = fresh(out / 'infill-thickness.png'), fresh(out / 'infill-thickness-turntable.gif')
    tris, thick = load_dump(dumps / 'infill-001.bin')
    keep = tris[:, :, 1].mean(1) < 0          # remove the y > 0 half; look into the cut from +y
    view, values = proxy(tris[keep], thick[keep], 0.7)
    rgba, norm = thickness_colours(values)
    rgba = shaded(rgba, view)

    def draw(azimuth, size):
        figure = plt.figure(figsize=(size, size * 0.86), dpi=128, facecolor=BG)
        axis = axes3d(figure, (0.0, 0.08, 0.86, 0.86), view, zoom=1.35)
        axis.add_collection3d(Poly3DCollection(view, facecolors=rgba, edgecolors='none', linewidths=0))
        axis.view_init(elev=24, azim=azimuth)
        bar = figure.add_axes((0.87, 0.2, 0.025, 0.6))
        figure.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='magma'), cax=bar)
        bar.axhline(1.0, color='white', lw=1.5)
        bar.set_ylabel('wall thickness (mm), min wall 1.0', color=MUTED, fontsize=8)
        bar.tick_params(labelsize=7, colors=MUTED)
        figure.text(0.43, 0.035, 'infill-001 gyroid, cut at y = 0 · ray thickness per triangle · display proxy',
                    ha='center', color=MUTED, fontsize=8)
        return figure

    figure = draw(118, 7.2)
    figure.suptitle('Measured wall thickness of the graded gyroid', color=INK, fontsize=12.5, y=0.97)
    figure.savefig(png, facecolor=BG); plt.close(figure)
    images = []
    for azimuth in np.linspace(118, 478, frames, endpoint=False):
        figure = draw(float(azimuth), 5.0)
        figure.canvas.draw()
        images.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
        plt.close(figure)
    images[0].save(gif, save_all=True, append_images=images[1:], duration=120, loop=0, optimize=True, disposal=2)
    proxy_info = {'method': 'vertex clustering for display only', 'cell_mm': 0.7, 'triangles': int(len(view)),
                  'source_triangles_shown': int(keep.sum()), 'cut': 'triangles with centroid y < 0'}
    for path in (png, gif):
        receipt(path, {'infill-001.bin': dumps / 'infill-001.bin'}, display_proxy=proxy_info,
                note='infill-001 fails strict-v3 on mesh defects; its thickness field is shown, not endorsed',
                **({'frames': frames, 'frame_ms': 120} if path == gif else {}))


def fold_closeup(dumps, out, centre=(15.585, -4.82, 28.5), radius=1.2):
    """The detached zero-volume sheet that libigl reports in infill-001: two quads
    back to back on the same four vertices. Every edge is used twice and it has no
    volume, so the edge and voxel checks cannot see it."""
    path = fresh(out / 'selfintersection-fold.png')
    tris, _ = load_dump(dumps / 'infill-001.bin')
    near = np.linalg.norm(tris.mean(1) - np.array(centre), axis=1) < radius
    local = tris[near]
    normals, _ = outward_normals(local)
    keys = [tuple(np.round(v / 1e-4).astype(np.int64)) for v in local.reshape(-1, 3)]
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    faces = np.array([ids[k] for k in keys]).reshape(-1, 3)
    edges = {}
    for f, (a, b, c) in enumerate(faces):
        for e in ((a, b), (b, c), (c, a)):
            edges.setdefault(tuple(sorted(e)), []).append(f)
    fold = np.zeros(len(local), bool)
    for members in edges.values():
        for i in members:
            for j in members:
                if i < j and normals[i] @ normals[j] < -0.999:
                    fold[[i, j]] = True
    figure = plt.figure(figsize=(6.4, 5.4), dpi=128, facecolor=BG)
    axis = axes3d(figure, (0, 0.1, 1, 0.82), local, zoom=1.2)
    base = shaded(np.tile(colors.to_rgba('#c9d6de'), (len(local), 1)), local)
    base[:, 3] = 0.45
    base[fold] = colors.to_rgba('#d1495b')
    axis.add_collection3d(Poly3DCollection(local, facecolors=base, edgecolors='#5b7380', linewidths=0.25))
    axis.view_init(elev=38, azim=-50)
    figure.suptitle('A detached zero-volume sheet in infill-001', color=INK, fontsize=12.5)
    figure.text(0.5, 0.025, f'red: {int(fold.sum())} triangles, two 0.10 x 0.09 mm quads back to back '
                f'on the same 4 vertices, at z = {centre[2]} mm.\nEvery edge is used twice and it has no volume, '
                'so the edge and voxel checks pass;\nthe exact self-intersection check fails it.',
                ha='center', color=MUTED, fontsize=8.5, linespacing=1.4)
    figure.savefig(path, facecolor=BG); plt.close(figure)
    receipt(path, {'infill-001.bin': dumps / 'infill-001.bin'}, highlighted_triangles=int(fold.sum()),
            window={'centre_mm': list(centre), 'radius_mm': radius},
            detector='libigl find_self_intersections reports 4 coplanar pairs; highlighted here by opposite normals across a shared edge')


def scan_reconstruction(dumps, fixtures, out, frames=24):
    """Raw synthetic scan beside the scan-001 reconstruction, PNG and turntable GIF."""
    png, gif = fresh(out / 'scan-001-reconstruction.png'), fresh(out / 'scan-001.gif')
    points = np.loadtxt(fixtures / 'scan.xyz', comments='#')
    meta = json.loads((fixtures / 'fixtures.json').read_text())
    tris, _ = load_dump(dumps / 'scan-001.bin')
    view, _ = proxy(tris, np.zeros(len(tris)), 0.9)
    face = shaded(np.tile(colors.to_rgba('#7fa7b8'), (len(view), 1)), view)
    rng = np.random.default_rng(1)
    sample = points[rng.choice(len(points), 25000, replace=False)]

    figure = plt.figure(figsize=(10, 5.0), dpi=128, facecolor=BG)
    left = axes3d(figure, (0.0, 0.12, 0.5, 0.78), view, zoom=1.3)
    left.scatter(*sample.T, s=0.4, c='#486270', alpha=0.5, depthshade=False)
    for c in meta['gap_centres']:
        left.scatter(*c, s=160, facecolors='none', edgecolors='#d1495b', linewidths=1.4, depthshade=False)
    left.view_init(elev=26, azim=-58)
    figure.text(0.25, 0.05, f"raw .xyz: {meta['scan_points']:,} points incl. {meta['scan_outliers']} outliers,\n"
                f"3 scanner gaps (red circles), noise sigma {meta['scan_noise_sigma_mm']} mm",
                ha='center', color=MUTED, fontsize=9)
    right = axes3d(figure, (0.5, 0.12, 0.5, 0.78), view, zoom=1.3)
    right.add_collection3d(Poly3DCollection(view, facecolors=face, edgecolors='none'))
    right.view_init(elev=26, azim=-58)
    figure.text(0.75, 0.05, 'scan-001 output: one closed solid, no enclosed voids,\n'
                '0 self-intersections (display proxy of the verified STL)', ha='center', color=MUTED, fontsize=9)
    figure.suptitle('Unoriented point cloud to closed solid by splatting and closing', color=INK, fontsize=12.5)
    figure.savefig(png, facecolor=BG); plt.close(figure)

    images = []
    for azimuth in np.linspace(-58, 302, frames, endpoint=False):
        figure = plt.figure(figsize=(5, 5), dpi=128, facecolor=BG)
        axis = axes3d(figure, (0, 0.06, 1, 0.86), view, zoom=1.3)
        axis.add_collection3d(Poly3DCollection(view, facecolors=face, edgecolors='none'))
        axis.view_init(elev=26, azim=float(azimuth))
        figure.suptitle('scan-001 · PicoGK output', color=INK, fontsize=12, fontweight='bold')
        figure.text(0.5, 0.04, 'Actual verified STL · display proxy · synthetic fixture', ha='center',
                    color=MUTED, fontsize=8.5)
        figure.canvas.draw()
        images.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
        plt.close(figure)
    images[0].save(gif, save_all=True, append_images=images[1:], duration=120, loop=0, optimize=True, disposal=2)
    proxy_info = {'method': 'vertex clustering for display only', 'cell_mm': 0.9, 'triangles': int(len(view))}
    for path in (png, gif):
        receipt(path, {'scan-001.bin': dumps / 'scan-001.bin', 'scan.xyz': fixtures / 'scan.xyz'},
                display_proxy=proxy_info, points_plotted=25000 if path == png else 0,
                **({'frames': frames, 'frame_ms': 120} if path == gif else {}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dumps', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    channel_section(args.dumps, args.out)
    fold_closeup(args.dumps, args.out)
    scan_reconstruction(args.dumps, args.fixtures, args.out)
    infill_thickness(args.dumps, args.out)


if __name__ == '__main__':
    main()
