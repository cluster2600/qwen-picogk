#!/usr/bin/env python3
"""Validate the exact ChatML JSONL contract and compile every assistant snippet."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

CHATML = re.compile(
    r"\A<\|im_start\|>user\n(?P<prompt>.+?)\n<\|im_end\|>\n"
    r"<\|im_start\|>assistant\n(?P<answer>.+?)\n<\|im_end\|>\Z", re.DOTALL
)
FENCE = re.compile(r"^```csharp\s*\n(?P<code>.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)
CATEGORIES = {"scan": 45, "infill": 60, "dfam": 30, "debug": 15}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_example_identity(text):
    text = re.sub(r"\bAmDataset\.Ex\d{3}\b", "AmDataset.ExNNN", text)
    return re.sub(r"\bEngineering exercise \d{3}:", "Engineering exercise NNN:", text)


def parse_record(line, number):
    record = json.loads(line, object_pairs_hook=strict_object)
    if not isinstance(record, dict) or set(record) != {"text"} or not isinstance(record["text"], str):
        raise ValueError(f"Line {number}: expected exactly one string field, text")
    match = CHATML.fullmatch(record["text"])
    if not match or record["text"].count("<|im_start|>") != 2 or record["text"].count("<|im_end|>") != 2:
        raise ValueError(f"Line {number}: invalid two-message ChatML framing")
    prompt, answer = match["prompt"], match["answer"]
    blocks = list(FENCE.finditer(answer))
    if len(blocks) != 1 or len(re.findall(r"^```", answer, re.MULTILINE)) != 2:
        raise ValueError(f"Line {number}: expected exactly one complete csharp fence in assistant text")
    code = blocks[0]["code"]
    if not code.strip() or not answer[:blocks[0].start()].strip():
        raise ValueError(f"Line {number}: missing explanation or code")
    expected_namespace = f"AmDataset.Ex{number:03}"
    if not re.search(rf"\bnamespace\s+{re.escape(expected_namespace)}\s*[;{{]", code):
        raise ValueError(f"Line {number}: namespace must be {expected_namespace}")
    if "using Library lib = new(0.2f);" not in code:
        raise ValueError(f"Line {number}: missing agreed 0.2 mm headless Library initialization")
    if re.search(r"\b(?:TODO|FIXME|NotImplementedException)\b|^\s*\.\.\.\s*$", code, re.MULTILINE):
        raise ValueError(f"Line {number}: incomplete code placeholder")
    return record["text"], prompt, answer, code


def validate(dataset, metadata):
    payload = dataset.read_bytes()
    if not payload.endswith(b"\n"):
        raise ValueError("Dataset must end with a newline")
    lines = payload.decode("utf-8").splitlines()
    if len(lines) != 150:
        raise ValueError(f"Expected 150 nonblank physical JSONL lines, found {len(lines)}")
    if any(not line.strip() for line in lines):
        raise ValueError("Blank physical JSONL lines are forbidden")
    rows = [parse_record(line, number) for number, line in enumerate(lines, 1)]
    for index, label in ((0, "text"), (1, "prompt"), (3, "code")):
        if len({row[index] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate {label}")
        groups = {}
        for number, row in enumerate(rows, 1):
            groups.setdefault(without_example_identity(row[index]), []).append(number)
        duplicates = [ids for ids in groups.values() if len(ids) > 1]
        if duplicates:
            raise ValueError(f"Duplicate {label} after removing namespace/exercise identity: {duplicates}")
    meta = json.loads(metadata.read_text(), object_pairs_hook=strict_object)
    examples = meta["examples"]
    if len(examples) != 150 or [row["id"] for row in examples] != list(range(1, 151)):
        raise ValueError("Metadata ids must be ordered integers 1 through 150")
    categories = dict(Counter(row["category"] for row in examples))
    if categories != CATEGORIES:
        raise ValueError(f"Wrong category counts: {categories}; required {CATEGORIES}")
    for example, row in zip(examples, rows):
        number = example["id"]
        if example["code_sha256"] != hashlib.sha256(row[3].encode()).hexdigest():
            raise ValueError(f"Example {number}: metadata code hash does not match the assistant snippet")
        mode = re.search(r'LoadScan\(lib,\s*input,\s*h,\s*"(splats|oriented|range|mesh)"\)', row[3])
        if not mode or mode[1] != example["load_mode"]:
            raise ValueError(f"Example {number}: metadata input mode does not match the assistant snippet")
        if not row[1].startswith(f'Engineering exercise {number:03}: {example["title"]}.\n'):
            raise ValueError(f"Example {number}: metadata title does not match the user prompt")
    return rows, {
        "dataset": str(dataset.resolve()),
        "dataset_sha256": sha256(dataset),
        "metadata_sha256": sha256(metadata),
        "count": len(rows),
        "categories": categories,
        "unique_texts": 150,
        "unique_prompts": 150,
        "unique_code_blocks": 150,
        "unique_codes_without_namespace": 150,
        "unique_prompts_without_exercise_id": 150,
        "metadata_code_hashes_titles_and_input_modes": "passed",
        "template_sharing": "Each standalone program repeats headless initialization, input validation, loaders, and final geometry screens. Distinct parameter cases do not imply independent algorithms.",
    }


def compile_snippets(rows, validation_dir, runtime):
    snippets = validation_dir / "snippets"
    snippets.mkdir(exist_ok=True)
    for number, row in enumerate(rows, 1):
        (snippets / f"Ex{number:03}.cs").write_text(row[3] + "\n")
    project = ET.Element("Project", Sdk="Microsoft.NET.Sdk")
    properties = ET.SubElement(project, "PropertyGroup")
    for key, value in {
        "TargetFramework": "net9.0", "OutputType": "Exe",
        "StartupObject": "AmDatasetValidation.Runner", "Nullable": "enable",
        "ImplicitUsings": "disable", "EnableDefaultCompileItems": "false",
        "TreatWarningsAsErrors": "true", "AssemblyName": "AmDatasetValidation",
        "RestoreIgnoreFailedSources": "true",
    }.items():
        ET.SubElement(properties, key).text = value
    items = ET.SubElement(project, "ItemGroup")
    ET.SubElement(items, "Compile", Include="snippets/*.cs")
    ET.SubElement(items, "Compile", Include="Runner.cs")
    reference = ET.SubElement(items, "Reference", Include="PicoGK")
    ET.SubElement(reference, "HintPath").text = str(runtime / "PicoGK.dll")
    ET.SubElement(reference, "Private").text = "true"
    ET.indent(project)
    project_path = validation_dir / "AmDatasetValidation.csproj"
    ET.ElementTree(project).write(project_path, encoding="unicode")
    command = ["dotnet", "build", str(project_path), "-c", "Release", "--nologo", "-v", "minimal"]
    built = subprocess.run(command, cwd=validation_dir, capture_output=True, text=True, timeout=180)
    log = validation_dir / "compile.log"
    log.write_text(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError(f"Compilation failed; read {log}")
    output = validation_dir / "bin" / "Release" / "net9.0"
    for library in sorted(runtime.glob("*.dylib")):
        shutil.copy2(library, output / library.name)
    runtime_files = [runtime / "PicoGK.dll", *sorted(runtime.glob("*.dylib"))]
    return {
        "status": "passed", "compiled_snippets": 150,
        "command": command, "assembly": str(output / "AmDatasetValidation.dll"),
        "assembly_sha256": sha256(output / "AmDatasetValidation.dll"),
        "log": str(log),
        "sdk": subprocess.check_output(["dotnet", "--version"], cwd=validation_dir, text=True).strip(),
        "runtime_files": [{"name": path.name, "sha256": sha256(path)} for path in runtime_files],
    }


def main():
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=directory.parent / "data" / "picogk-am-150.jsonl")
    parser.add_argument("--metadata", type=Path, default=directory.parent / "metadata.json")
    parser.add_argument("--runtime", type=Path, default=Path(__file__).resolve().parents[2]/"work/picogk-runtime")
    parser.add_argument("--structure-only", action="store_true")
    arguments = parser.parse_args()
    report = {"status": "failed"}
    try:
        rows, details = validate(arguments.dataset, arguments.metadata)
        report.update(details)
        report["structure"] = "passed"
        if not arguments.structure_only:
            report["compile"] = compile_snippets(rows, directory, arguments.runtime)
        report["status"] = "passed"
    except (KeyError, ValueError, OSError, RuntimeError, subprocess.SubprocessError) as failure:
        report["error"] = str(failure)
    path = directory / "dataset-validation.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
