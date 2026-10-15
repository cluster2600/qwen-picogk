#!/usr/bin/env python3
"""Generate exclusively synthetic 8 mm cube inputs; no measured scan data."""

import csv
import hashlib
import json
from pathlib import Path
import struct


def fixture_points():
    values = (-4.0, -2.0, 0.0, 2.0, 4.0)
    rows = []
    for axis in range(3):
        other = [index for index in range(3) if index != axis]
        for sign in (-1.0, 1.0):
            for first in values:
                for second in values:
                    point = [0.0, 0.0, 4.0]
                    point[axis] = (0.0 if sign < 0 else 8.0) if axis == 2 else 4.0 * sign
                    point[other[0]] = first + (4.0 if other[0] == 2 else 0.0)
                    point[other[1]] = second + (4.0 if other[1] == 2 else 0.0)
                    normal = [sign if index == axis else 0.0 for index in range(3)]
                    sensor = [point[index] + 4.0 * normal[index] for index in range(3)]
                    rows.append((*point, *normal, 1.0, *sensor))
    return rows


def cube_triangles():
    vertices = [(-4., -4., 0.), (4., -4., 0.), (4., 4., 0.), (-4., 4., 0.),
                (-4., -4., 8.), (4., -4., 8.), (4., 4., 8.), (-4., 4., 8.)]
    faces = [(0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7),
             (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5),
             (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2)]
    return [tuple(vertices[index] for index in face) for face in faces]


def generate(directory):
    directory.mkdir(exist_ok=True)
    points = fixture_points()
    assert len(points) == 150
    with (directory / "input.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("x", "y", "z", "nx", "ny", "nz", "w", "sx", "sy", "sz"))
        writer.writerows(points)
    (directory / "input.xyz").write_text("".join(" ".join(f"{value:g}" for value in point[:3]) + "\n" for point in points))
    triangles = cube_triangles()
    with (directory / "input.stl").open("wb") as output:
        output.write(b"Synthetic 8 mm cube; no measured geometry".ljust(80, b"\0"))
        output.write(struct.pack("<I", len(triangles)))
        for triangle in triangles:
            output.write(struct.pack("<12fH", 0., 0., 0., *triangle[0], *triangle[1], *triangle[2], 0))
    receipt = {
        "synthetic_only": True, "units": "mm", "shape": "8 mm cube",
        "bounds_min": [-4, -4, 0], "bounds_max": [4, 4, 8],
        "oriented_samples": len(points), "surface_grid_spacing_mm": 2.0,
        "normals": "outward", "weights": 1.0, "sensor_origin": "point + 4 mm outward normal",
        "limitations": "Sparse planar samples test I/O and execution; they do not qualify reconstruction accuracy.",
        "files": [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for path in sorted(directory.glob("input.*"))],
    }
    (directory / "fixture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(generate(Path(__file__).resolve().parent / "fixtures"), indent=2))
