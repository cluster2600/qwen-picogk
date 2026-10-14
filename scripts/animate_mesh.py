"""Create a turntable GIF from an existing native STL, preserving its geometry."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, __version__ as pillow_version

from render_gallery import triangles, panel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    receipt_path = args.output.with_suffix('.json')
    if args.output.exists() or receipt_path.exists():
        parser.error('Use new GIF and receipt paths; never overwrite published evidence')
    mesh = triangles(args.mesh)
    span = float(np.ptp(mesh, axis=(0, 1)).max())*1.25
    figure = plt.figure(figsize=(5, 5), dpi=128, facecolor='#f6f8fa')
    axis = figure.add_subplot(111, projection='3d', facecolor='#f6f8fa')
    panel(axis, mesh, dict(recipe=args.title, language='', parameters_mm=[]), span)
    axis.set_title(args.title, fontsize=13, color='#193341', fontweight='bold')
    axis.texts[-1].set_text('Actual PicoGK STL · voxel 0.5 mm')
    figure.text(0.5, 0.045, 'Qwen output · synthetic research geometry', ha='center', color='#486270', fontsize=9)
    frames = []
    for azimuth in np.linspace(-58, 302, 24, endpoint=False):
        axis.view_init(elev=28, azim=float(azimuth))
        figure.canvas.draw()
        frames.append(Image.fromarray(np.asarray(figure.canvas.buffer_rgba())).convert('RGB'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(args.output, save_all=True, append_images=frames[1:], duration=120, loop=0,
                   optimize=True, disposal=2)
    plt.close(figure)
    with Image.open(args.output) as image:
        assert image.n_frames == 24 and image.size == (640, 640) and image.info['loop'] == 0
        hashes = []
        for i in (0, 6, 12, 18):
            image.seek(i); hashes.append(hashlib.sha256(image.convert('RGB').tobytes()).hexdigest())
        assert len(set(hashes)) >= 3
    receipt = dict(schema='qwen-picogk.turntable@1', title=args.title,
                   mesh_sha256=hashlib.sha256(args.mesh.read_bytes()).hexdigest(),
                   gif_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                   source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   mesh_renderer_sha256=hashlib.sha256(Path(__file__).with_name('render_gallery.py').read_bytes()).hexdigest(),
                   frames=24, duration_ms=120, loop=0, size_px=[640,640],
                   engine='Matplotlib actual mesh turntable; Pillow GIF encoder', pillow=pillow_version,
                   geometry_changed=False, manufacturing_qualified=False)
    receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
    print('Turntable and frame checks passed: '+str(args.output), flush=True)


if __name__ == '__main__':
    main()
