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

Bloom's vendored Workflow (salk-bloom `origin/main`, 2026-09-30) is still the **4-task** DAG — no
`continueOn`, no `exit-gate` — while this repo's `sleap-roots-pipeline.yaml` is the 5-task DAG.
Failure consequences below are stated for both.

## Goals / Non-Goals

- Goals: cap the pipeline's concurrent GPU (predictor) and stage-in (images-downloader) tasks
  namespace-wide, so a large Bloom trigger keeps the pipeline's non-preemptible GPU use within
  busch-lab's quota (at most K predictor pods, not one per batch) and at most M downloader pods into the namespace; make both caps
  live-tunable and drift-checked.
- Non-Goals: bounding whole runs (a Workflow-level gate, cross-repo); Bloom-side backpressure
  (bloom#964); stopping retries on a deterministic 404 (bloomctl); gating trait-extractor or
  write-back; the unmaintained `local-WSL2-*` manifests.

## Verified facts this design rests on (2026-09-30)

- **Controller version is v3.6.7.** Every pod in `runai-busch-lab` carries
  `quay.io/argoproj/argoexec:v3.6.7`. (The local CLI is v3.6.5, which is not what matters.) The
  plural `synchronization.semaphores:` list is supported; the singular form is deprecated.
- **`argo-user` may get, list, create, update and patch ConfigMaps** in `runai-busch-lab`
  (`kubectl auth can-i`).
- **Slice size.** A live predictor pod's RunAI GPU ConfigMap recorded
  `gpu-memory-request=8192000000` and `RUNAI_NUM_OF_GPUS: 0.18`: ⌊1/0.18⌋ = 5 slices per GPU, 10
  across the 2-GPU deserved quota.
- **Lock semantics, read from v3.6.7 source** (`workflow/controller/operator.go` `executeTemplate`;
  `workflow/sync/{sync_manager,semaphore,lock_name}.go`; `workflow/controller/controller.go`;
  `pkg/apis/workflow/v1alpha1/workflow_types.go`). These are source readings; task 5.5's lock test
  exercises 1 and 2, and the optional task 5.0 the rest.
  1. **One slot per task, held across retries and backoff.** The lock is taken under the task's
     node ID before the retry node is created, and released only when that node is fulfilled.
  2. **A waiting task has no pod.** Its node is Pending with
     `Waiting for <ns>/ConfigMap/<name>/<key> lock. Lock status: <free>/<limit>`.
  3. **FIFO.** Waiters are ordered by Workflow `spec.priority`, then creation time.
  4. **Resizing is lazy.** The limit is re-read from the API server on every acquire attempt, but a
     live *raise* wakes no waiter: `resize()` notifies nobody, and the ConfigMap watcher's
     `GetSemaphoreKeys` reads only `spec.templates` / `StoredWorkflowSpec`, which never contain a
     `templateRef` target. Waiters see a raise at the next slot release, or at the 20-minute
     workflow resync.
  5. **A failed limit lookup is an Error, including for running tasks.** `getSyncLimit` returns an
     error for a missing ConfigMap, a missing key, a non-integer value (`strconv.Atoi`) or a failed
     API read, and `TryAcquire` runs on *every* reconcile of an unfulfilled gated node. The error
     marks that node Error whether it is waiting or already running (`initializeNodeOrMarkError` →
     `markNodeError` for an existing node).
  6. **Holders are not restored after a controller restart.** `Initialize` resolves each holder's
     lock level from `wf.Spec.Templates`, which never contains a `templateRef` target, so it fails
     ("unable to determine level") and skips the holder. After a restart the pool starts empty. By
     fact 5 the old holders call `TryAcquire` again on their next reconcile and, queued by Workflow
     creation time, usually win their slots back, so over-admission is a short race (2K at worst).
     A holder that loses the race returns via `markNodeWaitingForLock` before `processNodeRetries`:
     its pod keeps running, but the node cannot retry or complete until it re-acquires.
  7. **Deleting a Workflow releases its slots** within about a minute (`CheckWorkflowExistence`),
     which is how Bloom run 17 was cancelled; a completed Workflow releases via `ReleaseAll`.
  8. The ConfigMap is looked up in the **Workflow's** namespace. Bloom forces that to
     `WORKFLOWS_K8S_NAMESPACE` (default `runai-busch-lab`).

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
unbounded; a Workflow-level semaphore bounds whole runs but must live in Bloom's vendored Workflow,
and has the same lookup-failure behaviour; workflow `parallelism` bounds fan-out within one
Workflow, not across Workflows; a controller-wide namespace parallelism limit is controller
configuration this repo cannot set.

### Starting limits: K = 8, M = 5

Chosen by the repo owner, 2026-09-30: the pipeline takes priority over the lab's interactive
sessions. Eight predictors are 1.44 GPU (8 × 0.18) of non-preemptible work, a margin below the
2-GPU quota in case another non-preemptible job appears; 10 would be the ceiling. The downloader
limit stays at 5.

**What K does and does not decide.** RunAI's admission check for non-preemptible work counts only
*non-preemptible* allocations against the deserved quota — its message reads "busch-lab quota is 2
GPUs, while 2 GPUs are already allocated for non-preemptible pods" (recorded in
`.claude/skills/runai/SKILL.md` §7). Preemptible sessions (`interactive-preemptible`, 75) don't
count toward it, and the predictor (`high`, 125) outranks them. So K predictors are within quota
whatever preemptible sessions are running, provided other non-preemptible busch-lab GPU work holds
≤ 2 − 0.18·K GPU (0.56 at K = 8, 0.2 at K = 10), and when physical GPUs are short RunAI
should preempt those sessions rather than hold the predictors. That preemption has not been
observed on this cluster; task 7.5 would show it if GPUs are tight. Run 17's 27 waiting predictors
are consistent with the pipeline's own non-preemptible pods exceeding the quota (61 batches against
room for about 11), which K prevents. Because a predictor can preempt a preemptible session,
`docs/cluster-identities.md`'s expectation to coordinate before large non-preemptible runs still
applies.

