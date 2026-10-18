"""Compare a variant's effect across meshes and build schedules, with a receipt and a figure.

    python physics/adamantine/schedule_effect.py \
        --config "1 mm, compressed=evidence/process/adamantine-layers-comparison.json:" \
        --config "2 mm, compressed=evidence/process/adamantine-layers-2mm-compressed.json:c2comp-" \
        --config "2 mm, cooled=evidence/process/adamantine-layers-2mm-cooled.json:c2cool-" \
        --evidence evidence/process/adamantine-layers-schedule.json --out docs/visuals/process

Each config is LABEL=COMPARISON_JSON:NAME_PREFIX. The effect is the paired
relative difference of `dfam-001` from `solid` within one comparison.
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
SERIES = ['#2a78d6', '#eb6834', '#1baf7a']          # validated categorical slots 1-3
METRICS = (('max_displacement_mm', 'Maximum displacement'), ('slab_top_uz_range_mm', 'Slab-top warp'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def effect(comparison, prefix, variant='dfam-001', base='solid'):
    rows = comparison['variants']
    a, b = rows[prefix + base], rows[prefix + variant]
    out = {'solid_final_mean_temperature_k': a['final_temperature_active']['mean'],
           'final_time_s': a['final_time_s']}
    for key, _ in METRICS:
        out[key] = {'solid': a[key], 'variant': b[key], 'effect': round((b[key] - a[key]) / a[key], 5)}
    return out


def figure(result, out):
    path = out / 'adamantine-layers-schedule.png'
    if path.exists() or path.with_suffix('.json').exists():
        raise SystemExit(f'{path} exists; never overwrite published figures')
    labels = list(result)
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.2), dpi=128, facecolor=BG, sharey=True)
    for axis, (key, title) in zip(axes, METRICS):
        axis.set_facecolor(BG)
        for side in ('top', 'right'):
            axis.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            axis.spines[side].set_color(GRID)
        for y, label in enumerate(labels):
            value = result[label][key]['effect'] * 100
            axis.scatter(value, y, s=70, color=SERIES[y % len(SERIES)], edgecolor=BG, linewidth=2, zorder=3)
            axis.text(value, y + 0.25, f'{value:+.1f} %', ha='center', color=INK, fontsize=8)
        axis.axvline(0, color=MUTED, lw=1)
        axis.grid(axis='x', color=GRID, lw=0.6)
        axis.tick_params(colors=MUTED, labelsize=8.5)
        axis.set_title(f'{title}: dfam-001 vs solid', color=INK, fontsize=10, loc='left')
        values = [result[l][key]['effect'] * 100 for l in labels]
        span = max(abs(v) for v in values) + 2
        axis.set_xlim(min(-1, min(values) - 2), span)
    axes[0].set_yticks(range(len(labels)),
                       [f"{l}\n(solid ends at {result[l]['solid_final_mean_temperature_k']:.0f} K)" for l in labels])
    axes[0].set_ylim(-0.6, len(labels) - 0.3)
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', action='append', required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.evidence.exists():
        parser.error('use a new evidence path')
    result, sources = {}, {}
    for item in args.config:
        label, rest = item.split('=', 1)
        path, prefix = rest.rsplit(':', 1)
        result[label] = effect(json.loads(Path(path).read_text()), prefix)
        sources[Path(path).name] = sha(path)
    record = {'schema': 'qwen-picogk.process.adamantine-schedule@1', 'variant': 'dfam-001', 'baseline': 'solid',
              'configs': result, 'sources_sha256': sources, 'analysis_sha256': sha(__file__),
              'uncalibrated_for_any_machine': True, 'manufacturing_qualified': False}
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
