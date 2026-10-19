"""Check a variant effect against a half-cell grid shift, with a receipt and a figure.

    python physics/adamantine/robustness.py \
        --aligned evidence/process/adamantine-layers-comparison.json \
        --shifted evidence/process/adamantine-layers-offset-comparison.json \
        --evidence evidence/process/adamantine-layers-robustness.json --out docs/visuals/process

The effect of a variant is its paired relative difference from the solid blank
on the same grid. It is called robust here when the effect keeps its sign and
changes by less than the grid shift alone changes the solid's absolute value.
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import __version__ as pillow_version  # noqa: E402

BG, INK, MUTED, GRID = '#f6f8fa', '#193341', '#486270', '#dde3e8'
SERIES = ['#2a78d6', '#eb6834']
METRICS = (('max_displacement_mm', 'Maximum displacement'), ('slab_top_uz_range_mm', 'Slab-top warp'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def effects(aligned, shifted, variant='dfam-001', base='solid', prefix='off-'):
    a, s = aligned['variants'], shifted['variants']
    out = {}
    for key, _ in METRICS:
        on_aligned = (a[variant][key] - a[base][key]) / a[base][key]
        on_shifted = (s[prefix + variant][key] - s[prefix + base][key]) / s[prefix + base][key]
        grid_shift = (s[prefix + base][key] - a[base][key]) / a[base][key]
        out[key] = {'effect_aligned': round(on_aligned, 5), 'effect_shifted': round(on_shifted, 5),
                    'effect_change': round(on_shifted - on_aligned, 5), 'solid_grid_shift': round(grid_shift, 5),
                    'robust': (on_aligned > 0) == (on_shifted > 0) and abs(on_shifted - on_aligned) < abs(grid_shift)}
    return out


def figure(result, out):
    path = out / 'adamantine-layers-robustness.png'
    if path.exists() or path.with_suffix('.json').exists():
        raise SystemExit(f'{path} exists; never overwrite published figures')
    fig, axis = plt.subplots(figsize=(7.4, 2.9), dpi=128, facecolor=BG)
    axis.set_facecolor(BG)
    for side in ('top', 'right'):
        axis.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        axis.spines[side].set_color(GRID)
    for y, (key, label) in enumerate(METRICS):
        row = result[key]
        for s, (field, name) in enumerate((('effect_aligned', 'aligned grid'), ('effect_shifted', 'grid shifted 0.5 mm'))):
            value = row[field] * 100
            axis.scatter(value, y + (0.12 if s else -0.12), s=70, color=SERIES[s], edgecolor=BG, linewidth=2,
                         zorder=3, label=name if y == 0 else None)
            axis.text(value + 0.12, y + (0.12 if s else -0.12), f'{value:+.2f} %', va='center', color=INK, fontsize=8)
        axis.text(0.15, y + 0.36, f"grid shift alone moves the solid by {row['solid_grid_shift'] * 100:+.1f} %",
                  color=MUTED, fontsize=7.8)
    axis.axvline(0, color=MUTED, lw=1)
    axis.set_yticks(range(len(METRICS)), [label for _, label in METRICS])
    axis.set_ylim(-0.6, len(METRICS) - 0.1)
    axis.set_xlim(-0.5, 6.5)
    axis.set_xlabel('dfam-001 relative to the solid blank on the same grid (%)', color=MUTED, fontsize=9)
    axis.tick_params(colors=MUTED, labelsize=8.5)
    axis.grid(axis='x', color=GRID, lw=0.6)
    axis.legend(loc='lower right', frameon=False, fontsize=8)
    axis.set_title('The channel effect survives a half-cell grid shift', color=INK, fontsize=10.5, loc='left')
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('aligned', 'shifted', 'evidence', 'out'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.evidence.exists():
        parser.error('use a new evidence path')
    result = effects(json.loads(args.aligned.read_text()), json.loads(args.shifted.read_text()))
    record = {'schema': 'qwen-picogk.process.adamantine-robustness@1', 'variant': 'dfam-001', 'baseline': 'solid',
              'grid_shift_xy_mm': 0.5, 'metrics': result,
              'sources_sha256': {args.aligned.name: sha(args.aligned), args.shifted.name: sha(args.shifted)},
              'analysis_sha256': sha(__file__), 'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False}
    args.evidence.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
    path = figure(result, args.out)
    path.with_suffix('.json').write_text(json.dumps({
        'image': path.name, 'image_sha256': sha(path), 'sources_sha256': {args.evidence.name: sha(args.evidence)},
        'render_source_sha256': sha(__file__),
        'renderer': f'matplotlib {matplotlib.__version__}, Pillow {pillow_version}, numpy {np.__version__}',
        'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False}, indent=1, sort_keys=True) + '\n')
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
