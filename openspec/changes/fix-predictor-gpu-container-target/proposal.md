# Point the predictor's fractional GPU at the `main` container

## Why

The predictor runs inference on CPU while holding a GPU slice
([#117](https://github.com/talmolab/sleap-roots-pipeline/issues/117)). Run:ai, cluster 2.22.64,
gives a pod-level fractional GPU to `spec.containers[0]`. In an Argo pod that is the `wait` sidecar,
so `main` gets `NVIDIA_VISIBLE_DEVICES=void`. Evidence and history: design.md, Context.

## What Changes

- `sleap-roots-predictor-template.yaml`:
  - add a template-level `podSpecPatch` whose `$setElementOrder` puts `main` before `wait`, so
    RunAI 2.22 gives `main` the slice. This was live-tested on 2026-10-03 (tasks.md §3);
  - add `gpu-fraction-container-name: "main"` beside `gpu-memory: "8192"`. Run:ai ≥ 2.24 selects
    the container by name, so the fix holds after the upgrade; 2.22 ignores it;
  - the comments beside both are the canonical explanation. Also correct the comments that claimed
    the GPU was visible, and fix three references to the archived #25 design.
- `scripts/check_manifests.py`: assert the exact `podSpecPatch`, and every manifest clause of the
  "fractional GPU at the pod level" scenario. Until now only `gpu-memory` was asserted.
- `scripts/check_docs.py`: regression assertions for the corrected GPU text.
- Docs: one sentence each, pointing to the template comments, in:
  - `README.md`;
  - `.claude/skills/runai/SKILL.md`;
  - `openspec/project.md`;
  - `.claude/commands/ci-debug.md` (its "no GPU" row);
  - the `review-pr`, `review-openspec` and `docs-review` checklists.
- Unchanged:
  - the slice size, the scheduler, the `pipeline-gpu` semaphore, and the absence of
    `nvidia.com/gpu`;
  - `local-WSL2-sleap-roots-predictor-template.yaml`.

Out of scope:
- a CPU-fallback warning in `sleap-roots-predict` (task 7.1);
- the cluster upgrade, which is an admin request (task 7.2);
- the roadmap edits, which go in the post-deploy PR (task 6.5).

## Impact

- Affected specs: `per-batch-pipeline`, MODIFIED requirement "Predictor runs the warm GHCR predict
  container".
- Affected files:
  - `sleap-roots-predictor-template.yaml`;
  - `scripts/check_manifests.py` and `scripts/check_docs.py`;
  - `README.md` and `openspec/project.md`;
  - `.claude/skills/runai/SKILL.md`;
  - `.claude/commands/{ci-debug,review-pr,review-openspec,docs-review}.md`.
- Deploy is a single `argo template update`. Bloom references the predictor only by `templateRef`
  (`salk-bloom/services/workflows/vendored/sleap-roots-pipeline.yaml:118-121`), with no
  `podMetadata` or `podSpecPatch`, so it needs no change. Workflows already running keep their
  stored copy of the template.
- No recompute: neither field is an idempotency-key input.
- Measured effect (tasks.md §3R, T2): about 22–30 fps on GPU against about 2 fps on CPU, with
  prediction counts matching earlier CPU outputs. Worst-case memory, with every catalog model
  resident (3.7): 4,350 MiB reserved against 7,488 MiB usable.
- Risks: see design.md, Risks.
