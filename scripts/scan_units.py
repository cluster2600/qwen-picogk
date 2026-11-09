"""Explicit source-unit normalization for scan intake; standard library only.

OBJ files carry no unit. Every scale therefore has exactly one recorded basis:

  declared_unit        A person declared the source unit. The factor is that
                       unit's defined length in millimetres, so the conversion
                       itself is checked (tests/test_scan_units.py).
  supplied_assumption  A person authorised a demonstration hypothesis. It is not
                       a conversion and nothing checks it.
  unknown              Neither. The result stays unknown; no millimetre geometry
                       is written and no demonstration default is adopted.

No basis verifies the physical size of the scanned object.
"""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_mesh import digest, fresh, save

MM_PER_UNIT = {'mm': 1., 'cm': 10., 'm': 1000., 'in': 25.4}
# Assumptions stay inside the registered demonstration course (scan_policy.expected).
ASSUMPTION_RANGE_MM = (.1, 2.)


def resolve_scale(unit=None, assumed_mm_per_unit=None):
    if unit is not None and assumed_mm_per_unit is not None:
        raise ValueError('Declare a unit or supply an assumption, not both')
    if unit is not None:
        if unit not in MM_PER_UNIT:
            raise ValueError('Unsupported declared unit')
        return dict(status='scale_resolved', basis='declared_unit', declared_unit=unit,
                    mm_per_source_unit=MM_PER_UNIT[unit], conversion_verified=True,
                    physical_scale_verified=False)
    if assumed_mm_per_unit is not None:
        v = assumed_mm_per_unit
        low, high = ASSUMPTION_RANGE_MM
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('A supplied assumption must be finite and inside the demo course')
        return dict(status='scale_resolved', basis='supplied_assumption', declared_unit=None,
                    mm_per_source_unit=float(v), conversion_verified=False,
                    physical_scale_verified=False)
    return dict(status='unknown_scale', basis='unknown', declared_unit=None,
                mm_per_source_unit=None, conversion_verified=False, physical_scale_verified=False)


def rewrite_obj(source, factor=None, target=None):
    """Return source-unit bounds; check, and with a target write, positions multiplied once by factor.

    Every other record is copied verbatim, so faces and indices stay identical and
    the unchanged intake contract (scan_mesh.read_obj) still applies downstream.
    """
    if Path(source).stat().st_size > 256*1024**2:
        raise ValueError('Demo input exceeds 256 MiB')
    low, high = [math.inf]*3, [-math.inf]*3
    out = Path(target).open('x') if target is not None else None
    try:
        with Path(source).open() as stream:
            for line in stream:
                f = line.split()
                if not f or f[0] != 'v':
                    if out:
                        out.write(line)
                    continue
                if len(f) != 4:
                    raise ValueError('Position-only vertices required')
                xyz = [float(x) for x in f[1:]]
                if not all(map(math.isfinite, xyz)):
                    raise ValueError('Finite vertices required')
                low, high = [min(a, b) for a, b in zip(low, xyz)], [max(a, b) for a, b in zip(high, xyz)]
                if factor is not None:
                    scaled = [x*factor for x in xyz]
                    if not all(map(math.isfinite, scaled)):
                        raise ValueError('Scaled vertices overflow')
                    if out:
                        out.write('v %r %r %r\n' % tuple(scaled))
    finally:
        if out:
            out.close()
    if low[0] == math.inf:
        raise ValueError('No vertices')
    return [low, high]


def normalize(source, output, unit=None, assumed_mm_per_unit=None):
    scale = resolve_scale(unit, assumed_mm_per_unit)
    sha = digest(source)
    bounds = rewrite_obj(source, scale['mm_per_source_unit'])  # validate before creating any output
    output = fresh(output)
    receipt = dict(source_sha256=sha, scale=scale, bounds_source_units=bounds, manufacturing_qualified=False)
    if scale['status'] == 'scale_resolved':
        rewrite_obj(source, scale['mm_per_source_unit'], output/'normalized.obj')
        receipt.update(coordinates_unit='mm', normalized_obj_sha256=digest(output/'normalized.obj'),
                       downstream_mm_per_unit=1.)
    else:
        receipt.update(coordinates_unit=None, normalized_obj_sha256=None, downstream_mm_per_unit=None)
    if digest(source) != sha:
        raise ValueError('Source changed during normalization')
    save(output/'scale.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    basis = parser.add_mutually_exclusive_group()
    basis.add_argument('--unit', choices=sorted(MM_PER_UNIT), help='Declared source unit')
    basis.add_argument('--assume-mm-per-unit', type=float, help='Authorised demonstration hypothesis')
    parser.add_argument('obj', type=Path)
    parser.add_argument('output', type=Path, help='New private directory')
    args = parser.parse_args()
    result = normalize(args.obj, args.output, args.unit, args.assume_mm_per_unit)
    print(json.dumps(result, allow_nan=False))
    raise SystemExit(0 if result['scale']['status'] == 'scale_resolved' else 3)
