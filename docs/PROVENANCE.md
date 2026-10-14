# Scope of the Apache-2.0 export

This repository is a separate, owner-authorised export of project-owned
synthetic model exercises, adapter contributions, guards and reports. The
Apache-2.0 choice applies only to this export. It does not change the licence
of the source Porsche catalogue, CAD parts, private archives or source papers.

## Original sources and lineage

The source implementation/evidence is recorded in
[porscheparts PR 257](https://github.com/cluster2600/porscheparts/pull/257).
The qualified planner's registered source revision is
`e5c08ce597322fafa717d3767dfae0a678075bab`; the selector's is
`d0a5c0d8423d9d0fccb97065fe268b93eff16e32`. Their public result records were
exported byte-for-byte from revision
`a4c257f3994fb3bf214f24157c1af889a2fc746c`.

The qualified adapter bytes are unchanged; training-only absolute paths were
removed from **exported adapter configuration copies**. Historic originals
and their frozen hashes were not edited. `release.json` separately hashes
the exported configurations. The three loader fields (fine-tune type, layer
count and LoRA parameters) retain their exact original values.

The 2,096-row training file is exported byte-for-byte. Its first 720 messages
match the registered new cases, and its two 688-row replay copies are exactly
equal. Historical documentation identifies the replay as 240 synthetic
recipe/refusal rows, 96 PicoGK coding rows, 96 OpenUSD coding rows and 256
additional authored graph rows. The check script verifies these structural
relationships and screens for private paths and credential-shaped text.
That automated screen is not a universal privacy proof.

No research manuscript text, proprietary manual, raw scan, photograph,
supplier quote, vehicle identifier, external CAD dataset or measured Porsche
interface is exported. This scope follows the coding-curriculum source
records, not unrelated private field-extraction or materials experiments.

## Third-party dependencies

- Qwen2.5-Coder-1.5B-Instruct and the pinned MLX conversion declare Apache-2.0:
  [Qwen](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct),
  [MLX conversion](https://huggingface.co/mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit).
- The four geometry library source revisions, original licences and per-file
  hashes are in [native/sources.json](../native/sources.json). Exported source
  bytes were verified against the installed suite's integrity manifest.
- Scalar/vector selector cards derive from the CC0-noticed simulation files;
  QuasiCrystals and experimental Geometry are Apache-2.0. Exact revisions
  remain in [the library report](../evidence/results-library.json).
- PicoGK/native dependencies are restored from pinned official NuGet packages;
  native binaries are not copied into the Git repository.

No third-party notice is replaced by the repository's top-level licence.
The project is independent of Qwen, LEAP71 and Porsche; the names identify
models, APIs and source context rather than sponsorship.
