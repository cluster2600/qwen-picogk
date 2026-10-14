#!/usr/bin/env python3
"""Assert native geometric-screen behavior on closed, sealed, and drained coupons."""

import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from fixtures import generate


def main():
    directory = Path(__file__).resolve().parent
    fixture_dir = directory / "fixtures"
    generate(fixture_dir)
    assembly = directory / "bin" / "Release" / "net9.0" / "AmDatasetValidation.dll"
    snapshot = {"dataset_sha256": hashlib.sha256((directory.parent / "data/picogk-am-150.jsonl").read_bytes()).hexdigest(),
                "assembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest()}
    run = directory / "semantic-runs" / uuid.uuid4().hex[:12]
    run.mkdir(parents=True)
    screens = {}
    for shape in ("cube", "sealed", "drained", "floating", "below"):
        output = run / shape
        command = ["dotnet", str(assembly), "screen-fixture", shape, str(fixture_dir / "input.stl"), str(output)]
        process = subprocess.run(command, cwd=assembly.parent, capture_output=True, text=True, timeout=60)
        (run / f"{shape}.log").write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f"Native {shape} fixture failed; see {run / (shape + '.log')}")
        screen = json.loads((output / "screen.json").read_text())
        assert screen["manufacturing_authorized"] is False
        screens[shape] = screen
    cube, sealed, drained = (screens[name] for name in ("cube", "sealed", "drained"))
    floating, below = screens["floating"], screens["below"]
    assertions = {
        "cube_has_one_solid_component": cube["solid_components"] == 1,
        "cube_has_zero_trapped_voids": cube["trapped_void_components"] == 0,
        "cube_build_plate_is_not_an_overhang": cube["unsupported_triangles"] == 0,
        "cube_has_actual_plate_contact": cube["plate_contact_triangles"] > 0,
        "cube_geometry_screen_passes": cube["geometry_screen_pass"] is True,
        "sealed_cavity_is_detected": sealed["trapped_void_components"] >= 1 and sealed["trapped_void_voxels"] > 0,
        "sealed_internal_roof_is_rejected": sealed["unsupported_triangles"] > 0 and sealed["geometry_screen_pass"] is False,
        "drain_connects_cavity_to_exterior": drained["trapped_void_components"] == 0 and drained["trapped_void_voxels"] == 0,
        "drain_does_not_qualify_the_horizontal_roof": drained["unsupported_triangles"] > 0 and drained["geometry_screen_pass"] is False,
        "floating_cube_has_no_plate_contact": floating["plate_contact_triangles"] == 0,
        "floating_cube_is_rejected": floating["geometry_screen_pass"] is False,
        "below_plate_cube_is_detected": below["below_plate_triangles"] > 0,
        "below_plate_cube_is_rejected": below["geometry_screen_pass"] is False,
    }
    report = {**snapshot, "status": "passed" if all(assertions.values()) else "failed",
              "synthetic_only": True, "physical_qualification": False,
              "screen_source": "AmDataset.Ex136.Program.Screen from the compiled corpus",
              "run_directory": str(run), "assertions": assertions, "screens": screens}
    (directory / "semantic-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "screens"}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
