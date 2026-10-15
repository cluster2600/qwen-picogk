# End-to-end OBJ → Qwen proposal → PicoGK STL demo

The new task is an automated **tool-assisted reconstruction demo**. It does
not make the text adapter a 3D encoder or a metrology instrument. Qwen proposes
a bounded reconstruction strategy from independently extracted topology and
explicit assumptions. Established geometry algorithms process the actual
vertices and triangles, and PicoGK builds the voxel model and STL. A separate
audit controls delivery; Qwen cannot certify its own proposal or geometry.

```mermaid
flowchart TD
    A["Private triangular OBJ"] --> B["Hash, indices, finite coordinates and topology audit"]
    B --> C["Explicit demo scale and independent open/closed feature"]
    C --> D["Separate trained Qwen scan-demo adapter"]
    D --> E["Strict JSON, EOS, method, units and resource bounds"]
    E --> F["Closed mesh import or screened Poisson hypotheses"]
    F --> G["Trusted PicoGK 2.3 C# host: Mesh → Voxels → STL"]
    G --> H["Independent topology and bidirectional surface-distance screens"]
    H --> I{"Demo screens pass?"}
    I -->|Yes| J["Deliver private demo.stl and evidence"]
    I -->|No| K{"Repair already used?"}
    K -->|No| L["Retain first rejection; one declared scan-envelope repair"]
    L --> M["Independent closed-envelope audit; second actual Qwen plan"]
    M --> G
    K -->|Yes| N["Retain rejected candidates; no delivered STL"]
```

## Scope and assumptions

The owner explicitly authorised hypotheses for a demonstration. The command
uses **1 mm per source coordinate unit**, **0.5 mm voxels**, **AlSi10Mg** as the
intended demonstration material and **laser powder bed fusion** as the intended
process. The material and process labels do not select machine parameters or
alter the mesh. A filename containing `0.5mm` does not calibrate the input.

The source is private and unchanged. Intake removes only exactly zero-area
triangles and applies a reversible rigid PCA pose. PCA is not a measured axis
or datum; no separate registration of a misaligned rear surface is performed.
Normals and material references in OBJ files are ignored, and referenced
material files are never opened. Polygons are rejected instead of silently
triangulated. Inputs are bounded to 256 MiB. No scan, reconstructed part or
user photograph is added to the public training corpus or repository.

For open input, the worker reduces the computational surface budget, estimates
normals and applies screened Poisson reconstruction. Missing surfaces become
**algorithmic hypotheses**, rather than measured geometry. Only tiny generated
components below the declared dust threshold are discarded. Independent scan
coverage must still pass. For closed input, the worker uses the acquired
surface directly. PicoGK then voxelises the closed surface and exports a new
mesh. This yields a voxel model, not a recovered feature-based CAD
design or inferred blade manufacturing drawing.

## What Qwen does

The original release remains unchanged. Its first scan-plan probe selected
direct voxelisation for an open scan and changed the requested 0.5 mm step to
5 mm. That answer was rejected. A separate 120-step continuation corrected
the step but still selected the wrong method for the specimen. It reached
23/24 development and 28/30 exact-preset final cases; those outcomes and the
failed specimen proposal remain evidence of a rejected candidate.

The separate 160-step course supplies a typed **open/closed** feature that is
derived from boundary-edge counts, rather than asking the language model to
infer topology from a large integer. Its 480 synthetic training records,
24 development records and 40 final records have disjoint numeric signatures;
the preceding final signatures are excluded. It continues from the released
planner with the same rank-8, scale-20, 16-layer LoRA, learning rate 1e-5, batch
two and prompt masking. No raw scan or scanned shape was used to train it.

The second candidate reaches **18/24 development and 31/40 exact-preset final**.
All 15 mismatches concern the specified 180,000-versus-300,000 face budget;
method, scale, voxel step and qualification flag agree in every recorded case.
These exact-preset scores are preserved. Execution separately permits either
of those two bounded budgets: retaining 300,000 faces is a valid, more expensive
geometry operation, even when the synthetic preset asked for 180,000. The
geometry screens remain mandatory. A separately registered fresh execution
final evaluates that policy; it must not be confused with the exact-preset
score or scan-reconstruction accuracy.

The fresh bounded-budget execution final passes **32/32** proposals. This is
tool-plan admission with typed metadata, not 32 successful scan reconstructions.

## Actual owner-selected fan OBJ: automatic run rejected

The selected input is the previously studied horizontal fan scan, identified
by its SHA-256. It has 624,492 vertices, 1,240,465 triangles and two acquired
surface components. Removing 26 exactly zero-area faces leaves 8,657 boundary
edges. The original bytes remain unchanged.

