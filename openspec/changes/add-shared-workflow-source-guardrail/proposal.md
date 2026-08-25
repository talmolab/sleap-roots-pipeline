## Why

A live production bug was found and root-caused 2026-08-24/25 during a baseline end-to-end
validation of the A4 pipeline: `salk-bloom`'s dispatch worker
(`services/workflows/k8s_client.py::build_workflow_body`) hand-reconstructs the same `Workflow`
shape this repo's `sleap-roots-pipeline.yaml` already canonically defines, and silently dropped
`spec.volumes` entirely — every real batch dispatch failed with `volume 'images-input-dir' not
found in workflow spec`. Root cause: two independent hand-maintained representations of the same
Workflow shape with no mechanism to detect drift between them. This file is the only one that has
ever been correctly complete and the only one that has ever actually run successfully end-to-end
(PR #33, 2026-07-30).

Full design, agreed with Elizabeth before any implementation:
`docs/superpowers/specs/2026-08-25-shared-argo-workflow-source-design.md`.

The actual fix — vendoring a copy in `salk-bloom`, a CI drift-check against a pinned commit SHA,
and rewriting `build_workflow_body` to load and patch it — lives entirely in `salk-bloom` and is
tracked there as [bloom #737](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/737),
not part of this change. This repo's side is small and specific: add a guardrail comment to the
top of `sleap-roots-pipeline.yaml` so a future editor of its `volumes`/`entrypoint`/
`serviceAccountName`/DAG structure is warned, at the point of editing, that this file is vendored
elsewhere and that changing it without updating the vendored copy will fail `salk-bloom`'s CI
loudly rather than drift silently — which is exactly what happened this time with no warning at
all.

## What Changes

- **MODIFIED** `per-batch-pipeline` capability, "Four-stage per-batch DAG" requirement: add a
  scenario asserting `sleap-roots-pipeline.yaml` carries a guardrail comment naming the vendored
  path in `salk-bloom` and the drift-check mechanism, so the requirement now also covers this
  file's role as a cross-repo canonical source, not just its own internal shape.
- Add the guardrail comment itself to `sleap-roots-pipeline.yaml`'s header (above the existing
  `apiVersion`/`kind`/`metadata` block, alongside the file's existing reference-link comments).

## Impact

- **Affected specs:** `per-batch-pipeline` (MODIFIED).
- **Affected code:** `sleap-roots-pipeline.yaml` (comment-only change — no `spec` field is
  modified, so this does not affect any already-running or already-submitted Workflow).
- **Out of scope:** the actual `salk-bloom` vendoring/CI-check/`build_workflow_body` rewrite
  (tracked as bloom #737); the four `*-template.yaml` `WorkflowTemplate` files (a differently-shaped
  "is the cluster's registered copy in sync" question — see the design doc's Scope section).
