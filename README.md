# Qwen PicoGK — bounded multilingual planning

An experimental **Qwen2.5-Coder-1.5B MLX LoRA adapter** for small synthetic
PicoGK parameter plans in English, French, German, Japanese and Chinese.
The supported-syntax final test passes **54/60**, versus **12/60** for the
retained earlier adapter on the same requests. Original exported material is
**Apache-2.0**. This independent repository contains no measured Porsche parts.

The useful contribution is a small, inspectable integration: explicit units
and radial roles, strict JSON, independent numeric intent checks, native
reference screens, failure records and uncertainty handling. It is not a
general CAD assistant or a manufacturing qualification system.

## Quick start on Apple silicon

Python **3.12** and the pinned MLX runtime are required for inference. Linux CI
checks contracts/data only. The adapter is MLX format, not a PEFT checkpoint.

```sh
git clone https://github.com/cluster2600/qwen-picogk.git
cd qwen-picogk
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
gh release download v0.1.0 --repo cluster2600/qwen-picogk --pattern 'planner-mlx.zip'
unzip planner-mlx.zip
mkdir work
.venv/bin/python infer.py --request examples/pipe-fr.json --output work/pipe.json
```

The archive extracts to `models/planner/`. First use downloads only the pinned
public base revision, roughly 1 GB. An existing exact base can instead be
supplied with `--base /path/to/base`; its nine file hashes must match.
Weights and configuration are verified before loading. No remote model code
is trusted. The launcher never executes geometry or generated code.

The French mixed-unit example requires `[12,8.5,2]` mm. Explicit named fields
are converted independently before inference; the model must preserve their
intent and reach EOS. This assisted command is **not** the raw multilingual
benchmark. Missing/unverified interfaces return `needs_measurement` without
calling MLX. Output files are never overwritten.

## What is supported

| Recipe | Ordered parameters, in mm |
|---|---|
| `cylinder` | length, radius |
| `pipe` | length, outer radius, inner radius |
| `washer` | thickness, outer radius, bore radius |
| `bcc` | cell side, beam **diameter** |
| `thread` | length, outer radius, core radius, pitch |
| `needs_measurement` | no parameters; missing measured interfaces |

All positive parameters lie within **0.5–24 mm**, with tighter BCC/thread
constraints. The thread cutter is synthetic, not a qualified thread standard.
The structured input accepts `mm`, `cm`, `m`, explicit length/radius/diameter,
and French/German decimal commas. Unknown fields, grouping, invalid bores,
nonfinite values and ambiguous quantity roles fail closed.

## Evidence and limitations

| Measurement | Recorded outcome | Interpretation |
|---|---|---|
| Supported-syntax fresh final | 54/60; retained baseline 12/60 | Shared syntax families; disjoint numeric intents and wrappers |
| Development | 53/60 raw; 60/60 canonical | Canonical input is a separate assisted mode |
| Old retention | 48/48 plans + 16/16 code | Previously exposed tasks, not new generalisation evidence |
| Final refusal cases | 10/10 | Small controlled set |
| Rejected predecessor | 27/60 final after 58/60 development | Substantial unseen field-presentation failure |
| Separate library selector | 20/20 development and final | Same twenty semantic questions with different wrappers |

The final contains 12 cases per language and ten refusal cases overall:
en/fr/de/zh each 11/12, ja 10/12. It is small, synthetic and single-seed.
The retained baseline is an earlier project adapter, **not untouched Qwen**.
The preceding failed final is a different protocol; the current 54/60 does
not solve that unseen-syntax benchmark. The selector only routes four supplied
API cards. Do not interpret its score as full-library knowledge.

Published final sets are now exposed and cannot serve as untouched future
holdouts. A correct JSON plan, positive voxel volume or STL roundtrip is not
proof of fitment, strength, fatigue, CFD/CHT or metal printing suitability.
Many bounded numeric tasks can be implemented with deterministic code; the
model's wider usefulness needs independent evaluation.

## Contents

- [Model card](hub/planner/README.md), [selector card](hub/selector/README.md),
  [dataset card](hub/dataset/README.md).
- [Training and reproduction](docs/TRAINING.md): exact parent, data, settings,
  exposed evaluation and recovery limits.
- [Provenance and licences](docs/PROVENANCE.md), [third-party notices](NOTICE).
- [Published results](evidence/results-002.json),
  [rejected predecessor](evidence/results-001.json),
  [library results](evidence/results-library.json).
- [Hugging Face publication procedure](docs/PUBLISHING.md).

`make check` uses the standard library and verifies the exported corpus,
contracts and vendored source hashes. On Python 3.12,
`python scripts/check_release.py --weights` also verifies all four downloaded
adapters. The historical GitHub project remains independent and keeps its
existing licence; this export grants no rights to its parts or private archives.
