---
license: apache-2.0
language: [en, fr, de, ja, zh]
---

# Planner corpus

`train.jsonl` is the exact 2,096-row training file, with its original bytes:
720 new authored rows plus **688 old rows repeated twice**. The 688 old rows
contain 240 recipe/refusal tasks, 96 older PicoGK coding exercises, 96 older
OpenUSD coding exercises and 256 additional synthetic graph exercises.
Those repeated rows provide replay, not 1,376 independent observations.

`cases.json` has 840 original new records: 720 training, 60 development and
60 final. Each includes its explicit input, independent expected plan,
language, ID, split and messages. `new-train.jsonl`, `new-valid.jsonl` and
`new-test.jsonl` are the new-course SFT views; `valid.jsonl` is the exact
original validation file. Validation/final are never added to training.

There are 300 positive training intents with radius/diameter pairs, producing
600 prompts, plus 120 refusals. Positive numeric intents are disjoint across
new partitions. Recipe, vocabulary and supported field-syntax families remain
shared. Final/validation each have 12 cases per language and ten refusals.

`retention-plans.json` and `retention-code.json` are exposed old checks.
They are not new holdouts. The replay includes authored C#/OpenUSD text;
do not execute arbitrary dataset text. The provided evaluator executes only
the trusted fixed native recipe host, after independent contract checks.

Source records are synthetic exercises, not transcriptions of measurements.
No external Hugging Face CAD dataset was imported. Full upstream Qwen
pretraining provenance is outside this project's audit.
