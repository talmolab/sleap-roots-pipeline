# Bound the pipeline's GPU and stage-in concurrency with Argo semaphores

## Why

Nothing bounds how many `sleap-roots-pipeline-*` Workflows run at once
([#98](https://github.com/talmolab/sleap-roots-pipeline/issues/98)). No manifest in this repo
declares `synchronization`, `parallelism`, a semaphore or a mutex. The A4 design already specifies
the gate ("every GPU batch acquires `pipeline-gpu: K`",
`docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` §9), and the A4 epic
([#10](https://github.com/talmolab/sleap-roots-pipeline/issues/10)) lists it, but it was never built.

Bloom supplies no backpressure of its own. `services/workflows/pipeline.py` splits a run into
`BATCH_SIZE = 25`-scan batches, one Workflow each, and `dispatch_worker.run()` claims and submits
back to back, sleeping only when the queue is empty
([bloom#964](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/964)). An
experiment-level trigger therefore lands every batch on the cluster at once.

That collides with the GPU quota. The predictor runs non-preemptible (`priorityClassName: high`, on
purpose, #37) at `gpu-memory: "8192"`, which RunAI records as `RUNAI_NUM_OF_GPUS: 0.18` per pod
(read from a live predictor pod's RunAI GPU ConfigMap, 2026-09-30). That is 5 slices per GPU, 10
across busch-lab's 2-GPU deserved quota, and the quota is shared with the lab's interactive
sessions. Beyond it, predictor pods wait as `NonPreemptibleOverQuota` (`docs/cluster-identities.md`).

Observed on 2026-09-30 (staging run 17, Bloom PR #965's §12.10 check, as reported by the operator):
a 1,515-scan experiment became 61 Workflows (⌈1515/25⌉ = 61), all submitted within about a minute.
Staging's image objects were missing, so every images-downloader attempt failed and retried. Within
about ten minutes that had produced roughly 165 failed downloader pods and 27 predictor pods waiting
for GPU, while two colleagues' interactive sessions held 1.5 of the lab's 2 GPUs. The run was
cancelled by deleting its Workflows. (Those Workflows and their pods are gone, so the pod counts are
the operator's observation, not something this change re-measured.)

## What Changes

- Add a namespaced ConfigMap, `sleap-roots-pipeline-semaphores` (new file
  `sleap-roots-pipeline-semaphores.yaml`), holding two limits: `pipeline-gpu: "5"` and
  `pipeline-stage-in: "5"`.
- The `predictor` template acquires `pipeline-gpu` and the `images-downloader` template acquires
  `pipeline-stage-in`, each via `synchronization.semaphores[].configMapKeyRef`. At most 5 predictor
  tasks and 5 downloader tasks run across the whole namespace (prod, staging and manual runs share
  the pool, as they share the quota). A task waiting for a slot is a Pending Argo node with no pod.
- `runai_run_pipeline.sh` creates the ConfigMap if it is absent, before registering templates, and
  never overwrites an existing one.
- `scripts/check_manifests.py` asserts the wiring: both refs name the repo ConfigMap and a key it
  defines; every value is an integer ≥ 1; `pipeline-gpu` stays within the quota's slice capacity.
- `scripts/check_cluster_drift.sh` also compares the live ConfigMap's `data` against the repo's, so
  a live retune is reported as drift.
- Document the gate in `docs/cluster-identities.md`, annotate A4 design §9 with what was built, and
  update `openspec/project.md` (the semaphore is no longer open work; the launcher now also needs a
  kubeconfig).

Out of scope: a Workflow-level (whole-run) gate, which would need Bloom's vendored Workflow; the
`local-WSL2-*` manifests, which are unmaintained and slated for removal;
and stopping retries on a deterministic 404, which is a bloomctl exit-code distinction (retrying exit 3 is deliberate — see the 2026-09-15
partial-success design, line 249).

## Impact

- Affected specs: `per-batch-pipeline` (ADDED: concurrency semaphores; MODIFIED: launcher
  registration).
- Affected files: `sleap-roots-pipeline-semaphores.yaml` (new),
  `sleap-roots-predictor-template.yaml`, `sleap-roots-images-downloader-template.yaml`,
  `runai_run_pipeline.sh`, `scripts/check_manifests.py`, `scripts/check_cluster_drift.sh`,
  `docs/cluster-identities.md`, `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`,
  `openspec/project.md`.
- **Deploy order matters.** In Argo v3.6.7 a missing ConfigMap or key makes the acquiring node
  Error rather than wait; with `continueOn: {failed: true}` only, the DAG stops and the run ends
  red. Create the ConfigMap before `argo template update`.
- Bloom needs no change: its vendored Workflow reaches both stages through `templateRef`, so the
  gate takes effect on Bloom-dispatched runs once the templates are updated, and Bloom's
  vendored-Workflow drift check is unaffected.
