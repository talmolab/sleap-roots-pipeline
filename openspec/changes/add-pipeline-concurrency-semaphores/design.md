# Design: pipeline concurrency semaphores

## Context

Issue #98 offered two placements. This change takes the first, a template-level gate, and extends it
from the predictor to the images-downloader as well.

| Option | Bounds | Lives in |
|---|---|---|
| Template-level semaphore on `predictor` (+ `images-downloader`) | concurrent GPU tasks (+ stage-in tasks) | this repo |
| Workflow-level semaphore | whole runs | Bloom's vendored Workflow (`services/workflows/vendored/sleap-roots-pipeline.yaml`, pinned by `SLEAP_ROOTS_PIPELINE_REF`, drift-checked) — cross-repo |

Bloom's vendored Workflow references both stages by `templateRef`
(`sleap-roots-predictor-template` / `predictor`, `sleap-roots-images-downloader-template` /
`images-downloader`), so a gate on the WorkflowTemplates applies to every Bloom-dispatched run as
soon as the templates are updated in the cluster, with no Bloom change.

## Goals / Non-Goals

- Goals: cap the pipeline's concurrent GPU (predictor) and stage-in (images-downloader) tasks
  namespace-wide, so a large Bloom trigger cannot queue past busch-lab's GPU quota or flood the
  namespace with retrying pods; make the caps live-tunable and drift-checked.
