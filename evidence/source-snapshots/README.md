# Historical source snapshots

These files preserve exact source bytes from before the repository layout
cleanup. They are evidence, not executable entry points.

- `v0.1.0/`: the original evaluator and gallery builder, checked against the
  unchanged `docs/visuals/generated/gallery.json` source hashes.
- `scan-demo-v0.2.0/scan_demo.py.txt`: the original scan launcher before its
  manifest moved to `config/scan-demo.json`.

The unchanged contracts source now lives in `contracts/__init__.py` and is
checked directly against the original gallery hash. The root `infer.py` and
`release.json` remain byte-identical because the separate AM C# study binds
its parent inputs to these paths and hashes. The current scan manifest records
the updated launcher hash and relocated training-config path; historical
results, data partitions and model weights are unchanged.
