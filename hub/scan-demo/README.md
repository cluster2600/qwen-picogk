---
license: apache-2.0
base_model: mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit
language:
  - en
tags:
  - mlx
  - picogk
  - lora
  - experimental
---

# Qwen PicoGK scan-demo tool planner

An additional MLX LoRA continuation for **typed scan metadata → constrained
reconstruction-tool plan**. This is not a point-cloud encoder, scan-to-CAD
model, general C# generator or manufacturing qualification model.

The automated local chain audits a private triangular OBJ, derives open/closed
topology, asks this adapter for a JSON proposal, admits bounded settings,
executes established reconstruction tools and native PicoGK, and independently
screens the resulting STL before delivery. Qwen sees numeric metadata and
explicit assumptions; geometry algorithms consume the actual mesh. There is
no manual geometry editing in the command and no model-written code execution.

The owner explicitly allowed hypotheses for a demonstration. Missing surfaces,
scale, material and process remain assumptions. See the
[full English workflow and limitations](https://github.com/cluster2600/qwen-picogk/blob/main/docs/OBJ_TO_STL_DEMO.md).

The adaptive demo retains a rejected first recipe, permits one declared
scan-point envelope/closing operation, audits the closed result, then makes
a second real model call before the final native export and quality screen.
Unregistered minor input surfaces are retained separately; the main-body
demo requires at least 95% of acquired surface area. This is an explicit
scope assumption, not complete reconstruction or automatic assembly alignment.

160 fixed steps continue from the original released planner, using rank 8,
scale 20, 16 adapted layers, learning rate 1e-5 and batch two. The course has
480 synthetic training, 24 development and 40 final cases. Exact-preset scores
are 18/24 and 31/40; every mismatch is a face-budget choice. The bounded-budget
execution protocol is evaluated separately. No raw scan or scanned shape was
used in training. The original planner's 54/60 score does not apply here.

Keep input geometry private. A closed STL does not establish original shape,
fitment, minimum printable features, supports, distortion, fatigue, balancing
or a permitted rotational speed. This adapter and workflow cannot authorise
metal manufacture or installation.