Two limits on this reasoning. It is GPU-only: the namespace also runs other non-preemptible
(`high`) workloads (cellranger and arabidopsis pipelines, 16 CPU / 64Gi per `count` pod, no GPU),
and whether busch-lab has a CPU or memory deserved quota that eight predictors (about 16 CPU / 96Gi
of non-preemptible requests) could exhaust has not been assessed. And 0.18 was measured on
gpu-node7 and gpu-node12 only: RunAI converts `gpu-memory` to a fraction of the landing node's GPU,
so on a smaller-memory GPU a predictor counts for more.

`check_manifests.py` enforces `pipeline-gpu ≤ 10`, derived as ⌊1/0.18⌋ × 2 at `gpu-memory: "8192"`,
and pins that `gpu-memory`, so changing it forces the bound to be re-derived. It is an upper bound
on what the quota can hold, not a recommendation.

### Retuning live

Lower or raise a limit with a validated patch, never `kubectl edit` (a typo is a non-integer, which
Errors every running gated task — fact 5):

```bash
n=3; [[ $n =~ ^[1-9][0-9]*$ ]] && kubectl patch configmap sleap-roots-pipeline-semaphores \
  -n runai-busch-lab --type merge -p "{\"data\":{\"pipeline-gpu\":\"$n\"}}"
```

A lowered limit applies at the next acquire. A raised one reaches existing waiters at the next
release or within 20 minutes (fact 4). `check_cluster_drift.sh` reports the live value until the repo
matches or the value is restored.

### Held slot during retry backoff (accepted)

