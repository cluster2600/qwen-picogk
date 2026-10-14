# AM C# training study — 14 October 2026

This separate study trains Qwen to write complete C# programs with PicoGK 2.3 for synthetic scan ingestion, morphological repair, bionic infill and additive-manufacturing geometry. **No AM C# adapter is qualified yet.** Four completed courses are rejected: three 1.5B courses and one fresh 7B course. Course 005 is registered and running. The repository's published multilingual JSON planner and its defaults are preserved.

| Experiment | Development | File-to-geometry scans | Outcome |
|---|---:|---:|---|
| Matched 1.5B base | 1/12 | — | Baseline |
| Original 150 pairs, 300 steps | 0/12 | 0/4 | Rejected |
| Compact 64 teachers, 192 steps | 0/12 | 0/4 | Rejected |
| Three header styles, 192 steps | 2/12 | 0/4 | Rejected |
| Matched untouched 7B base | 1/12 | — | Separate baseline |
| Fresh 7B, 342 rows and steps | 3/12 | 0/4 | Rejected |
| 7B continuation, course 005, 224 rows / 448 planned steps | Pending | Pending | Registered and running |

The bases pass different tasks. Candidate selection must use the matched baseline for its own base identity. [Results](evidence/results-summary.json) bind reported scores, captured responses, protocols, weights and configurations by SHA-256. Training loss, EOS, compilation and a closed mesh are separate observations; none replaces independent geometry or model gates.

Course 004 completed 342 steps with a finite adapter, and all 16 development/scan responses stopped normally. Initialization, erosion and hollow-shell tasks pass; the matched base's erosion pass is retained. The [independent diagnostic](evidence/course004-7b342-independent-review.json) records compile/API failures, incorrect geometry and output-contract failures. Its prompt-only refusal wrote the correct refusal JSON while also exporting invented geometry. A separate scan refusal preserved input-validity behavior but changed the required identifiers; STL roundtrip geometry passed while its report schema failed. The [formal gate](evidence/course-004-formal-rejection.json) rejects the adapter. Final tests remain unopened.

## Data and scientific scope

- [Original 150-pair ChatML JSONL](data/train.jsonl) is byte-identical to the requested dataset; [messages](data/train-chat.jsonl) preserve its user/assistant content for assistant-only loss. Categories are 45 scan, 60 infill, 30 DfAM and 15 debugging pairs. All 150 teachers compiled and completed native execution; only 12 geometric candidates passed their screens, while 138 were rejected. These are teaching/rejection examples, not 150 approved metal parts.
- [Corrective 64](data/corrective-001/train.jsonl) contains four fresh parameter/input variants of 16 families. Independent compilation, native execution and 900 Boolean checks pass. It includes 56 geometric coupons and eight bounded refusals, with actual input parsing, alternate fixtures, powder-port connectivity, shell cavities and TPMS family/width checks.
- [Header augmentation](data/corrective-002/train.jsonl) presents those unchanged 64 teachers under three generic headers: 192 rows and 55 distinct C# sources, not 192 new programs. The common development header stops before the task suffix; no development task body or reserved final content was copied.
- [Mixed 7B corpus](data/mixed-7b-001/train.jsonl) is the exact concatenation of original 150 messages and the 192 augmented rows. Actual 7B tokenizer and installed MLX dataset-mask checks cover all 342 rows; maximum sequence length is 5,416, under 6,144. No example is truncated.
- [Corrective 003](data/corrective-003/README.md) adds 16 fresh programs in 32 rows: eight prompt-only refusals and eight beams with specified radii and flat caps. Its retained native receipt passes all 16 programs and 648 Boolean checks; two deliberately incorrect beam variants are rejected. The first validation attempt is preserved with the correction for changing VDB file identifiers. Teacher source bytes are unchanged.
- [Targeted 224-row corpus](data/targeted-7b-001/train.jsonl) concatenates the 192 augmented rows and these 32 new rows exactly. Its actual 7B tokenizer receipt confirms complete assistant EOS, matching prompt prefixes and no truncation. [Course 005 registration](evidence/course-005-protocol.json) fixes a continuation from the rejected course 004 adapter for 448 steps over two epochs. This plan has no completed result yet; its live weights and log are excluded.

The real API types are `Voxels`, `Mesh`, `Lattice` and `System.Numerics.Vector3`; `VoxelMatrix` and `PolyMesh` are not PicoGK 2.3 types. The compact teachers produce one complete C# fence, own their headless Library lifetime, export the same solid to VDB/STL and remove exactly zero-area facets. Refusal programs do not initialize native geometry. Scans and dimensions are generated synthetic fixtures; no proprietary scan or measured vehicle interface is included.