- Non-Goals: bounding whole runs (a Workflow-level gate, cross-repo); Bloom-side backpressure
  (bloom#964); stopping retries on a deterministic 404 (bloomctl); gating trait-extractor or
  write-back; the local-WSL2 manifests.

## Verified facts this design rests on (2026-09-30)

- **Controller version is v3.6.7.** Every pod in `runai-busch-lab` carries
  `quay.io/argoproj/argoexec:v3.6.7`. The local CLI is v3.6.5, which is not what matters. The plural
  `synchronization.semaphores:` list is therefore supported.
- **`argo-user` may get, list, create, update and patch ConfigMaps** in `runai-busch-lab`
  (`kubectl auth can-i`).
- **Slice size.** A live predictor pod's RunAI GPU ConfigMap records
  `gpu-memory-request=8192000000` and `RUNAI_NUM_OF_GPUS: 0.18`: ⌊1/0.18⌋ = 5 slices per GPU, 10
  across the 2-GPU deserved quota.
- **Lock semantics, read from v3.6.7 source** (`workflow/controller/operator.go` `executeTemplate`,
  `workflow/sync/sync_manager.go`, `workflow/controller/controller.go`):
  - The lock is acquired under the node ID of the template's node, which for a template with a
    `retryStrategy` is the **retry parent**. It is released when that retry node is fulfilled. So
    one slot covers one task across all its attempts **and the backoff between them**, with at most
    one pod live at a time.
  - A node that cannot acquire is created `Pending` with the message
    `Waiting for <ns>/ConfigMap/<name>/<key> lock. Lock status: <free>/<limit>`; no pod is created.
  - Waiters are queued by Workflow `spec.priority`, then creation time, i.e. FIFO here.
  - The limit is re-read from the ConfigMap on every acquire attempt and the semaphore resized, so K
    can be changed live without restarting anything.
  - A missing ConfigMap, or a missing key, is an error, not a wait: `getSyncLimit` returns it and
    the node is marked Error.

## Decisions

### Two keys, one ConfigMap, one namespace-wide pool

`pipeline-gpu` on `predictor` bounds GPU pods directly. `pipeline-stage-in` on `images-downloader`
bounds the CPU pod flood a large trigger produces in stage-in, which is where run 17's pile-up was
largest. One ConfigMap keeps both knobs in one place.

The pool is shared by prod, staging and manual runs. That is intended: they share the namespace and
the GPU quota, so a per-environment pool would let two environments together exceed the bound.

No deadlock is possible: each task holds only its own stage's lock, and releases it before any
downstream task can start.

Alternatives considered: predictor-only (one key, as A4 §9 wrote it) leaves the stage-in pod flood
unbounded; a Workflow-level semaphore bounds whole runs but must live in Bloom's vendored Workflow;
workflow `parallelism` bounds fan-out within one Workflow, not across Workflows; a controller-wide
namespace parallelism limit is controller configuration this repo cannot set.

### Starting limits: K = 5, M = 5

Chosen by the repo owner (alternatives offered: 4/4, 2/4, 10/10). Five predictors are 0.9 GPU (5 × 0.18), one GPU's worth of slices, leaving
the other GPU for the lab's interactive sessions. The downloader limit matches, so stage-in keeps
roughly one batch ahead of each GPU slot without flooding the namespace with pods.

`check_manifests.py` enforces `pipeline-gpu ≤ 10`, derived as ⌊1/0.18⌋ × 2 at `gpu-memory: "8192"`.
It is an upper bound on what the quota can hold, not a recommendation. If the predictor's
`gpu-memory` or the project's quota changes, this bound must be re-derived.

### Held slot during retry backoff (accepted)

A predictor task that is failing deterministically holds its slot through `limit: 3` retries with
2m/4m/8m backoff, about 14 minutes, while running no pod for most of it. That wastes throughput but
never over-commits the quota, so it is acceptable. The alternative, a gate that releases between
attempts, is not what Argo implements at template level.

### Launcher creates the ConfigMap only if absent

`runai_run_pipeline.sh` runs `kubectl create -f sleap-roots-pipeline-semaphores.yaml` only when
`kubectl get configmap sleap-roots-pipeline-semaphores --ignore-not-found -o name` succeeds and
prints nothing. If that `get` itself fails (no kubeconfig, no VPN, no permission) the launcher
aborts before registering any template, rather than updating templates whose gate may not exist.
The launcher otherwise talks to the Argo Server (`gpu-master:8888`, `ARGO_TOKEN`), which has no
ConfigMap API, so this step is its only `kubectl` use and needs a working `KUBECONFIG`.

It never updates an existing ConfigMap, so a manual run cannot silently undo an operator's live
retune (for example, dropping `pipeline-gpu` to 2 while colleagues need the GPUs). Repo changes to the limits are applied by the deploy procedure,
not by the launcher, and `check_cluster_drift.sh` reports any live value that differs from the repo.

### Local-WSL2 templates are exempt

The `local-WSL2-*` manifests are Docker-Desktop/WSL2 counterparts, not mirrors, and parity between
them is mount/path parity (`openspec/project.md`). Local testing is CPU-only (the local predictor's
`nvidia.com/gpu: 1` is a known stale spot, per `project.md`), so there is no GPU quota to protect,
and the local launcher is currently broken for the A4 DAG (#21). A gate there would also need its
own ConfigMap in the local namespace. `check_manifests.py` asserts the local templates carry no `synchronization`, so the
exemption is explicit rather than accidental.

## Risks

- **Deploy order.** If the templates are updated before the ConfigMap exists, every new predictor
  and downloader node Errors. The DAG stops (the tasks' `continueOn` is `failed` only) and the run
  ends red, which is loud, not silent. Mitigation: the deploy procedure creates the ConfigMap first,
  and the rollback (below) is two template updates.
- **Accidental deletion of the ConfigMap** has the same effect. `check_cluster_drift.sh` reports a
  missing ConfigMap as drift.
- **Throughput.** A 61-batch experiment now runs at most 5 predictor tasks at a time. That is the
  point of the change; raise K live if the quota is free.

## Open Questions

- Can the workflow-controller's service account read ConfigMaps in `runai-busch-lab`? Standard in
  Argo's install, but cluster-scoped RBAC is Forbidden to `argo-user`; task 5.4's lock test is the
  evidence, and task 6.4 records it.
- Deploy from the branch before merge, or from `main` after? The owner's call at task 5.2.

## Deploy and rollback

Deploy (each step needs the owner's go-ahead; first confirm no `sleap-roots-pipeline` Workflow is in
flight with `argo list -n runai-busch-lab`):

1. `kubectl create -f sleap-roots-pipeline-semaphores.yaml`
2. `argo template update sleap-roots-images-downloader-template.yaml -n runai-busch-lab` and
   the same for `sleap-roots-predictor-template.yaml`.
3. `wsl -e bash scripts/check_cluster_drift.sh`.

Rollback: re-apply the two templates from the previous `main` commit. The ConfigMap can stay; nothing
reads it once no template references it.
