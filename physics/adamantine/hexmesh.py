"""Convert a closed binary STL into a Gmsh 2.2 hexahedral mesh for adamantine.

Phase 3 of docs/PHYSICS_EVIDENCE_PLAN.md. A cell is solid when its centre is
inside the mesh by vertical ray parity, the same rule as the DfAM checker's
occupancy raster (rays jittered off cell edges). This is a separate tool so
the trusted checker and its corpus receipts stay unchanged.

    hexmesh.py PART.stl OUT.msh --cell-mm 1.0 [--plate-mm 5]   -> JSON summary on stdout

--plate-mm adds a build plate under the part, spanning the grid's footprint,
and writes its bottom faces as Gmsh quadrilaterals with physical tag 1, which
deal.II reads as boundary id 1 (clamped in the thermo-mechanical runs).

Coordinates stay in millimetres; set `units { mesh millimeter }` in adamantine.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

JITTER = (1.234567e-3 * np.sqrt(2), 2.345678e-3 * np.sqrt(3))   # fractions of a cell, as in the checker


def read_binary_stl(path):
    raw = Path(path).read_bytes()
    count = int(np.frombuffer(raw[80:84], '<u4')[0])
    record = np.dtype([('normal', '<f4', 3), ('v', '<f4', (3, 3)), ('attr', '<u2')])
    if len(raw) != 84 + count * record.itemsize:
        raise ValueError('not a complete binary STL')
    return np.frombuffer(raw[84:], record, count)['v'].astype(np.float64)


def signed_volume(tris):
    return float(np.einsum('ij,ij->i', tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum() / 6.0)


def occupancy(tris, cell):
    """Boolean grid (nz, ny, nx) of solid cells and the grid origin (cell corner)."""
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    origin = lo - cell
    nx, ny, nz = (np.ceil((hi - lo) / cell).astype(int) + 2)
    jx, jy = JITTER[0] * cell, JITTER[1] * cell
    # Every (triangle, column) pair whose column centre lies in the triangle's xy box.
    i0 = np.clip(np.floor((tris[:, :, 0].min(1) - origin[0]) / cell - 0.5).astype(int), 0, nx - 1)
    i1 = np.clip(np.ceil((tris[:, :, 0].max(1) - origin[0]) / cell - 0.5).astype(int), 0, nx - 1)
    j0 = np.clip(np.floor((tris[:, :, 1].min(1) - origin[1]) / cell - 0.5).astype(int), 0, ny - 1)
    j1 = np.clip(np.ceil((tris[:, :, 1].max(1) - origin[1]) / cell - 0.5).astype(int), 0, ny - 1)
    spans = (i1 - i0 + 1) * (j1 - j0 + 1)
    tri = np.repeat(np.arange(len(tris)), spans)
    local = np.arange(spans.sum()) - np.repeat(np.cumsum(spans) - spans, spans)
    width = (i1 - i0 + 1)[tri]
    ci, cj = i0[tri] + local % width, j0[tri] + local // width
    px, py = origin[0] + (ci + 0.5) * cell + jx, origin[1] + (cj + 0.5) * cell + jy
    a, b, c = tris[tri, 0], tris[tri, 1], tris[tri, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-18                                   # vertical triangles never cross a vertical ray
    with np.errstate(divide='ignore', invalid='ignore'):   # vertical triangles are masked by ok
        l1 = ((b[:, 1] - c[:, 1]) * (px - c[:, 0]) + (c[:, 0] - b[:, 0]) * (py - c[:, 1])) / d
        l2 = ((c[:, 1] - a[:, 1]) * (px - c[:, 0]) + (a[:, 0] - c[:, 0]) * (py - c[:, 1])) / d
        l3 = 1 - l1 - l2
        ok &= (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
    column, z = (cj * nx + ci)[ok], z[ok]
    # Count crossings below each cell centre per column: parity gives inside.
    order = np.lexsort((z, column))
    column, z = column[order], z[order]
    grid = np.zeros((nz, ny * nx), dtype=bool)
    centres = origin[2] + (np.arange(nz) + 0.5) * cell
    starts = np.searchsorted(column, np.unique(column))
    for col, s, e in zip(np.unique(column), starts, np.append(starts[1:], len(column))):
        crossings = np.searchsorted(z[s:e], centres)       # crossings below each centre
        grid[:, col] = (crossings % 2) == 1
    return grid.reshape(nz, ny, nx), origin


def add_plate(grid, origin, cell, plate_mm):
    """Fill the empty bottom layer and add layers below it, so the plate top is the part's lowest z."""
    layers = max(1, int(np.ceil(plate_mm / cell)))
    grid = np.concatenate([np.ones((layers - 1,) + grid.shape[1:], bool), grid], axis=0)
    grid[layers - 1] = True                       # the grid's first layer lies just below the part
    origin = origin.copy()
    origin[2] -= (layers - 1) * cell
    return grid, origin, layers


