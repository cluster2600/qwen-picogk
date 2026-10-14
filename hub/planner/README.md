---
license: apache-2.0
library_name: mlx
base_model: mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit
base_model_relation: adapter
language: [en, fr, de, ja, zh]
pipeline_tag: text-generation
tags: [mlx, lora, picogk, cad, synthetic-data, research]
---

# Qwen2.5-Coder-1.5B PicoGK Planner — MLX LoRA v0.1

Experimental parameter planning for five bounded synthetic geometry recipes
and missing-interface refusal. **54/60** supported-syntax fresh final,
versus **12/60** for a retained earlier project adapter on the same requests.
These scores do not compare against untouched Qwen. The original 64-task
retention passes; those old tasks are exposed, not fresh generalisation tests.

![Actual Qwen-to-PicoGK mesh gallery](https://raw.githubusercontent.com/cluster2600/qwen-picogk/main/docs/visuals/generated/overview.png)

[Raw model responses, native STL files and image provenance](https://github.com/cluster2600/qwen-picogk/blob/main/docs/visuals/README.md).
These are exposed synthetic demonstrations, not a new benchmark.

![Restricted actual Qwen C# beam program rendered by PicoGK](https://raw.githubusercontent.com/cluster2600/qwen-picogk/main/docs/visuals/animations/spaceframe.gif)

[Restricted C# success and broader diffuser failure](https://github.com/cluster2600/qwen-picogk/blob/main/docs/SCAN_TO_PICOGK.md)
are separate probes. This adapter has no mesh/point-cloud encoder and does
not claim scan reconstruction or reliable arbitrary PicoGK program generation.

## Architecture and training

MLX LoRA rank 8, scale 20, no dropout, 16 layers on the 4-bit MLX
Qwen2.5-Coder-1.5B-Instruct base. Exact base revision:
`b3252a2f97102b1fb1571fec2c9b27219a8536be`. This file set contains only
the adapter: `adapters.safetensors` and `adapter_config.json`. It is not a
full standalone model or a Transformers/PEFT adapter.

240 fixed continuation steps, learning rate 0.0000025, batch 2, seed 9931312,
prompt masking, sequence cap 1,024. Training has 720 new authored examples
plus 688 synthetic replay examples repeated twice: 2,096 rows. The full
corpus and exact training parent are available in the
[source release](https://github.com/cluster2600/qwen-picogk).
MLX 0.32.3, MLX-LM 0.31.3, Transformers 5.17.0, Python 3.12.11.
Peak observed training allocation: 5.000 GB; inference is capped at 8 GiB.

## Use

Follow the [copy-and-run setup](https://github.com/cluster2600/qwen-picogk#quick-start-on-apple-silicon).
The repository launcher verifies base/adapter hashes and the explicit request
contract before accepting a result. Put these two adapter files under its
`models/planner/`. Example:

```sh
.venv/bin/python infer.py --request examples/pipe-fr.json --output work/pipe.json
```

Structured input requires recipe, language, interface status and named fields
with explicit values, units and length/radius/diameter quantities. The assisted
launcher canonicalises those fields before inference. Its results must not
be substituted for the raw multilingual benchmark. It never executes model
code or geometry. Unverified/missing interfaces refuse without model inference.

## Evaluation and limitations

Final languages: en/fr/de/zh 11/12 each; ja 10/12. Ten refusal cases are
included in the total sixty, all pass. The remaining fifty are synthetic
positive recipe requests. Numeric intents and phrase wrappers are disjoint;
supported syntax families and recipe vocabulary are shared with training.
Greedy decoding, 192 plan tokens and EOS required.

Development: 53/60 raw, 60/60 canonical. Canonical final was not separately
measured. A predecessor scored only **27/60** under an unseen field-presentation
shift and was rejected. That failure remains published; this release makes
no unseen-syntax or unrestricted natural-language claim.

Bounds: positive parameters 0.5–24 mm, tighter BCC/thread limits. Synthetic
thread cutters are not standard-qualified threads. Raw JSON, independent
intent agreement and native geometry screens do not establish fitment,
strength, fatigue, thermal performance, mesh qualification or manufacturing
approval. The test is small, single-seed and now public; make new untouched
holdouts for future selection. No measured Porsche part is represented.

## Provenance and licence

Original exported contributions: Apache-2.0, Copyright 2026 Maxime Grenu.
The Qwen base and MLX conversion retain their Apache-2.0 terms. Native
dependencies retain their individual licences. The scoped export does not
relicense the original Porsche catalogue. No private research documents,
scans, vehicle identifiers or external CAD training dataset are supplied.
Upstream Qwen pretraining data was not independently audited here.

[Source, evidence and reproduction limits](https://github.com/cluster2600/qwen-picogk/blob/main/docs/TRAINING.md).
