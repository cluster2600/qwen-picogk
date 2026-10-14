# Publishing the research release

GitHub is the source/evidence repository. Hugging Face should have separate
planner and selector model repositories plus one synthetic dataset repository.
Do not mix their incompatible output tasks or combine their evaluation scores.

The release contains HF-ready English cards under `hub/`. Run the packaging
script after `make check` and `scripts/check_release.py --weights`:

```sh
.venv/bin/python scripts/package_release.py
```

The script creates `planner-mlx.zip`, `selector-mlx.zip`, `baseline-mlx.zip`
and `training-parent-mlx.zip`, plus exact allowlisted Hugging Face staging
folders under `.release/huggingface/`. Base weights, native SDKs, private
archives, output directories and authentication files are not packaged.

With an authorised publishing identity, use Hugging Face's supported CLI:

```sh
hf repos create OWNER/Qwen2.5-Coder-1.5B-PicoGK-Planner-MLX-LoRA --repo-type model
hf upload OWNER/Qwen2.5-Coder-1.5B-PicoGK-Planner-MLX-LoRA .release/huggingface/planner .
hf repos create OWNER/Qwen2.5-Coder-1.5B-PicoGK-Selector-MLX-LoRA --repo-type model
hf upload OWNER/Qwen2.5-Coder-1.5B-PicoGK-Selector-MLX-LoRA .release/huggingface/selector .
hf repos create OWNER/picogk-synthetic-multilingual --repo-type dataset
hf upload OWNER/picogk-synthetic-multilingual .release/huggingface/dataset . --repo-type dataset
```

Use an existing narrowly scoped approved authentication mechanism. Never
paste tokens into this repository, shell arguments, logs, chat or model cards.
The source Mac's HF CLI currently reports no authenticated identity, so the
HF staging folders are prepared without claiming any Hub upload occurred.

After upload, verify the actual remote file lists, metadata, download hashes
and a fresh-directory inference. Add the real Hub URLs to the GitHub README
and cards only after confirming them. A successful upload is distinct from
inference-provider deployment; this adapter requires its pinned MLX base.

The original protocol/results remain historical evidence. Record portability
checks separately, including their hardware/software and omitted native tasks.
