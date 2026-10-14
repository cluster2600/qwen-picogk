# Original AM pairs plus short validated teachers

`train.jsonl` is exactly the bytes of `../train-chat.jsonl` (150 rows), followed by `../corrective-005/train.jsonl` (160 rows). No message is reserialized, duplicated or rewritten. `prepare.py` verifies the first 150 user/assistant hashes and round-trips them to the original raw ChatML text. It also verifies all 160 supplemental answer/source/fixture/native-result bindings. `provenance.json` records both source hashes and all row bindings; existing files are never overwritten.

The supplemental rows reuse 80 accepted synthetic teacher cases and 71 distinct C# programs. The original 150 remain the requested AM teaching corpus; their earlier runtime study accepted 12 geometry cases and retained 138 rejections. Including them does not convert those rejections into accepted geometry, nor establish generalization, physical scan accuracy or manufacturing qualification.

Independent validation uses the pinned 14B tokenizer and the installed prompt-masked ChatDataset on CPU. Preparation performs no model loading, MLX/GPU operation, native rerun, training registration or final-task access. A later training decision must separately bind this exact corpus and its tokenizer receipt.
