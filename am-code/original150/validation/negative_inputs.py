#!/usr/bin/env python3
"""Prove malformed synthetic scan inputs fail before any candidate is exported."""

import hashlib
import json
from pathlib import Path
import subprocess
import uuid


def main():
    directory = Path(__file__).resolve().parent
    assembly = directory / "bin" / "Release" / "net9.0" / "AmDatasetValidation.dll"
    snapshot = {"dataset_sha256": hashlib.sha256((directory.parent / "data/picogk-am-150.jsonl").read_bytes()).hexdigest(),
                "assembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest()}
    cases = [
        ("nan-coordinate", "NaN,0,0,1,0,0,1,4,0,0\n", "nonfinite coordinate"),
        ("absent-oriented-normal", "0,0,0\n", "require outward normals"),
        ("zero-oriented-normal", "0,0,0,0,0,0,1,4,0,0\n", "require outward normals"),
        ("confidence-above-one", "0,0,0,1,0,0,1.1,4,0,0\n", "confidence in (0,1]"),
        ("confidence-zero", "0,0,0,1,0,0,0,4,0,0\n", "confidence in (0,1]"),
    ]
    run = directory / "negative-runs" / uuid.uuid4().hex[:12]
    run.mkdir(parents=True)
    results = []
    for name, data, expected in cases:
        case = run / name
        case.mkdir()
        fixture = case / "invalid.csv"
        fixture.write_text(data)
        output = case / "output"
        command = ["dotnet", str(assembly), "139", str(fixture), str(output)]
        process = subprocess.run(command, cwd=assembly.parent, capture_output=True, text=True, timeout=30)
        log = process.stdout + process.stderr
        (case / "run.log").write_text(log)
        exports = [path.name for path in output.iterdir()] if output.exists() else []
        passed = process.returncode != 0 and expected in log and not exports
        results.append({"case": name, "id": 139, "exit_code": process.returncode,
                        "expected_error_observed": expected in log,
                        "exported_files": exports, "status": "passed" if passed else "failed"})
    report = {**snapshot, "status": "passed" if all(result["status"] == "passed" for result in results) else "failed",
              "synthetic_only": True, "run_directory": str(run),
              "early_rejection_without_candidate_verified": all(not result["exported_files"] for result in results),
              "cases": results}
    (directory / "negative-inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
