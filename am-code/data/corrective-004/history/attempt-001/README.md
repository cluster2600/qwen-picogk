# Task-body augmentation 004

This corpus contains **320 newly worded user prompts backed by 80 existing validated teacher cases and 71 unique C# source programs**. Each teacher has four formulations: intent first, explicit pipeline/ownership, geometry or evidence specification first, and broken-API repair or conditional refusal contrast. Every row uses the existing full generic API header. It introduces no new algorithm, C# program, geometry parameter, scan, or native execution.

The assistant answers, including explanations and complete C# fences, are unchanged from corrective corpora 001 and 003. Their source programs, synthetic fixtures, independent oracles and retained native result hashes are bound in `manifest.json`. Input-driven programs legitimately share code between different validated fixtures. These are 80 teacher cases, not 320 new programs.

The augmentation follows a diagnostic in which course-005 reproduced all six selected seen answers and source programs byte for byte under compact/full headers, despite failing independent development tasks. That diagnostic receives no qualification credit. It supports testing task-body diversity; it does not establish a unique cause or guarantee the next course will generalize.

The new bodies spell out the same factual obligations in different request structures:

- TPMS family, phase origin, dimensionless nodal formula, cell period, nominal millimetre sheet width, re-distancing, symmetric offsets and clipping.
- Complete `IImplicit` helpers and the `Lattice` to `Voxels` to `Mesh` ownership pipeline; export the final field and remove exactly zero-area STL facets.
- Actual STL, named-plane CSV, XYZ and JSON input contracts; reference fixture values must not replace input-driven geometry.
- Exact JSON keys, value types and evidence IDs. Prompt-only refusals ignore the input path; signed-range refusals validate unsigned syntax; measurement-contract refusals dynamically report missing finite quantities. None creates native geometry.

The JSONL serialization is ASCII, using JSON escapes where unchanged assistant text contains Unicode. Parsing restores the original assistant strings and their exact SHA-256 hashes. All new prompts are ASCII. Only the generated synthetic teacher fixtures and existing parameters were used; no evaluation gold, development/final task bodies, captured model answers, private scans, or new physical measurements were used as teaching data.

`augment.py` derives facts from the existing teacher oracles, source and synthetic input files. It asserts header identity, 80-by-4 order, distinct prompt bodies, source/answer/fixture/native bindings, single complete C# fences, and unchanged parsed targets. Independent semantic and CPU tokenization reviews are separate receipts and must pass before a training course is registered.

Native teacher checks establish finite-resolution software and geometry behavior. TPMS grading is not Sigmund FE optimization, reconstruction is not complete Curless-Levoy range fusion, openings do not prove powder removal, and nominal wall rules do not solve Mercelis-Kruth residual stress. Manufacturing remains unauthorized.
