---
license: apache-2.0
language: [en, fr, de, ja, zh]
task_categories: [text-generation]
tags: [picogk, cad, synthetic, multilingual, research]
size_categories: [1K<n<10K]
configs:
  - config_name: planner
    data_files:
      - split: train
        path: data/planner/train.jsonl
      - split: validation
        path: data/planner/valid.jsonl
      - split: test
        path: data/planner/new-test.jsonl
  - config_name: selector
    data_files:
      - split: train
        path: data/selector/train.jsonl
      - split: validation
        path: data/selector/valid.jsonl
      - split: test
        path: data/selector/test.jsonl
---

# PicoGK synthetic multilingual planning and operation selection

Owner-authored synthetic SFT messages and inspectable expected plans. No
measured vehicle geometry, scans, papers, proprietary manuals or external
CAD dataset is included. Original exported data: Apache-2.0.

The **planner** training file has 2,096 rows: 720 new multilingual rows and
688 old synthetic PicoGK/OpenUSD examples replayed twice. Repetition is
intentional; this is not 2,096 independent geometric designs. Development
and final each have 60 new requests, 12 per language and ten refusals overall.
Each JSONL row has `messages` with system/user/assistant roles. The case JSON
adds the independently specified request, expected plan, ID, language and
split for auditing. Older replay includes generated code text; never execute
arbitrary dataset text.

The new training course pairs radius/diameter renderings of 300 positive
numeric intents (600 prompts) and includes 120 refusals. Positive intents
and wrappers are split-disjoint. Recipe/vocabulary/supported field-syntax
families remain shared. Six bounded categories: cylinder, pipe, washer,
BCC cell, synthetic thread cutter, needs_measurement. Units: mm/cm/m;
positive ordered parameters generally 0.5–24 mm with stricter BCC/thread
bounds. Unknown Porsche interfaces stay unknown.

The **selector** has 20 rows in each partition, four operations times five
languages. The same twenty semantic questions repeat with different wrappers.
Use it for format/routing exercises, not independent semantic evaluation.

The released planner achieved 54/60 fresh final against 12/60 retained
baseline on the same requests. These metrics are specific to the registered
course and grader. The predecessor's 27/60 syntax-shift failure is documented.
These public final sets are now exposed and must not select future models.
All examples are research fixtures, not engineering evidence or build files.

Source attribution, exact hashes, training/evaluation scripts, model release
assets and rejected results are available at
[cluster2600/qwen-picogk](https://github.com/cluster2600/qwen-picogk).
Upstream Qwen's pretraining corpus was not independently audited.
