---
license: apache-2.0
---

# PicoGK DfAM code corpus (work in progress)

**Status: 4 of 150 planned cases.** This directory holds the tooling and the
first examples of a corpus for C# and PicoGK 2.3.0. The task
it covers is turning 3D scan data into lightweight parts designed for
laser powder bed fusion of metals (PBF-LB/M). The planned split is 45 scan
repair, 60 bionic infill, 30 DfAM and 15 troubleshooting cases. No
train/valid/test files exist yet, and assembly requires all 150 cases.
`scan-001`, `dfam-001` and `debug-001` pass the strict policy `dfam-strict-v3`
under isolated native verification ([receipt](../../evidence/dfam-code/strict-v3-20261015.json);
the earlier [strict-v2 receipt](../../evidence/dfam-code/strict-v2-20261015.json)
is kept). The first case, `infill-001`, fails on 86 degenerate triangles and a
detached zero-volume sheet that the self-intersection check reports. Its old
receipts and source are preserved.
See the [authoring and validation guide](../../docs/DFAM_CODE_CORPUS.md).

## How an example is accepted

Each record in `cases.jsonl` is a prompt, an explanation and a complete C#
program. `scripts/dfam_corpus.py` handles acceptance in two stages.

`lint` checks the following, without .NET:
- the schema;
- the exact headless `Run(Library, string, string)` entry point;
- comment density;
- PicoGK names that do not exist or misbehave;
- near-duplicates;
- that every `(year)` citation matches a key in `bibliography.json`.

`verify` compiles every example against the pinned PicoGK NuGet package and
runs each one on synthetic fixtures in a Linux bubblewrap namespace with
systemd memory/task limits, no network, read-only runtime/input mounts and
one writable output directory. Missing isolation stops verification; there
is no host-execution or uncapped fallback. This native path is not available
on macOS. It
then measures each output STL with `dfam-native/Checker`, which never loads
corpus code. The measurements are:
- open and non-manifold edges;
- solid components;
- powder trapped in fully enclosed cavities, rasterised by ray parity,
  independently of OpenVDB;
- the share of surface facing downward at less than 45 deg;
- the thin-wall share, measured by morphological opening;
- wall thickness on the mesh itself, by a ray from every triangle along the
  inward normal (area-weighted percentiles and the area below the minimum
  wall);
- needle triangles, whose height is below 1e-3 of their longest edge;
- self-intersecting triangle pairs, counted by a separate libigl sidecar with
  exact predicates;
- volume relative to the fixture.

Every example must have no detected open/non-manifold edges, inconsistent
orientations, degenerate or needle triangles, or self-intersecting pairs, and
one voxel-connected solid. Enclosed
voids must remain within the declared raster tolerances (2 mm³ total and
0.25 mm³ for the largest pocket); this is not a physical depowdering guarantee.
For `infill-001`, an unvented copy fails with 19,216 mm³ of trapped powder.
For `dfam-001`, the same channel with a round roof measures an overhang
fraction of 0.0483 and fails the declared 0.035 limit, which the teardrop
passes at 0.0218 ([negative control](../../evidence/dfam-code/negative-controls/)).

The fixtures are a synthetic slab with bosses, plus a noisy point cloud with
outliers and gaps derived from it. They are not a vehicle part.
`assemble` writes MLX `messages` records for prompt masking. It requires all
150 planned cases, family-disjoint partitions, current bound strict-policy
native receipts and a hash-verified local tokenizer. Rows exceeding 8,192
tokens are refused rather than truncated. The dedicated training configuration
is `training/configs/dfam-code.json`; the original 1,024-token planner settings
are unchanged. Historical receipts alone cannot authorize assembly.

## Runtime findings the corpus encodes

These were observed with PicoGK 2.3.0 and PicoGKRuntime `0f26321` on Linux:
- `IntersectImplicit` aborts with "expected grid A outside value > 0" at voxel
  sizes below 1/3 mm. The cause is that `PicoGKVdbVoxels.h:390` passes the
  background in millimetres to an integer narrow-band parameter. The corpus
  renders implicits into a `BBox3` and uses `BoolIntersect` instead.
- `Library.MmToVoxels` calls `_VoxelsToMm` in 2.3.0. It is fixed on upstream
  main.
- A `ScalarField` built from voxels returns `false` from `bGetValue` outside
  the narrow band, but the written value still has the correct sign.
  `fSignedDistance` scales those values by the voxel size a second time.
- Converting a mesh to voxels fills fully enclosed cavities. This is useful
  for solidifying a closed splat shell, and it is why the checker uses parity
  instead.

## Limits

Compilation, a closed mesh and the checker's metrics are not manufacturing
qualification. They do not establish strength, fatigue, dimensional accuracy
or printability on a given machine. The 1.0 mm minimum wall and the vent
sizes are stated assumptions. Sources are scoped in `bibliography.json`.
Several user-suggested sources were left out: two could not be accessed, one
was off-topic, and one was reachable only as a title.
