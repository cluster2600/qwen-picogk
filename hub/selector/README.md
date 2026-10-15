---
license: apache-2.0
library_name: mlx
base_model: mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit
base_model_relation: adapter
language: [en, fr, de, ja, zh]
pipeline_tag: text-generation
tags: [mlx, lora, picogk, research, operation-selection]
---

# PicoGK four-card operation selector — MLX LoRA v0.1

A separate experimental adapter that returns exactly one JSON key:
`{"operation":"scalar_vdb"}`. Other admitted values are `vector_vdb`,
`quasicrystal`, `geometry_frame`. It chooses among API cards supplied in the
system prompt; it does not produce geometry, C# or physics solutions.

It starts from the qualified planner and has 160 additional steps at learning
rate 0.000005, batch 2, LoRA rank 8/scale 20/16 layers. Same pinned 4-bit
Qwen base and runtime as the planner. This is MLX adapter format, not PEFT.

## Honest interpretation of 20/20

The course has **20 training, 20 development and 20 final requests**: four
operations times five languages. The same twenty semantic questions appear
across all three partitions with different English wrapper prefixes. The
trained selector passes 20/20 development and final; before selector training
the planner passes 14/20 development with the same cards. An earlier 80-step
trial passed 19/20 development and did not open its final.

This is a bounded operation/JSON-format check. It is **not an independent
semantic generalisation benchmark**, full API mastery or geometric accuracy.
Native reference checks are separate: six mesh/VDB recipes, 61 scalar/vector
probe positions, domain preservation, 32 experimental Geometry tests. No
CFD solver or physical validation was performed.

## Use and provenance

Put these two adapter files in the source repository's `models/selector/`.
The exact system cards and recorded questions are in `data/selector/`.

```sh
.venv/bin/python scripts/evaluate.py --adapter selector --split test --output work/selector.json
```

Original contributions: Apache-2.0. Scalar/vector cards derive from four
CC0-noticed PicoGK_SimulationExample source files; QuasiCrystals and
experimental PicoGK.Geometry are Apache-2.0. Source revisions, notices,
historical results and reproduction limits are recorded in the
[dedicated GitHub project](https://github.com/cluster2600/qwen-picogk).

Do not replace the planner adapter with this selector or combine their scores.
