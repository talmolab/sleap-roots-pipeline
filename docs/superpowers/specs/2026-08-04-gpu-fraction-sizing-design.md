# Enabling RunAI GPU fractions for the predictor — design

## Context

`sleap-roots-predictor-template.yaml` declares `gpu-fraction: "0.5"` at the WorkflowTemplate
object's `metadata.annotations`. Argo does not copy object-level annotations onto the pod, so this
value has no effect — the container's `resources.limits.nvidia.com/gpu: 1` is what actually takes
effect, and every predictor pod claims a whole GPU regardless. Tracked as
[issue #25](https://github.com/talmolab/sleap-roots-pipeline/issues/25), which already contains an
empirical repro (a live pod's annotations show no `gpu-fraction`, `runai-total-requested-gpus: "1"`)
and cites RunAI's own docs for the fix shape.

This matters now because Bloom is expected to submit inference-only predictor workloads into
`runai-busch-lab`, whose real configured GPU quota is **2 GPUs** (confirmed via
`runai project list`, not assumed) — small enough that whole-GPU-per-pod allocation defeats any
useful concurrency.

## What was measured (live cluster, not assumed)

- A real warm-batch predictor run (production image, 3-scan test batch) peaks at **4,676 MiB**
  GPU memory on a **46,068 MiB** card — about **10.2%** of the GPU. Memory reached this figure
  after model load and stayed flat across the rest of the batch (util varied 24–63%, memory did
  not); the trace does not show bursty spikes for this batch size.
- `runai-busch-lab`'s GPU node (`gpu-node2`) is comparable-class hardware: a 0.10 fractional
  request there reserved 4,830M, implying a ~48.3GB card — same order of magnitude as talmo-lab's.
- Cluster admission policy currently **rejects** `security.privileged` on `runai workspace submit`
  outright. The predictor ran successfully with no `privileged`/root override — independent,
  live-cluster confirmation that the templates' existing "likely unnecessary, verify + drop" TODO
  on `privileged: true` / `runAsUser: 0` was correct.
- `runai project list` shows `busch-lab`'s quota as **2.00 GPUs**, currently at **100% allocation**
  (both already held by pre-existing long-running interactive sessions unrelated to this program).
  This does not block Bloom's predictor pods: the template already runs at
  `priorityClassName: interactive-preemptible`, which schedules via RunAI's over-quota preemptible
  mechanism rather than requiring busch-lab's own deserved GPUs to be free — the same mechanism
  `talmo-lab` already relies on today (currently at 162% of its 20-GPU quota via preemptible jobs).

## Verified against RunAI's own docs (not just issue #25's description of them)

Fetched directly rather than relied on secondhand: RunAI GPU Fractions docs
(`run-ai-docs.nvidia.com/saas/platform-management/runai-scheduler/resource-optimization/fractions`).
Confirms: annotations go in **pod-level** `metadata.annotations` (not the container spec);
`schedulerName: runai-scheduler` is required (matches what we already expected to be automatic in
`runai-talmo-lab`/`runai-busch-lab`); no other required fields for a single-GPU-device fractional
request. Also surfaced something our original plan missed: RunAI supports **two** sizing modes —
`gpu-fraction` (relative, e.g. `"0.25"`) and `gpu-memory` (absolute MiB, e.g. `"4096"`) — and the
docs recommend the absolute form for precision. Also flagged: "splitting a GPU into fractions may
generate some fragmentation... the Scheduler will try to consolidate GPU resources where feasible
(preemptible workloads)" — relevant since predictor already runs preemptible.

## The fix

1. Move `gpu-memory: "<value>"` (absolute MiB, not a relative `gpu-fraction`) to
   `spec.templates[predictor].metadata.annotations` (pod-level), so Argo actually places it on the
   pod.
2. Remove `resources.limits.nvidia.com/gpu: 1` from the predictor container — fractional/absolute
   GPU-memory requests and whole-GPU limits are mutually exclusive in RunAI's model (this is also
   the literal root cause of issue #25: the pod inspection showed `runai-total-requested-gpus: "1"`
   with the old `nvidia.com/gpu: 1` limit present, i.e. RunAI honored the whole-GPU resource and
   ignored the annotation).
3. Remove `privileged: true` and `runAsUser: 0` from the predictor's `securityContext` — no longer
   just a TODO, now confirmed unnecessary (cluster policy blocks `privileged` anyway; the pod ran
   and wrote to the NFS hostPath output normally without either).
4. Confirm `schedulerName: runai-scheduler` lands on the resulting pod (confirmed required per
   RunAI's docs above; expected to already be automatic in `runai-talmo-lab`/`runai-busch-lab`,
   per the `runai` skill, since existing whole-GPU predictor pods already schedule via RunAI today
   — this task verifies that continues to hold, not that we need to add it ourselves).

## Sizing: `gpu-memory: "8192"` (8GB), not a flat fraction

Originally sized as a `0.25` fraction (~2.4x headroom over the measured ~4,676 MiB peak, 4 pods
per GPU). Switched to an absolute `gpu-memory` value per RunAI's own precision guidance, because a
flat fraction means something different on every card: `0.25` reserves ~11.5GB on talmo-lab's
46,068 MiB card but ~12.1GB on busch-lab's ~48.3GB card, despite the workload only ever using
~4.7GB either way — wasted headroom that directly costs concurrency on the smaller busch-lab
quota.

`8192` MiB gives ~1.75x margin over the measured peak (for larger production batches —
`BATCH_SIZE` up to ~25–50 vs. the 3-scan test measured here — and fragmentation/multi-tenant
safety), while allowing **more** concurrency than the flat-fraction approach:
`46068 ÷ 8192 ≈ 5` predictor pods per GPU on talmo-lab, `48300 ÷ 8192 ≈ 5` on busch-lab — versus
4 under the rejected `0.25`-fraction approach.

**Alternatives considered:**
- **Relative `gpu-fraction: "0.25"`** (original plan) — rejected in favor of absolute `gpu-memory`
  once RunAI's docs confirmed the memory-based form exists and is the precision-recommended
  option; sizing to measured VRAM directly is both more accurate and yields more concurrency here.
- **Dynamic GPU Fractions** (request/limit split) — issue #25 floats this for "bursty" memory.
  Rejected for now: the measured trace was a stable plateau, not bursty, so the added complexity
  isn't earned yet. Revisit if a real large-batch production run shows memory growth the 3-scan
  test didn't.
- **Larger reservation (e.g. 16GB), fewer concurrent (~3)** — more margin, but discards most of the
  concurrency this change exists to unlock. Rejected.

## Scope boundary

- `trait-extractor` (CPU-only) and `sleap-roots-images-downloader-template.yaml` /
  `sleap-roots-write-back-template.yaml` (bloomctl-based, no GPU) are untouched.
- `local-WSL2-sleap-roots-predictor-template.yaml` is untouched — GPU fractions are a
  RunAI-scheduler-specific concept with no equivalent on local Docker Desktop dev, and that file is
  already known-stale relative to the production template (old args pattern, old image).

## Spec impact

The existing `per-batch-pipeline` OpenSpec capability's "Predictor runs the warm GHCR predict
container" requirement currently asserts the predictor "SHALL request a GPU (`nvidia.com/gpu`)"
and its scenario asserts "it requests `nvidia.com/gpu`" — both need a MODIFIED delta changing the
assertion to the pod-level `gpu-memory` annotation shape with no `nvidia.com/gpu` limit.

## Validation plan (implementation-time, not yet run)

- Submit the updated template; confirm the resulting pod's annotations show `gpu-memory` and no
  `nvidia.com/gpu` limit (closes issue #25's first acceptance criterion).
- Submit 2 fractional predictor pods concurrently on the same physical GPU; confirm neither OOMs
  (closes the second acceptance criterion).
- Run the full four-stage DAG end-to-end to confirm nothing else broke.
- Verify `priorityClassName: interactive-preemptible` + `retryStrategy` still behave correctly
  under the fractional shape (an eviction mid-run should still retry as it does today).

## Out of scope

- The idempotency / skip-if-done gap (issue #37) — separate, already-tracked, in-progress
  cross-repo work, unrelated to GPU scheduling.
- Any change to which RunAI project (`talmo-lab` vs. `busch-lab`) Bloom submissions target — that
  decision is separate from this fix, which applies identically to either.
