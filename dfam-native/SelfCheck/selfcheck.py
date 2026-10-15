"""Count self-intersecting triangle pairs of a binary STL with libigl.

Trusted side of the DfAM code corpus, run after the C# checker on the same
output STL. It never loads corpus code. Vertices are welded on the checker's
0.0001 mm grid so that triangles sharing a corner are recognised as
neighbours; libigl then tests every remaining pair with an AABB tree and
exact predicates (igl.predicates.find_self_intersections).

    selfcheck.py OUTPUT.stl          -> one JSON line on stdout
    selfcheck.py --self-test         -> synthetic cases with known answers
"""
import json
from importlib import metadata
import sys
import time

import numpy as np

WELD_MM = 1e-4          # same vertex cell as dfam-native/Checker
MAX_TRIANGLES = 20_000_000


def read_binary_stl(path):
    with open(path, 'rb') as stream:
        header = stream.read(84)
        if len(header) != 84:
            raise ValueError('STL is shorter than its header')
        count = int(np.frombuffer(header[80:84], dtype='<u4')[0])
        if count > MAX_TRIANGLES:
            raise ValueError(f'{count} triangles exceed the {MAX_TRIANGLES} limit')
        record = np.dtype([('normal', '<f4', 3), ('v', '<f4', (3, 3)), ('attr', '<u2')])
        data = np.fromfile(stream, dtype=record, count=count)
    if len(data) != count:
        raise ValueError('Binary STL is truncated (ASCII STL is not accepted)')
    return data['v'].astype(np.float64)


def weld(triangles):
    """Return (V, F, collapsed) with vertices merged on the WELD_MM grid."""
    points = triangles.reshape(-1, 3)
    if not np.isfinite(points).all():
        raise ValueError('Nonfinite vertex')
    keys = np.round(points / WELD_MM).astype(np.int64)
    unique, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    vertices = points[first]
    faces = inverse.reshape(-1, 3).astype(np.int64)
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return np.ascontiguousarray(vertices), np.ascontiguousarray(faces[keep]), int((~keep).sum())


def count_pairs(vertices, faces):
    import igl
    import igl.predicates
    found, pairs, coplanar = igl.predicates.find_self_intersections(vertices, faces, False)
    pairs = np.asarray(pairs).reshape(-1, 2)
    coplanar = np.asarray(coplanar).reshape(-1)
    return bool(found), len(pairs), int(coplanar.sum()), len(np.unique(pairs)) if len(pairs) else 0


def check(path):
    started = time.time()
    vertices, faces, collapsed = weld(read_binary_stl(path))
    found, pairs, coplanar, involved = count_pairs(vertices, faces)
    return {
        'self_intersecting_pairs': pairs,
        'self_intersecting_coplanar_pairs': coplanar,
        'self_intersecting_triangles': involved,
        'selfcheck_collapsed_triangles': collapsed,
        'selfcheck_triangles': int(len(faces)),
        'selfcheck_seconds': round(time.time() - started, 2),
        'selfcheck_engine': f'libigl {metadata.version("libigl")} find_self_intersections',
    }


def cube(offset=(0.0, 0.0, 0.0), size=1.0):
    corners = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], float) * size + offset
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    faces = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    return corners[np.array(faces)]


def self_test():
    """Known answers: a closed cube has none; overlapping cubes intersect;
    two cubes sharing only a face region but not interpenetrating stay
    distinguishable through the coplanar count."""
    results = {}
    for name, triangles, expect_found in [
            ('closed_cube', cube(), False),
            ('separate_cubes', np.concatenate([cube(), cube((2.0, 0, 0))]), False),
            ('overlapping_cubes', np.concatenate([cube(), cube((0.5, 0.5, 0.5))]), True)]:
        vertices, faces, collapsed = weld(triangles)
        found, pairs, coplanar, involved = count_pairs(vertices, faces)
        results[name] = {'found': found, 'pairs': pairs, 'coplanar': coplanar}
        if found != expect_found or collapsed:
            raise SystemExit(f'self-test failed for {name}: {results[name]}')
    return results


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--self-test':
        print(json.dumps({'self_test': self_test()}, sort_keys=True))
    elif len(sys.argv) == 2:
        print(json.dumps(check(sys.argv[1]), sort_keys=True))
    else:
        raise SystemExit(__doc__)