def write_gmsh(path, grid, origin, cell, physical=1, clamp_bottom=False):
    """Gmsh 2.2 ASCII: shared corner nodes, 8-node hexahedra (type 5) with one physical tag,
    and optionally quadrilaterals (type 3, physical tag 1) on the grid's bottom faces."""
    nz, ny, nx = grid.shape
    k, j, i = np.nonzero(grid)
    corners = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])
    keys = ((k[:, None] + corners[:, 2]) * (ny + 1) + (j[:, None] + corners[:, 1])) * (nx + 1) + (i[:, None] + corners[:, 0])
    used, inverse = np.unique(keys, return_inverse=True)
    inverse = inverse.reshape(-1, 8)
    ni = used % (nx + 1)
    nj = (used // (nx + 1)) % (ny + 1)
    nk = used // ((nx + 1) * (ny + 1))
    xyz = origin + np.stack([ni, nj, nk], 1) * cell
    quads = np.zeros((0, 4), int)
    if clamp_bottom:
        bottom = k == 0
        quads = inverse[bottom][:, [0, 3, 2, 1]]             # bottom face, outward normal -z
    n = len(inverse) + len(quads)
    with open(path, 'w') as out:
        out.write('$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n%d\n' % len(used))
        np.savetxt(out, np.column_stack([np.arange(1, len(used) + 1), xyz]), fmt='%d %.6f %.6f %.6f')
        out.write('$EndNodes\n$Elements\n%d\n' % n)
        elements = np.column_stack([np.arange(1, len(inverse) + 1), np.full(len(inverse), 5),
                                    np.full(len(inverse), 2), np.full(len(inverse), physical),
                                    np.full(len(inverse), physical), inverse + 1])
        np.savetxt(out, elements, fmt='%d')
        if len(quads):
            faces = np.column_stack([np.arange(len(inverse) + 1, n + 1), np.full(len(quads), 3),
                                     np.full(len(quads), 2), np.ones(len(quads), int), np.ones(len(quads), int),
                                     quads + 1])
            np.savetxt(out, faces, fmt='%d')
        out.write('$EndElements\n')
    return len(used), len(inverse)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stl', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--cell-mm', type=float, default=1.0)
    parser.add_argument('--plate-mm', type=float, default=0.0)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite an existing mesh')
    tris = read_binary_stl(args.stl)
    grid, origin = occupancy(tris, args.cell_mm)
    part_cells = int(grid.sum())
    plate_layers = 0
    if args.plate_mm > 0:
        grid, origin, plate_layers = add_plate(grid, origin, args.cell_mm, args.plate_mm)
    nodes, cells = write_gmsh(args.out, grid, origin, args.cell_mm, clamp_bottom=args.plate_mm > 0)
    mesh_volume = abs(signed_volume(tris))
    hex_volume = part_cells * args.cell_mm ** 3
    print(json.dumps({'stl_sha256': hashlib.sha256(args.stl.read_bytes()).hexdigest(),
                      'msh_sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(),
                      'cell_mm': args.cell_mm, 'grid': list(grid.shape[::-1]), 'nodes': nodes, 'hexahedra': cells,
                      'part_hexahedra': part_cells, 'plate_layers': plate_layers,
                      'plate_top_mm': round(float(origin[2] + plate_layers * args.cell_mm), 6),
                      'top_mm': round(float(origin[2] + grid.shape[0] * args.cell_mm), 6),
                      'stl_volume_mm3': round(mesh_volume, 2), 'hex_volume_mm3': round(hex_volume, 2),
                      'volume_ratio': round(hex_volume / mesh_volume, 4)}, sort_keys=True))


if __name__ == '__main__':
    main()