The single command calls the separate Qwen adapter, preserves its actual
Poisson/300,000-face/1 mm-per-unit/0.5 mm proposal without repair, reconstructs
the input, executes native PicoGK and performs the independent audit. It
produces 2,315,628 native triangles, passes closure, winding, positive volume,
zero-area and detected self-intersection/nonmanifold screens. Scan → native
P95 is 0.0722 assumed mm, with sampled maximum 0.2593 mm.

**It is rejected for delivery:** the STL has two substantial disconnected
components, rather than a tiny numerical speck, and native → open scan reaches
19.8988 assumed mm versus the registered 15 mm maximum. P95 in that direction
is 0.7051 mm; a low percentile does not excuse the unsupported closure. The
command exits 2 and creates no `demo.stl`. Its private candidate is retained
for diagnosis, and the public [rejection receipt](../evidence/scan-demo/automatic-scan-rejected.json)
contains metrics and provenance without mesh bytes.

This is evidence that the automatic chain and refusal work. It does not meet
the owner's target of an impeccable printable reconstruction. Rear registration,
unsupported hub/rear closures and complete component reconstruction remain
geometry work. Any alternative reconstruction is a new, separately screened
candidate; thresholds and the failed result are not silently changed.

## One bounded automatic repair for the demonstration

The first full-scan envelope also exposes a semantic input problem: an
unregistered subordinate scan surface crosses the fan's centre. Closure and
surface-distance checks cannot establish correct assembly registration. The
current demo therefore isolates the **dominant acquired surface**, requiring
at least 95% of total acquired triangle area. Any subordinate surfaces are
retained separately with face correspondence and are explicitly omitted from
the delivered main-body demo. Two substantial unregistered parts are refused,
rather than fused automatically. This is a declared scope assumption; it does
not recover the complete original OBJ or reconstruct the missing rear.

For the owner-selected input, this retains **98.6894% of acquired triangle
area** and omits **16,755 prepared triangles** into a separate private fragment
file. The retained surface has 1,223,684 triangles. The source OBJ stays
unchanged. These fractions describe acquired surface area, not confidence,
material mass or percentage of the original mechanical part reconstructed.

The next workflow version preserves that first failure and permits exactly
one further demonstration hypothesis. Its trusted C# recipe consumes the
actual prepared STL's vertices, deduplicates identical positions, creates a
PicoGK `Lattice` with 1 mm spheres, converts it to `Voxels` at 0.5 mm and applies
`Offset(3)` followed by `Offset(-3)`. Those fixed radii are declared demo
assumptions. The input points are real scan data, rather than the simulated
sphere in the suggested screenshots.

An independent backend witness finds a single closed, consistently oriented
surface and no detected self-intersections/nonmanifold features. It passes
the original distance thresholds: scan → envelope P95 1.0201 assumed mm and
sampled maximum 2.0513 mm; envelope → scan P95 1.4705 mm and sampled maximum
3.8572 mm. The unchanged thresholds and the rejected Poisson result remain
recorded. This witness uses owned C# directly and is **not a Qwen-generated
program or evidence of an end-to-end model run**.

The automatic chain uses that same recipe only after the first geometry
rejection, on that retained dominant surface. It independently inspects the resulting closed envelope and makes
a second actual Qwen call with the newly audited topology and counts. Qwen
must propose an admitted closed-mesh plan without changing units or voxel
step; the trusted native host executes it and the final mesh is audited
against the retained acquired surface. The receipt declares its retained area
fraction and omitted face count, and preserves the full-OBJ first result.
Both raw model responses and both quality records
are kept. If the second geometry fails, no STL is delivered; there is no
unbounded retry, manual edit or silent threshold change.

The repair changes the object into a **closed, thickened surface envelope**.
It can fill gaps, connect nearby acquired regions and change features smaller
than the closing scale. It does not establish the historical solid, correct
the rear registration or recover engineering intent. Any resulting STL is a
nonfunctional demonstration geometry under those assumptions, rather than
an impeccable recovered rotor or a metal-print release.

The separate direct route also runs end-to-end on a known 2 × 3 × 4 mm closed
synthetic box. A regression test ensures that the small acquired mesh survives
unchanged: the dust threshold applies only to generated Poisson fragments.
An acquired closed surface is not removed because it has fewer than 100 faces.
The [direct-route receipt](../evidence/scan-demo/closed-cube-direct.json) records
the actual model call, native result and independent geometry checks.

The model emits JSON, not unrestricted executable C#. Its raw output is stored
without repair and must reach EOS. Unsupported methods, changed scale/voxel
step, additional fields, duplicate keys, invalid integer settings and any
claim of manufacturing qualification are rejected. The C# host is owned,
compiled source using the pinned real API. There is no shell command or file
path generated by Qwen, and no model-written program is executed.

