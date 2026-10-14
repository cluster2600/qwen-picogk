"""Render actual binary STL triangles with Matplotlib; geometry is never invented."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np


def triangles(path):
    data = path.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    if count == 0 or len(data) != 84+50*count:
        raise ValueError('Expected a nonempty binary STL with exact triangle records')
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
    vertices = np.frombuffer(data, dtype=dtype, offset=84, count=count)['vertices'].astype(float)
    if not np.isfinite(vertices).all():
        raise ValueError('Nonfinite STL vertices')
    return vertices


def panel(axis, vertices, record, span):
    centre = (vertices.min(axis=(0, 1))+vertices.max(axis=(0, 1)))/2
    points = vertices-centre
    normals = np.cross(points[:, 1]-points[:, 0], points[:, 2]-points[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals/np.maximum(lengths[:, None], 1e-12)
    light = np.array([-0.5, -0.5, 1.0]); light /= np.linalg.norm(light)
    intensity = 0.48+0.52*np.clip(normals@light, 0, 1)
    colors = np.clip(np.array([0.23, 0.49, 0.66])[None, :]*intensity[:, None]+0.09, 0, 1)
    axis.add_collection3d(Poly3DCollection(points, facecolors=colors, edgecolors='none', linewidths=0))
    axis.set(xlim=(-span/2, span/2), ylim=(-span/2, span/2), zlim=(-span/2, span/2))
    axis.set_box_aspect((1, 1, 1))
    axis.set_proj_type('ortho')
    axis.view_init(elev=28, azim=-58)
    axis.set_axis_off()
    axis.set_title(record['recipe'].upper()+'  /  '+record['language'].upper(), fontsize=15,
                   color='#193341', fontweight='bold', pad=0)
    parameters = ', '.join(format(v, 'g') for v in record['parameters_mm'])
    axis.text2D(0.5, 0.02, '['+parameters+'] mm', transform=axis.transAxes,
                ha='center', color='#486270', fontsize=11)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gallery', type=Path)
    args = parser.parse_args()
    manifest = args.gallery/'gallery.json'
    receipt = json.loads(manifest.read_text())
    records = receipt['records']
    meshes = [triangles(args.gallery/record['recipe']/'raw.stl') for record in records]
    span = max(float(np.ptp(mesh, axis=(0, 1)).max()) for mesh in meshes)*1.20
    for record, mesh in zip(records, meshes):
        figure = plt.figure(figsize=(7, 7), facecolor='#f6f8fa')
        axis = figure.add_subplot(111, projection='3d', facecolor='#f6f8fa')
        panel(axis, mesh, record, span)
        figure.text(0.5, 0.045, 'Qwen MLX plan → PicoGK STL · synthetic · voxel 0.5 mm',
                    ha='center', color='#486270', fontsize=10)
        path = args.gallery/record['recipe']/'render.png'
        figure.savefig(path, dpi=180, facecolor=figure.get_facecolor())
        plt.close(figure)
        record['files_sha256'][str(path.relative_to(args.gallery))] = hashlib.sha256(path.read_bytes()).hexdigest()
    figure = plt.figure(figsize=(15, 10), facecolor='#f6f8fa')
    for i, (record, mesh) in enumerate(zip(records, meshes), 1):
        axis = figure.add_subplot(2, 3, i, projection='3d', facecolor='#f6f8fa')
        panel(axis, mesh, record, span)
    figure.text(0.73, 0.28, 'REAL MODEL OUTPUT\n\nPinned Qwen adapter\nRaw multilingual requests\nIndependent parameter checks\nNative PicoGK meshes\n\nFive exposed demonstrations',
                fontsize=13, color='#193341', linespacing=1.6)
    figure.suptitle('QWEN → PICOGK  |  FIVE TRACEABLE GEOMETRIES', y=0.98,
                     fontsize=22, fontweight='bold', color='#193341')
    figure.text(0.5, 0.015, 'Same orthographic scale · ordered parameters in mm · voxel 0.5 mm · research only',
                ha='center', color='#486270', fontsize=11)
    path = args.gallery/'overview.png'
    figure.savefig(path, dpi=160, facecolor=figure.get_facecolor())
    plt.close(figure)
    receipt['overview_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt['rendering'] = dict(engine='Matplotlib triangle mesh rendering, not a PicoGK viewer screenshot',
                                matplotlib=matplotlib.__version__, numpy=np.__version__,
                                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                shared_orthographic_span_mm=span, smoothing_or_geometry_editing=False)
    manifest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print('Rendered five actual PicoGK meshes and a shared-scale overview')


if __name__ == '__main__':
    main()