A predictor task that is failing deterministically holds its slot through `limit: 3` retries with
2m/4m/8m backoff — at least 14 minutes, plus each attempt's run and RunAI-Pending time — while
running no pod for most of it. That wastes throughput but never over-commits the quota. Argo offers
no template-level gate that releases between attempts. Since the bloomctl writer flip (2026-09-29)
this is also the path a predictor takes when its run's images-downloader wrote no
`run_manifest.<name>.json`: predict exits 1 deterministically on every attempt, so a trigger-wide
stage-in failure (like staging run 17's) can hold every GPU slot for that long with no GPU work
done (about 61 × 14 m / 8 ≈ 1.8 h for a 61-batch run).

### Launcher creates the ConfigMap only if absent

`runai_run_pipeline.sh` otherwise talks to the Argo Server (`gpu-master:8888`, `ARGO_TOKEN`), which
has no ConfigMap API, so this is its only `kubectl` use and needs a working `KUBECONFIG`
(**BREAKING** for operators: the launcher previously needed only `ARGO_TOKEN`). Before registering
any template it:

1. aborts if `kubectl` is absent, and prints the `kubectl` context it will use, so a kubeconfig
   pointed at the wrong cluster is visible;
2. runs `kubectl get configmap sleap-roots-pipeline-semaphores --ignore-not-found -o name`, and
   aborts if that command fails (no VPN, no permission);
3. creates the ConfigMap only if that printed nothing (a concurrent launcher's `AlreadyExists` then
   aborts the second one, which is harmless);
4. otherwise checks each key the templates acquire is present and a decimal integer ≥ 1, and aborts
   if not — an incomplete ConfigMap would Error every gated node.

It never updates an existing ConfigMap, so a manual run cannot undo an operator's live retune.
Repo changes to the limits are deployed deliberately (below), and `check_cluster_drift.sh` reports
any live difference.

### Drift check covers the ConfigMap

`check_cluster_drift.sh` compares the live ConfigMap's `data` with the repo's: equal → IN SYNC;
different → DRIFT naming each key's repo and live values; absent → NOT CREATED (drift); a failed
read or failed comparison → CHECK FAILED (exit 2), never "in sync" and never downgraded to 1. The
existing template loop's `drift=1` assignments are fixed to stop overwriting an earlier 2.

### Local-WSL2 manifests are out of scope

The `local-WSL2-*` manifests are unmaintained and slated for removal (owner, 2026-09-30), so this
change neither gates them nor asserts anything about them.

## Risks / Trade-offs

- **ConfigMap loss or corruption kills running work.** Deleting the ConfigMap, a non-integer
  value, or a transient API-server error on the controller's live read marks gated nodes Error,
  including running ones (fact 5). In this repo's 5-task DAG the DAG stops, `exit-gate` is Omitted
  and the run ends red; in Bloom's 4-task DAG the failed task fails the Workflow. Either way the
  batch must be resubmitted. Mitigations: validated retunes only; the drift check reports a missing
  or malformed ConfigMap; the ConfigMap is never deleted while any gated Workflow exists.
- **Controller restart over-admits briefly.** After a restart the pool forgets its holders (fact
  6); they usually win their slots back on their next reconcile, so over-admission (2K at worst)
  is a short race, and a holder that loses it cannot retry or finish until it re-acquires. This is
  Argo behaviour this repo cannot fix. Predictors admitted beyond RunAI's non-preemptible quota
  wait as `NonPreemptibleOverQuota`.
- **Stuck Pending pods stall the whole namespace.** The slot is taken before the pod exists, and
  a pod that never schedules (hostPath mount failure, ImagePullBackOff, `NonPreemptibleOverQuota`)
  stays Pending with no retry, no `continueOn` and no timeout, holding its slot. Before this change
  such a hang stalled only its own run; now `pipeline-stage-in` such downloaders, or `pipeline-gpu`
  such predictors, stall every gated run in the namespace, Bloom prod included. Recovery: delete or
  `argo stop` the stuck Workflows (slots free within about a minute, fact 7). A pod-Pending timeout
  is a follow-up (task 8.6).
- **Deploy order.** Templates updated before the ConfigMap exists make every new gated node Error.
  The deploy procedure and the launcher both create the ConfigMap first.
- **Throughput.** A 61-batch experiment runs at most 8 predictor tasks at a time. That is the point;
  raise K when the quota is free.

## Migration Plan

Merge first; then deploy from `main` at the squash commit (the #89/#91/#92/#99 pattern — #53, applied
from an open PR, is recorded in the roadmap as a problem). Each cluster step needs the owner's
go-ahead:

1. `bash scripts/check_cluster_drift.sh` (WSL) → record as the rollback pre-image.
2. `argo list -n runai-busch-lab` → no `sleap-roots-pipeline-*` Workflow Running or Pending.
3. `kubectl create -f sleap-roots-pipeline-semaphores.yaml`.
4. `argo template update` the images-downloader and predictor templates.
5. `check_cluster_drift.sh` → exit 0.

Rollback: `argo template update` both templates from the squash commit's parent, **and** open a
revert PR on `main` (otherwise the next launcher run re-registers the gated templates). Keep the
ConfigMap until every Workflow that stored a gated template has finished — a running Workflow keeps
its stored template, and deleting the ConfigMap would Error it. Resubmit any batch that Errored.

## Open Questions

- Can the workflow-controller's service account `get` ConfigMaps in `runai-busch-lab`? Likely: the
  controller already lists and watches ConfigMaps in its managed namespace, and a failed cache sync
  at startup is fatal (`controller.go` `newConfigMapInformer`, `WaitForCacheSync`). That evidences
  `list`/`watch`, not `get`, and cluster-scoped RBAC is Forbidden to `argo-user`. Task 5.0 or 5.5 evidences it; task 6.4 records it.
