# Review of the latest changes: 15 October 2026

Reviewed remote `main` at `935dd24` (PR #12), following PRs #7–#10, alongside
the PyMesh integration in PR #11. This review covers repository sources,
documentation, CI configuration and recorded metrics. It does not attribute
commits to a particular computer; Git does not establish that.

## What improved

- `dfam-strict-v3` adds needle-triangle detection, inward-ray wall-thickness
  measurements and a separately installed, hash-pinned libigl intersection
  sidecar. Current receipts bind both checker sources and case contents.
- The recorded isolated Linux run passes `scan-001`, `dfam-001` and
  `debug-001`. `infill-001` remains rejected: 86 degenerate triangles, the
  same 86 counted as needles, and four self-intersecting pairs. These are
  overlapping diagnostics, not 176 separate defects.
- The new figures and GIFs have provenance records. The physics plan
  distinguishes current geometry checks from planned process simulation.
- The scan reconstruction chain now separately uses genuine PyMesh for
  exact cleanup and intersection auditing. It does not change the DfAM
  policy, train a model, or qualify the demo fan for manufacture.

The current policy/checker hashes and all four case hashes were checked
against `strict-v3-20261015.json`; verdicts were recomputed from its recorded
metrics. This checks consistency, not independent reproduction of the Linux
native runs. The historical receipt was not rewritten.

## Next work, in order

| Priority | Work | Acceptance evidence |
|---|---|---|
| 1 | Correct the infill generator/export path in a new versioned candidate. Draft PR #6's vertex weld is insufficient for the detached zero-volume sheet. Keep the rejected seed and receipts. | New isolated strict-v3 receipt: zero degenerates, needles and intersection pairs; declared wall, overhang, volume and void gates pass. Compare the retained intended geometry and preserve the existing negative control. |
| 2 | Run the pinned libigl sidecar's known-answer tests in a required Linux CI job. | CI installs the hash-pinned CPython 3.12 Linux wheels and runs `selfcheck.py --self-test` without skips. The current contracts job does not install numpy/libigl and can skip this test; the PyMesh job tests a different engine. |
| 3 | Add adversarial thickness and component fixtures before treating the new metrics as broad coverage. | Known answers for tapered/curved thin walls, concave regions, reversed winding and a disconnected zero-volume sheet. Distinguish a capped ray from an unresolved ray; show what remains undetected. Centroid-normal distances are a geometric screen, not a certified minimum wall. |
| 4 | Expand the corpus by distinct geometry families and difficulty levels, with family-disjoint train/validation/test assignment. | Current strict receipts for every accepted case, no family leakage, tokenizer checks at the existing 8,192-token limit. There are only four of 150 planned cases and three accepted cases; assembly remains blocked. |
| 5 | Benchmark Linux capacity and reproduce one upstream physics example before a parameter sweep. | Exact host/runtime and solver bindings, measured peak memory/time, a predeclared comparison tolerance for the reference result, then an explicitly uncalibrated 316L study. Do not treat the plan's time estimates as measured capacity. |

## Physics-plan decisions to settle first

The [physics evidence plan](PHYSICS_EVIDENCE_PLAN.md) is a useful roadmap,
but its solver builds and results are still planned. Start with a single
upstream reference case and its published comparison quantities. Declare
numerical tolerances before running it; investigate failures before adding
an alloy or a sweep. Benchmark the actual Linux machines rather than assume
the stated 16-core/15-GB host is currently reachable or representative.

For a later adamantine study, confirm the suspected upstream formula issues
with small known-answer tests before interpreting those outputs. No upstream
report or fix was submitted during this review. A homogenised lattice and
lumped layers need a convergence/sensitivity study before comparing variants;
part-volume agreement alone does not validate temperatures or stresses.

## Integration boundary and limitations

The statement that PyMesh was unused has been corrected: scan reconstruction
uses its isolated legacy runtime; DfAM keeps libigl. Their welding tolerances
and intersection counts must remain identified separately. PyMesh runtime
redistribution licensing is unresolved here; it stays an external dependency.

The complete private-fan run passed its nine demo checks only after its one
declared envelope retry. The unregistered rear fragment is omitted and added
connections remain hypotheses, as documented in the
[scan guide](PYMESH_SCAN_RECONSTRUCTION.md). This is not a new model score,
an exact scan reconstruction, or a metal-print release.

No new training, physics solve, remote Linux native rerun or physical test
was performed for this review. No historical checkpoints or evidence were
replaced.