[Scientific sources](original150/sources.json) distinguish the dimensionless Fourier nodal surfaces of von Schnering and Nesper from exact SDFs. TPMS carriers are re-distanced before millimetre offsets. Known nodal-ray width samples are local finite-resolution checks, not global wall guarantees or Sigmund structural optimization. Point normals/sphere splats do not reproduce full calibrated Curless–Levoy fusion. Conical angles and voxel void connectivity do not prove support-free LPBF or physical powder evacuation; wall assumptions do not solve Mercelis–Kruth residual stress. Strength, fatigue, fitment, distortion and machine/process qualification remain open.

## Portable source and reproduction boundaries

Python 3.12 and [the pinned requirements](../requirements.txt) are required for the MLX tools; native evaluation requires macOS arm64 and the declared .NET 9.0.317/PicoGK 2.3 runtime. This subtree contains public copies of training, capture, evaluators, qualification guards and the isolated CLI. Path relocation changes their byte hashes, recorded in [source export bindings](evidence/source-export-bindings.json). Historical receipts retain original hashes; sanitized copies are provenance views and are not fresh runtime qualification.

The default base is the existing nine-file 1.5B identity in [base-manifest.json](base-manifest.json), restored externally into the repository's ignored `model/` directory. [base-profile-7b.json](base-profile-7b.json) specifies the optional pinned 7B conversion and its contained `am-code/model7b/` directory. All nine files are verified before MLX loading; extra shards, mixed explicit/default identities and escaping paths fail closed. Base weights are fetched from their pinned upstream repositories; neither base is redistributed here.

Configure `QWEN_PICOGK_AM_DOTNET` and `QWEN_PICOGK_AM_PICO` to externally restored native paths and verify their identities with `python am-code/check_publication.py --native-runtime`. [Native dependency metadata](native-runtime-manifest.json) provides exact hashes and upstream URLs. Candidate execution retains the macOS sandbox. Restoring geometry/reference evidence from release archives or validating development references is required before native candidate scoring. Public scan bindings use the repository's retained planner/selector files; their public-location freeze is distinct from the historical local freeze. Relocation therefore needs configuration and validation, rather than a claim of drop-in reproduction.

For data/source checks without MLX or native execution:

```sh
make check PYTHON=python3.12
python3.12 am-code/check_publication.py
```

`train.py` supports an exact-hash supplemental corpus, a fresh output run and an optional pinned `--base-profile`; failed adapters are retained. `infer.py` captures model text and never executes it. Development selection requires at least 11/12, all four critical families, all four scan tasks, no lost baseline pass, complete stopped responses and bound native/source/model evidence. Final acceptance requires at least 11/12 under its independently registered gates. Reserved final prompts, references, gold exports and their task author are withheld until actual model evaluation opens that boundary. The final guard source and acceptance contract are included as prospective metadata, without final content.

The isolated `qwen-picogk-am` CLI is disabled (`TRUSTED_PROFILE_SHA256=None`) until a complete qualified profile/receipt is deliberately installed. No failed checkpoint is promoted or made the default. The header-style explanation for earlier format failures remains a hypothesis; the observed 2/12 course still fails qualification.

## Full evidence and assets

[AM release metadata](release.json) verifies this source/data snapshot and [asset inventory](evidence/assets.json). The [initial study tag](https://github.com/cluster2600/qwen-picogk/releases/tag/am-code-20261014-study) remains fixed at `baef888964d8f8f74c10e4a62d0b9aa7cca00359`; its five archives and two uploaded metadata files remain immutable. The additions described here belong to the [PR 2 source update](https://github.com/cluster2600/qwen-picogk/pull/2), and are absent from that initial tagged source snapshot. The PR's Files changed view provides the current source additions while review remains open.

A sixth asset, `rejected-7b-course004-full-evidence.tar.gz` (259,079,481 bytes), is separately staged with the completed 7B run, all six checkpoint/final adapter tensor files, its exact 342-row corpus, captured responses, raw logs, native STL/VDB exports, CPU audit and rejection evidence. [Course 004 asset metadata](evidence/course004-assets.json) records its hash and the unchanged initial uploaded metadata hashes. A seventh asset, `corrective003-full-native-evidence.tar.gz` (7,627,612 bytes), contains complete new teacher fixtures, retained native/fault evidence, source and token reviews, the targeted 224-row corpus and its provenance, and the course 005 registration. [Corrective 003 asset metadata](evidence/corrective003-assets.json) binds that separate archive. Unique `course004-AM-release.json` metadata accompanies this update; it does not replace the initial uploaded `AM-release.json`.

Each archive's `export-index.json` binds original bytes/hashes to public bytes/hashes and records local-path redaction. C# teachers, datasets, geometry and adapter tensor bytes remain exact. Original local artifacts are immutable. Third-party binaries, SDK/packages/caches/compiler products, upstream base weights and uncompleted course weights/logs are excluded. Large assets are kept out of Git history and clearly labelled unqualified; staging the new asset does not imply its upload already occurred.

Original exported source/data follow this repository's Apache-2.0 licence. Upstream models, libraries and scientific papers retain their own rights and notices; paper text is not included. This is software/geometry research and does not authorize manufacture.
