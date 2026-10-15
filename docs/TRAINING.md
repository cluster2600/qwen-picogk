# Training, evaluation and reproduction

## Exact released checkpoint

The base is `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit` at revision
`b3252a2f97102b1fb1571fec2c9b27219a8536be`. `release.json` lists all nine
base file hashes and every adapter hash. This is QLoRA-style training on a
4-bit MLX base, with rank 8, scale 20, no dropout and 16 adapted layers.

| Setting | Planner | Separate selector |
|---|---:|---:|
| Fixed additional steps | 240 | 160 |
| Learning rate | 0.0000025 | 0.000005 |
| Batch | 2 | 2 |
| Training records | 2,096 | 20 |
| Sequence cap | 1,024 | 1,024 |
| Prompt masking | enabled | enabled |

Planner seed: 9931312. The registered decoding is greedy, temperature zero,
192 plan tokens and EOS required. The observed planner maximum complete
training sequence is 547 tokens, peak allocation 5.000 GB and final validation
loss 0.018. Loss does not determine qualification. MLX 0.32.3, MLX-LM 0.31.3,
Transformers 5.17.0 and Python 3.12.11 were used on Apple silicon.

The planner is a continuation from the **rejected predecessor** adapter
`b714724b4fb500451b9fada523658775c99a324ef8d2e3d8336221c1af6cae46`,
distributed as the explicitly labelled training-parent asset. The baseline
asset is the retained earlier r3 adapter, not the original Qwen base. The
selector starts from the qualified planner and keeps a separate output task.

## Repeat this continuation

Download/extract the planner, baseline and training-parent release assets.
This repeats the final continuation from a retained parent; it does not
reconstruct the complete historical chain from Qwen. Two original coding-008
parent inputs are unavailable, so full historical retraining is not claimed.

```sh
.venv/bin/python -m mlx_lm lora \
  --model /path/to/exact/pinned/base \
  --train --data data/planner --resume-adapter-file models/training-parent/adapters.safetensors \
  --adapter-path work/retrained-planner --config training/configs/planner.yaml
```

For the separate selector, replace the data folder with `data/selector`,
the parent with `models/planner/adapters.safetensors`, the destination with
`work/retrained-selector` and the config with `training/configs/selector.yaml`.
Training validation data must remain fixed.
The command is a reproduction aid, not a promise of byte-identical weights
on different software/hardware. Do not select a new checkpoint on the now
public final set; create a new untouched final before future optimisation.

## Repeat exposed evaluations

```sh
.venv/bin/python scripts/evaluate.py --base /path/to/exact/base \
  --adapter planner --split test --output work/planner-contract-final.json
.venv/bin/python scripts/evaluate.py --base /path/to/exact/base \
  --adapter baseline --split test --output work/baseline-contract-final.json
```

These commands send the original raw messages, not canonical prompts, and
report **contract-only** scores unless `--native-host` is supplied. They do
not silently inherit historical native or retention qualification.

For a native replay on supported PicoGK platforms, install the .NET 9 runtime
and a compatible SDK, then build the trusted host. Its owner-authored source
is unchanged; vendored recipe libraries preserve their source pins. The
portable build uses official NuGet PicoGK 2.3.0. Its managed assembly differs
from the historically built wrapper, so new portability receipts remain
distinct from the original benchmark receipts.

```sh
dotnet restore native/GeometryHost.csproj --locked-mode
dotnet build native/GeometryHost.csproj -c Release -o native/bin --no-restore
.venv/bin/python scripts/evaluate.py --base /path/to/exact/base --adapter planner \
  --native-host native/bin/GeometryHost.dll --output work/planner-native-final.json
```

The trusted host checks positive volume, triangles, material/void probes,
STL roundtrip and analytic volume within 15% where applicable. It does not
test arbitrary generated C#, strict raw-mesh topology, physical tolerances,
fitment or manufacturing. Old 64-task retention is supplied as historical
evidence/data; this smaller portable evaluator does not re-execute those old
OpenUSD/C# harnesses or all library witnesses.

## Why both success and failure are published

The first independent continuation reached 58/60 development but only 27/60
on a final field-presentation shift; it was rejected. The successor used a
prospectively registered broader supported-syntax course, new numeric intents
and wrappers, with 1,418 preceding intents excluded. Its selected checkpoint
reached 53/60 development and 54/60 fresh final. Shared syntax families make
that result narrower than unseen-syntax generalisation.

The separate selector reuses the same twenty semantic questions across
train/development/final with different wrappers. Its 20/20 final measures
operation/JSON-format selection with supplied API cards, not independent task
generalisation. Full original native witnesses are summarised and hashed in
the library evidence; no CFD solver was run.
