#!/usr/bin/env python3
"""Execute compiled examples on synthetic inputs in isolated native processes."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import uuid

from fixtures import generate


def cross(left, right):
    return (left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0])


def mesh_screen(path):
    data = path.read_bytes()
    if len(data) >= 84 and len(data) == 84 + 50 * struct.unpack_from("<I", data, 80)[0]:
        triangles = []
        for offset in range(84, len(data), 50):
            values = struct.unpack_from("<12fH", data, offset)
            triangles.append((values[3:6], values[6:9], values[9:12]))
    else:
        coordinates = re.findall(rb"\bvertex\s+([\-+\deE.]+)\s+([\-+\deE.]+)\s+([\-+\deE.]+)", data)
        if len(coordinates) % 3:
            raise ValueError("ASCII STL has an incomplete triangle")
        vertices = [tuple(float(value) for value in vertex) for vertex in coordinates]
        triangles = [tuple(vertices[index:index + 3]) for index in range(0, len(vertices), 3)]
    if not triangles:
        raise ValueError("STL contains no triangles")
    edges = Counter()
    signed_volume = 0.0
    degenerate = 0
    for triangle in triangles:
        if any(not math.isfinite(value) for vertex in triangle for value in vertex):
            raise ValueError("STL contains nonfinite coordinates")
        first, second, third = triangle
        side_a = tuple(second[index] - first[index] for index in range(3))
        side_b = tuple(third[index] - first[index] for index in range(3))
        area_vector = cross(side_a, side_b)
        if sum(value * value for value in area_vector) <= 1e-16:
            degenerate += 1
        volume_vector = cross(second, third)
        signed_volume += sum(first[index] * volume_vector[index] for index in range(3)) / 6.0
        for left, right in ((first, second), (second, third), (third, first)):
            edges[tuple(sorted((left, right)))] += 1
    boundary = sum(count == 1 for count in edges.values())
    nonmanifold = sum(count > 2 for count in edges.values())
    return {
        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
        "triangles": len(triangles), "degenerate_triangles": degenerate,
        "boundary_edges": boundary, "nonmanifold_edges": nonmanifold,
        "signed_volume_mm3": signed_volume,
        "closed_edge_incidence": boundary == 0 and nonmanifold == 0,
        "positive_signed_volume": signed_volume > 0,
        "qualification": "geometric screen only",
    }


def run_example(example, assembly, fixture_dir, runs_dir, timeout):
    number = example["id"]
    output = runs_dir / f"Ex{number:03}"
    output.mkdir(exist_ok=True)
    mode = example["load_mode"]
    suffix = {"splats": "xyz", "oriented": "csv", "range": "csv", "mesh": "stl"}[mode]
    fixture = fixture_dir / f"input.{suffix}"
    command = [os.environ.get("QWEN_PICOGK_AM_DOTNET", "dotnet"), str(assembly), str(number), str(fixture), str(output)]
    result = {"id": number, "category": example["category"], "load_mode": mode,
              "fixture": fixture.name, "status": "failed", "command": command}
    start = time.monotonic()
    try:
        process = subprocess.run(command, cwd=assembly.parent, capture_output=True, text=True, timeout=timeout)
        (output / "run.log").write_text(process.stdout + process.stderr)
        result["exit_code"] = process.returncode
        if process.returncode:
            if "Safety rejection:" in process.stderr and not (output / "candidate.stl").exists() and not (output / "screen.json").exists():
                result["status"] = "early_safety_rejected"
                result["rejection_reason"] = next(line for line in process.stderr.splitlines() if "Safety rejection:" in line)
                result["elapsed_seconds"] = round(time.monotonic() - start, 3)
                return result
            raise RuntimeError("Native process exited with a failure; see run.log")
        screen = json.loads((output / "screen.json").read_text())
        if not isinstance(screen, dict):
            raise ValueError("screen.json must contain an object")
        if not isinstance(screen.get("geometry_screen_pass"), bool) or screen.get("manufacturing_authorized") is not False:
            raise ValueError("screen.json must report a geometry_screen_pass boolean and manufacturing_authorized=false")
        result["program_screen"] = screen
        result["mesh"] = mesh_screen(output / "candidate.stl")
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
        result["error"] = str(failure)
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    return result


def main():
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="Comma-separated example ids; omitted runs all 150")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180)
    arguments = parser.parse_args()
    if arguments.workers < 1 or arguments.timeout <= 0:
        parser.error("workers and timeout must be positive")
    examples = json.loads((directory.parent / "metadata.json").read_text())["examples"]
    if arguments.ids:
        ids = {int(value) for value in arguments.ids.split(",")}
        if not ids or any(value < 1 or value > 150 for value in ids):
            parser.error("ids must lie between 1 and 150")
        examples = [example for example in examples if example["id"] in ids]
    fixture_dir = directory / "fixtures"
    generate(fixture_dir)
    assembly = directory / "bin" / "Release" / "net9.0" / "AmDatasetValidation.dll"
    if not assembly.is_file():
        parser.error("Compile the dataset with validate_dataset.py first")
    snapshot = {
        "dataset_sha256": hashlib.sha256((directory.parent / "data" / "picogk-am-150.jsonl").read_bytes()).hexdigest(),
        "assembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest(),
    }
    compiled = json.loads((directory / "dataset-validation.json").read_text())
    if snapshot["dataset_sha256"] != compiled.get("dataset_sha256") or snapshot["assembly_sha256"] != compiled.get("compile", {}).get("assembly_sha256"):
        parser.error("Dataset or compiled assembly changed; rerun validate_dataset.py before native execution")
    runs = directory / "runs" / uuid.uuid4().hex[:12]
    runs.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        results = list(executor.map(lambda example: run_example(example, assembly, fixture_dir, runs, arguments.timeout), examples))
    passed = sum(result["status"] == "passed" for result in results)
    rejected = sum(result["status"] == "early_safety_rejected" for result in results)
    report = {**snapshot, "status": "passed" if passed + rejected == len(results) else "failed",
              "synthetic_only": True, "physical_qualification": False,
              "run_directory": str(runs),
              "executed": len(results), "completed_with_candidate_and_screen": passed,
              "early_safety_rejections": rejected, "unexpected_failures": len(results) - passed - rejected,
              "geometry_screen_accepted": sum(result.get("program_screen", {}).get("geometry_screen_pass") is True for result in results),
              "geometry_screen_rejected": sum(result.get("program_screen", {}).get("geometry_screen_pass") is False for result in results),
              "independent_native_processes": True,
              "closed_edge_incidence_count": sum(result.get("mesh", {}).get("closed_edge_incidence", False) for result in results),
              "examples": results}
    output = directory / ("native-runtime.json" if not arguments.ids else "native-runtime-subset.json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "examples"}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
