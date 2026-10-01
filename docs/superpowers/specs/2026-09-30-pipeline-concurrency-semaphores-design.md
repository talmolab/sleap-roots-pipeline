# Pipeline concurrency semaphores — design (#98)

**Date:** 2026-09-30 · **Change:** `openspec/changes/add-pipeline-concurrency-semaphores/`

## Intent

A large Bloom trigger must not be able to flood busch-lab's GPU quota or fill the namespace with
retrying pods. Bloom submits every 25-scan batch of a run at once (bloom#964), and nothing in this
repo bounds how many run concurrently. Build the gate A4 design §9 already specifies ("every GPU
batch acquires `pipeline-gpu: K`"), in this repo.

## Decisions (agreed with the repo owner, 2026-09-30)

- **Placement:** template-level Argo semaphores on the WorkflowTemplates, not a Workflow-level gate.
  Bloom's vendored Workflow reaches both stages by `templateRef`, so this needs no Bloom change.
- **Scope:** two keys in one ConfigMap, `sleap-roots-pipeline-semaphores`: `pipeline-gpu` on
  `predictor` and `pipeline-stage-in` on `images-downloader`. One namespace-wide pool shared by prod,
  staging and manual runs.
- **Limits:** `pipeline-gpu: 8`, `pipeline-stage-in: 5` (owner, 2026-09-30: the pipeline outranks
  the lab's interactive sessions). Eight predictor slices = 1.44 GPU; the quota holds 10 whole slices.
  Retune live with the validated patch in the ConfigMap header, never `kubectl edit`.
- **Launcher:** creates the ConfigMap only if absent, never overwrites a live retune, and aborts if
  it can't read it or it's incomplete (BREAKING for operators: now needs `kubectl` + `KUBECONFIG`).
- **Known limits (from Argo v3.6.7 source, reviewed 2026-09-30):** a missing/malformed ConfigMap Errors running tasks too; a controller restart can
  transiently over-admit; a live raise reaches waiters only at the next release or ~20 min.
- **Deploy:** after merge, from `main`.
- **Checks:** `check_manifests.py` asserts the wiring and `pipeline-gpu ≤ 10`;
  `check_cluster_drift.sh` compares the live ConfigMap.
- **Out of scope:** the `local-WSL2-*` manifests: unmaintained, to be removed in a follow-up.
- **Follow-ups, not this change:** the deterministic-404 downloader retry (bloomctl), and a
  whole-run gate (Bloom).

Verified facts, lock semantics from Argo v3.6.7 source, risks, deploy order and rollback are in the
OpenSpec change's `design.md`, which is the authoritative record.
