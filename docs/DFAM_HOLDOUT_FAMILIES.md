# Reserved validation and test families (proposal)

**Status: a proposal awaiting human review. Nothing here is a holdout yet.**
No case in `data/dfam-code/cases.jsonl` carries a `valid` or `test` split, and
no partition file exists. This document reserves the *names* of the families
that will fill those partitions, so that training cases written from now on do
not quietly become variants of a family meant to be held out.

The allocation it serves is the one in
[the corpus guide](DFAM_CODE_CORPUS.md#complete-the-corpus-and-reserve-evaluation-families):
15 validation and 15 test cases, split 5/4 for scan repair, 6/6 for bionic
infill, 3/3 for DfAM and 1/2 for troubleshooting.

## Why reserve names before authoring

The assembler keeps every variant of a `family` in one partition and rejects
lexical near-duplicates. That check runs at assembly, when 150 cases already
exist; by then a training case that duplicates a reserved operation is
expensive to move, because its family must move with it. Reserving the
operation up front makes the collision visible while the case is still an
idea.

## What the eleven existing cases can be

All eleven stay in `train`. They are published, and each one was iterated
against `dfam-native/Checker` until it passed: thresholds, vent sizes and
guard limits were chosen while watching the measurements. The corpus guide
already states that existing public examples and exposed tests cannot be
called untouched holdouts, and these are both.

The same argument rules out three otherwise attractive troubleshooting cases.
The `IntersectImplicit` narrow-band abort, the swapped `Library.MmToVoxels`
conversion and the needle triangles from a zero-valued level set are all
written up in `data/dfam-code/README.md` and in this `docs/` tree. A model
trained on this repository's prose has seen the diagnosis. They belong in
`train`.

## Reserved operations

One case per family for now. A later variant of a reserved family, in any
dimension, language or noise level, goes to that family's partition.

Several reserved operations below refuse an input. None of them refuses the
fixture it is graded on. `verify` measures an STL from every case, and only a
troubleshooting case may carry `broken` code that is expected to fail, so a
refusal path is exercised the way `dfam-001` and `infill-003` exercise theirs:
the graded run succeeds, and a variant that the program refuses is recorded as
a negative control under `evidence/dfam-code/negative-controls/`. A holdout
whose graded fixture it refuses is a holdout that cannot be verified.

### Scan repair (5 validation, 4 test)

| Split | Family | Operation that makes it distinct |
|---|---|---|
| valid | `scan-knn-statistical-outlier-rejection` | A statistical k-nearest-neighbour filter with a reported rejection rate, instead of letting the splat radius absorb outliers |
| valid | `scan-two-overlapping-clouds-merge` | Two clouds of one part, deduplicated and checked for rigid agreement; refuse a misaligned pair |
| valid | `scan-feature-preserving-decimation` | Decimation under a declared deviation bound, refused when the bound is exceeded |
| valid | `scan-multi-shell-triage` | Several reconstructed shells: keep the body, drop specks, refuse when a second shell is substantial |
| valid | `scan-nonuniform-density-resampling` | Resampling to a target spacing before reconstruction; refuse when a gap exceeds the splat radius |
| test | `scan-two-sided-thin-wall-cloud` | A cloud sampling both faces of a sub-millimetre wall, which must not fuse into one solid |
| test | `scan-open-shell-offset-thickening` | An open shell turned into a solid by offsetting the surface, not by closing its holes |
| test | `scan-units-and-axis-recovery` | Units and build axis inferred from the header and the bounding box, with a refusal when ambiguous |
| test | `scan-self-intersection-repair` | A raw mesh whose triangles intersect, repaired until the libigl sidecar is clean |

### Bionic infill (6 validation, 6 test)

| Split | Family | Operation that makes it distinct |
|---|---|---|
| valid | `infill-schwarz-primitive-graded` | A different TPMS family, graded by a scalar proxy field rather than by height |
| valid | `infill-octet-truss` | An octet cell, whose horizontal struts must be rotated away or refused |
| valid | `infill-voronoi-foam-z-biased` | A stochastic cell structure, seeds biased along the build direction |
| valid | `infill-internal-rib-waffle` | Not a lattice: internal ribs on the principal axes, each self-supporting |
| valid | `infill-conformal-offset-lattice` | A lattice warped to follow the skin instead of a straight grid |
| valid | `infill-prismatic-honeycomb` | A 2.5D honeycomb extruded along the build direction |
| test | `infill-density-from-supplied-field` | Density read from a supplied table or field file, not computed from geometry |
| test | `infill-packed-hollow-spheres` | Packed hollow spheres, each with its own drain opening |
| test | `infill-topology-blend` | A continuous blend between two sheet topologies, with a continuity guard |
| test | `infill-channel-clearance-band` | A lattice holding a declared clearance band around internal channels |
| test | `infill-guard-refuses-a-control` | A cell whose own down-skin self-check passes the graded fixture and refuses a recorded control variant |
| test | `infill-multi-body-part` | A lattice in the reserved multi-body fixture |

### DfAM (3 validation, 3 test)

| Split | Family | Operation that makes it distinct |
|---|---|---|
| valid | `dfam-bore-entry-exit-transitions` | Self-supporting entry and exit transitions on a vertical bore |
| valid | `dfam-support-free-boss-fillet` | A fillet radius chosen so a boss needs no support |
| valid | `dfam-orientation-scoring` | Candidate build orientations scored by down-skin area, with a refusal |
| test | `dfam-wall-thickening-with-draft` | Thickening to the minimum wall while holding a draft angle |
| test | `dfam-sacrificial-supports` | Support bodies generated as separate solids with a break-off interface |
| test | `dfam-powder-drain-ports` | Drain port placement and sizing on a closed cavity |

### Troubleshooting (1 validation, 2 test)

| Split | Family | Operation that makes it distinct |
|---|---|---|
| valid | `debug-nonmanifold-from-coplanar-boolean` | Non-manifold edges from a boolean between coincident faces |
| test | `debug-voxel-size-feature-loss` | A voxel size too coarse for the declared minimum wall, which silently loses a rib |
| test | `debug-part-splits-after-pocketing` | Pocketing leaves two solids, which no exception reports |

## Reserved fixture families

The corpus guide notes that three synthetic shapes are not evidence of
generalisation. Two further shapes are proposed, generated by the same trusted
checker and **used by no training case**:

| Family | Shape | What it exercises |
|---|---|---|
| `housing` | thin-walled box, 1.0-1.5 mm walls, a lid flange and two bosses | minimum wall, draft, drain ports |
| `multibody` | two solids joined by a thin bridge | component counts, splitting, per-body treatment |

Reserving a fixture is the stronger half of this proposal: a held-out case on a
held-out shape is not answered by memorising a training case's numbers.

## Authoring rules these names imply

1. A training case may not implement a reserved operation, and may not use the
   `housing` or `multibody` fixtures.
2. A holdout case is authored after the training cases of its category, from
   the prompt alone, without reading a training case's program.
3. A holdout case is still iterated against the checker, because it has to
   pass. That is a real limitation: its thresholds are fitted to its own
   output, exactly as the training cases' are. What it is never fitted to is a
   model's answer.
4. A holdout that fails is replaced, not loosened. Its declared limits are not
   widened to admit it, and its receipt is not re-run until it passes.
5. Test authoring and test results stay out of training decisions.

## Limits

This document reserves names and nothing else. It measures nothing, verifies
nothing and qualifies nothing. The partition it describes does not exist until
30 cases carry a `valid` or `test` split and pass native verification under
the strict policy. Disjoint family labels are not proof of independent
families: that grouping needs the human review this proposal is submitted for.
Even a complete partition on reserved fixtures measures generation of these
synthetic cases, not manufacturability of any real part.
