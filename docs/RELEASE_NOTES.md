# v0.1.0 — bounded multilingual PicoGK research release

First dedicated Apache-2.0 release: MLX planner/selector adapters, exact
synthetic training data, strict request contracts, English model/dataset
cards, pinned native library sources and exposed evaluation tooling.

The standalone portable evaluator reproduces **54/60** planner and **12/60**
retained-baseline final outcomes, including trusted native recipe screens.
The separate selector reproduces **20/20**, with its shared-question limitation
explicitly documented. Historical 64-task retention remains evidence from the
original harness rather than a newly executed portable check.

A fresh Git clone and new Python 3.12 virtual environment install the pinned
runtime successfully, pass `pip check`, reproduce mixed-unit inference and
refuse unverified interfaces without a model call. Nine focused tests and
Linux CI pass. This checks a fresh directory on the source Mac, not another
physical machine or a full historical retraining.

Assets:

- `planner-mlx.zip`: selected six-category planner, extracted to `models/planner/`.
- `selector-mlx.zip`: separate four-card operation selector.
- `baseline-mlx.zip`: retained earlier adapter used for comparisons.
- `training-parent-mlx.zip`: rejected predecessor retained only as the exact
  warm-start parent for this continuation; not the recommended inference model.
- `SHA256SUMS`: release archive integrity checks.

Base weights and native SDKs are downloaded separately. Each weight/config
is bound in `release.json`. Source documents, private archives and vehicle
identifiers are excluded. The original Porsche repository is unchanged.

HF-ready staging/card files are prepared. Hugging Face upload has not happened
because the source environment has no authenticated publishing identity.
The release is synthetic research, with no part or manufacturing qualification.
