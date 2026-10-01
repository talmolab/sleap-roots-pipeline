# Bound the pipeline's GPU and stage-in concurrency with Argo semaphores

## Why

Nothing bounds how many `sleap-roots-pipeline-*` Workflows run at once
([#98](https://github.com/talmolab/sleap-roots-pipeline/issues/98)), so one large Bloom trigger can
queue a predictor pod per batch against busch-lab's 2-GPU quota and flood the namespace with
retrying pods. The A4 design already specifies the gate ("every GPU batch acquires
`pipeline-gpu: K`", `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` §9),
and the A4 epic ([#10](https://github.com/talmolab/sleap-roots-pipeline/issues/10)) lists it, but it
was never built.

Background. No manifest in this repo declares `synchronization`, `parallelism`, a semaphore or a
mutex. Bloom supplies no backpressure of its own: `services/workflows/pipeline.py` splits a run
into `BATCH_SIZE = 25`-scan batches, one Workflow each, and `dispatch_worker.run()` claims and
submits back to back, sleeping only when the queue is empty
([bloom#964](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/964)). The predictor
runs non-preemptible (`priorityClassName: high`, on purpose, #37) at `gpu-memory: "8192"`, which
RunAI records as `RUNAI_NUM_OF_GPUS: 0.18` per pod (read from a live predictor pod's RunAI GPU
ConfigMap, 2026-09-30): 5 slices per GPU, 10 across the quota, which is shared with the lab's
interactive sessions. Beyond it, predictor pods wait as `NonPreemptibleOverQuota`.

Observed on 2026-09-30 (staging run 17, Bloom PR #965's §12.10 check, as reported by the operator):
a 1,515-scan experiment became 61 Workflows (⌈1515/25⌉ = 61), all submitted within about a minute.
Staging's image objects were missing, so every images-downloader attempt failed and retried. Within
about ten minutes that had produced roughly 165 failed downloader pods and 27 predictor pods waiting
for GPU, while two colleagues' interactive sessions held 1.5 of the lab's 2 GPUs. The run was
cancelled by deleting its Workflows. (Those Workflows and their pods are gone, so the pod counts are
the operator's observation, not something this change re-measured.)

## What Changes

- Add a namespaced ConfigMap, `sleap-roots-pipeline-semaphores` (new file
  `sleap-roots-pipeline-semaphores.yaml`), holding two limits: `pipeline-gpu: "8"` and
  `pipeline-stage-in: "5"`.
- The `predictor` template acquires `pipeline-gpu` and the `images-downloader` template acquires
  `pipeline-stage-in`, each via `synchronization.semaphores[].configMapKeyRef`. At most 8 predictor
  tasks (1.44 GPU, inside the 2-GPU quota) and 5 downloader tasks hold a slot across the whole
  namespace (prod, staging and manual runs share the pool, as they share the quota). A task waiting
  for a slot is a Pending Argo node with no pod.
- **BREAKING (operators):** `runai_run_pipeline.sh` now also needs `kubectl` and a `KUBECONFIG` that
  can read and create ConfigMaps in `runai-busch-lab`. Before registering templates it creates the
  ConfigMap if absent, never updates an existing one, and aborts if it cannot read it or it lacks a
  valid key.
- `scripts/check_manifests.py` asserts the wiring and limits; `scripts/check_cluster_drift.sh`
  compares the live ConfigMap and stops a later drift finding from masking a CHECK FAILED.
- Document the gate (what it bounds, how to retune it safely, the new failure symptoms) in
  `README.md`, `docs/cluster-identities.md`, `.claude/commands/ci-debug.md` and
  `.claude/skills/runai/SKILL.md`; annotate A4 design §9 with what was built; correct
  `openspec/project.md`'s stale A4 open-work list and its `NonPreemptibleOverQuota` advice.

Out of scope: a Workflow-level (whole-run) gate, which would need Bloom's vendored Workflow; the
`local-WSL2-*` manifests, which are unmaintained and slated for removal; and stopping retries on a
deterministic 404, which is a bloomctl exit-code distinction (retrying exit 3 is deliberate — see
the 2026-09-15 partial-success design, line 249). The roadmap update is drafted after merge, for the
owner's approval.

## Impact

- Affected specs: `per-batch-pipeline` (ADDED: concurrency semaphores; ADDED: drift check covers
  the ConfigMap; MODIFIED: launcher registration).
- Affected files: `sleap-roots-pipeline-semaphores.yaml` (new),
  `sleap-roots-predictor-template.yaml`, `sleap-roots-images-downloader-template.yaml`,
  `runai_run_pipeline.sh`, `scripts/check_manifests.py`, `scripts/check_cluster_drift.sh`,
  `README.md`, `docs/cluster-identities.md`, `.claude/commands/ci-debug.md`,
  `.claude/skills/runai/SKILL.md`,
  `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`, `openspec/project.md`.
  Not `sleap-roots-pipeline.yaml`, so Bloom's `SLEAP_ROOTS_PIPELINE_REF` pin and drift check are
  unaffected.
- **New failure modes (design.md, Risks).** A missing ConfigMap or key, a non-integer value, or a
  failed API read on the controller's live lookup marks gated nodes Error, including running ones,
  and a controller restart can transiently over-admit up to 2K tasks. Create the ConfigMap before
  `argo template update`, retune only with the validated patch, and never delete the ConfigMap
  while a gated Workflow exists.
- Bloom needs no change: its vendored Workflow reaches both stages through `templateRef`, so the
  gate takes effect on Bloom-dispatched runs once the templates are updated.