## Geometry acceptance before delivery

The final STL must have a single component, closed edge topology, consistent
winding, positive volume, no zero-area faces, no detected self-intersecting
faces and no detected nonmanifold edges or vertices. Native positive volume
and equal STL roundtrip triangle count are recorded separately.

Two independent sets of 2,000 area-uniform samples measure distances to target
triangles, with fixed distinct seeds. Under the assumed scale, scan → native
must have P95 ≤ 1.5 mm and sampled maximum ≤ 10 mm. Native → open scan must have
P95 ≤ 3 mm and sampled maximum ≤ 15 mm. These broad demonstration thresholds
are registered before geometry evaluation. They are not fitment tolerances.
The reverse direction includes reconstructed closures where the scan has gaps.
Sampled maxima are not exact Hausdorff distances, and the filters are finite
numerical screens rather than mathematical proofs.

## Local command and runtime

The separate adapter is available in the experimental
[scan-demo-v0.1.0 release](https://github.com/cluster2600/qwen-picogk/releases/tag/scan-demo-v0.1.0).
Install the original planner/base as described in the main README, then add
the separate scan adapter:

```sh
gh release download scan-demo-v0.1.0 --repo cluster2600/qwen-picogk \
  --pattern scan-demo-mlx.zip
unzip scan-demo-mlx.zip
python3 scripts/check_release.py --weights
```

The chain currently targets the configured Apple-silicon Mac. Use the original
pinned inference environment and base, and the separate scan-demo adapter.
Docker must contain the registered local scientific image identified in
`scan-demo.json`; the command does not pull an image or install software.
That environment already supplies NumPy, SciPy, trimesh, rtree and PyMeshLab.
Its amd64 geometry tools run locally under Docker emulation. Native PicoGK runs
on macOS through .NET 9 and the locked official PicoGK 2.3.0 NuGet package.

```sh
.venv/bin/python scan_demo.py \
  --obj /private/path/fan.obj \
  --output work/new-fan-demo \
  --base /path/to/the/exact/pinned/base \
  --demo
```

The output directory must be new. Within a Git checkout, output is restricted
to ignored `work/`. Source/adapter hashes and runtime versions are checked;
Docker uses read-only source mounts and no network. Evidence includes intake,
actual raw Qwen response, reconstruction hypotheses, native metrics, independent
quality results, logs and a final result record. `demo.stl` appears only after
acceptance. Rejected intermediate files remain private for diagnosis.

## Completed automatic main-body demonstration

The complete command runs on the owner-selected OBJ without manual geometry
editing. Its first raw Qwen proposal selects Poisson and preserves the declared
units/step. The first geometry is rejected and kept. The automatic demo repair
isolates the 98.6894% dominant surface, creates the declared envelope/closing,
independently audits it and calls the **same actual adapter again**. That second
raw response selects `direct_voxelization` for the now-closed envelope, preserves
1 mm/unit and 0.5 mm voxels, and reaches EOS. Neither response is repaired.

The final native STL has **3,487,584 triangles**, a single component, positive
volume, consistent winding and no zero-area, detected self-intersecting or
nonmanifold features. It passes the unchanged registered demonstration screens:

| Comparison against the retained surface, under assumed scale | P95 | Sampled maximum |
|---|---:|---:|
| Acquired dominant surface → final native STL | 1.0231 mm | 2.0381 mm |
| Final native STL → acquired dominant surface | 1.5557 mm | 3.7587 mm |

The command exits zero and writes `demo.stl`, with SHA-256
`bf5283aa0b55639109e122aeddce64ece955950398d6d91548b8b434be838572`.
The [public scalar receipt](../evidence/scan-demo/automatic-main-demo.json)
records scope, both quality outcomes, assumptions and source bindings. Its
private source snapshot preserves the executed worker version before the
small-closed-mesh regression fix; that fix affects the direct import branch,
not this fan's geometry operations. The owner requested publication of the
[fan preview](visuals/scan-demo/fan-preview.png); its
[provenance and reuse status](visuals/scan-demo/fan-preview.json) are recorded.
Raw geometry, correspondence, STL and GIF remain private. This single exposed
development example is not a new geometry
holdout, dimensional inspection, original CAD recovery or metal-process proof.

## About the suggested screenshot code

The screenshots describe point spheres followed by dilation/erosion, and their
loader generates a synthetic sphere rather than reading the owner's OBJ.
That is a conceptual illustration, not an implemented fan reconstruction.
The installed/reflected PicoGK 2.3 API has `Library`, `Mesh`, `Lattice` and
`Voxels`; it has no `VoxelMatrix`, `PolyMesh` or `Library.Init` from those
screenshots. The actual host uses `new Library(voxel)`,
`Mesh.mshFromStlFile`, `new Voxels(mesh)`, `mshAsMesh` and `SaveToStlFile`.
See the [official PicoGK source](https://github.com/leap71/PicoGK).

The additional workflow screenshot describes a plausible architecture, not
evidence that our adapter can generate a complete reconstruction program.
PicoGK's `Voxels` represent discretised signed-distance fields; see the
[official explanation of implicit geometry and offsets](https://picogk.org/coding-for-engineers/19-computational-geometry-part7.html).
Importing samples, voxelising them and closing gaps is therefore a possible
tool workflow. It does not establish recovery of the original part.

In the current demonstration, Qwen proposes **bounded JSON tool plans from
numerical metadata**. The geometry tools consume the actual scan, and the
trusted C# hosts are project code. Qwen did not generate those hosts, and no
model-written reconstruction program was executed. The earlier C# spaceframe
example does not demonstrate scan-to-code capability.

To demonstrate **OBJ → Qwen-generated PicoGK C# → faithful STL**, a separate
experiment must retain the raw model-written program, compile it against the
locked API, execute it in isolation and independently compare its output with
the acquired geometry. Any diagnostic-driven retry must preserve the failed
program and distinguish model corrections from human edits. Training needs
licensed executable geometry/program pairs and real compiler/runtime
diagnostics; the current metadata-only course does not supply those pairs.

Adding spheres and closing gaps can alter bores, merge adjacent blades and
change wall thickness. Neither that recipe nor Poisson reconstruction proves
the missing material's shape. Our code retains the acquired scan and measures
the proposed result instead of calling arbitrary smoothing a reconstruction.

## Remaining metal-print work

A successful result is a **geometry-screened demonstration STL**. A supplier
still needs machine-specific orientation, support access/removal, powder
evacuation, minimum features, allowances, calibrated parameters, thermal
distortion control, heat treatment, machining and inspection. The workflow
does not produce those settings, a machine build file or a physical print.

For a working rotor, measured interfaces, rear registration, material/process
allowables, load cases, fatigue/overspeed assessment and balancing are separate
requirements. Demonstration assumptions do not authorise installation or
rotation. Genuine feature-based reconstruction would require segmented blade
profiles, hub/bore axes and independently measured interfaces, followed by
feature-to-PicoGK program training and held-out geometry families. End-to-end
raw-scan learning would additionally require a dedicated 3D encoder and suitable
licensed scan/program training pairs.

## Training milestones beyond this tool planner

1. **Recover geometric features and correspondence.** Establish which acquired
   surfaces belong together, their alignment uncertainty, axes, hub/bore
   profiles, individual blade sections and real interface datums. Keep observed
   geometry, repairs and missing regions separate. A language model cannot
   infer an original surface that was never acquired merely from this dataset.
2. **Build licensed geometry/program pairs.** Start with owned PicoGK programs,
   independently checked native meshes and simulated scans containing realistic
   holes, noise and registration errors. Include refusal cases and preserve
   invalid programs/API diagnostics. Synthetic metadata rows alone do not
   teach geometric reconstruction. Do not add the private fan to public data.
3. **Train feature-to-code within the real API.** Add guarded lofts, local frames,
   bores, shells, implicit fields and boolean operations. Compile each accepted
   C# proposal against the exact locked libraries and evaluate resulting geometry
   independently. The earlier diffuser failure and screenshot API errors provide
   concrete negative examples; passing `AddBeam` does not cover those families.
4. **Evaluate unseen geometry, not just numbers.** Hold out complete rotor and
   feature families, scan defects and acquisition variants. Measure interface
   errors, bidirectional distances, missing/extra geometry, topology and critical
   thickness. Preserve exposed development cases and single-seed limitations.
   The owner's fan has been repeatedly inspected during development; it is not
   an untouched geometry benchmark.
5. **Add a 3D encoder only with a suitable corpus.** Raw point clouds need an
   explicit spatial input representation and scan/program supervision. The text
   adapter cannot acquire that ability through a different prompt or filename.
   Compare this route against the simpler feature/tool pipeline before increasing
   model size. Related research licensing must remain compatible with the intended
   distribution; none is silently imported into the Apache-2.0 project.
6. **Connect actual metal-process checks.** Choose the machine and qualified
   material/process, then assess orientation, supports, escape paths, allowances,
   distortion and inspection. Simulation and print/bench correlation are distinct
   from successful code, a closed STL or a favourable tool-plan score.
