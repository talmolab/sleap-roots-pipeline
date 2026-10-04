# Design: targeting the predictor's GPU slice at `main`

## Context

Bloom prod run `sleap-roots-pipeline-x68sv` (2026-10-02, 24 scans, `gpu-node7`) logged
`device=cpu` at about 2 fps. Its predictor pod spec, read 2026-10-02:

| container | `NVIDIA_VISIBLE_DEVICES` | RunAI GPU env and mounts |
|---|---|---|
| `wait` (argoexec, `spec.containers[0]`) | from ConfigMap `…-runai-sh-gpu-0`, key `RUNAI-VISIBLE-DEVICES` | `RUNAI_GPU_MEMORY_*`, `/etc/ld.so.preload`, `/etc/runai.d/*` |
| `main` (predict, `spec.containers[1]`) | literal `void` | none |
| `init` (initContainer) | literal `void` | none |

- **The cluster runs Run:ai 2.22.64** on Kubernetes v1.32.9 (`runai cluster list`). RunAI gives a
  pod's fractional GPU to the pod's first container. Choosing another container with the
  `gpu-fraction-container-name` annotation exists only "From cluster v2.24 onward"
  ([What's New 2.24](https://run-ai-docs.nvidia.com/self-hosted/2.24/getting-started/whats-new/whats-new-2-24)).
  The annotation-only fix was live-tested and ignored (tasks.md 3.1).
- **Argo v3.6.7** builds the pod by appending `wait` and then `main`
  (`workflow/controller/workflowpod.go` L219–226). It then applies template-level `podSpecPatch`
  with Kubernetes' `strategicpatch.StrategicMergePatch` (`workflow/util/util.go:1530`): the
  Workflow-level patch first, then the template-level one.
- **Likely origin:** #25's fix (PR #41, 2026-08-05) removed `nvidia.com/gpu: 1` from `main`. Until
  then the device plugin assigned the GPU to that container. PR #41 verified scheduling but not
  visibility inside the container: its task 4.3 records that exec was unavailable.

## Decision

1. **`podSpecPatch: '{"$setElementOrder/containers":[{"name":"main"},{"name":"wait"}]}'`** on the
   predictor template. `$setElementOrder` is a standard strategic-merge-patch directive, so `main`
   becomes `spec.containers[0]` and RunAI 2.22 gives it the slice.
2. **Keep `gpu-fraction-container-name: "main"`.** It does nothing on 2.22. From 2.24 it selects
   `main` by name, so the upgrade can't break the fix. Without it, 2.24 would still default to
   the first container, which is `main`, so the two mechanisms agree either way.

## Evidence

All runs are in tasks.md §3; each used one A40 slice of 8,192,000,000 bytes.

| test | what it covered | result |
|---|---|---|
| 3.1 | annotation only | **failed**: slice went to `wait`, `cuda False` |
| reorder probe | cheap probe of the reorder | `main` first and holds the slice; `cuda True`; out of memory at **7,488 MiB** usable; Workflow Succeeded and exitCode recorded |
| T1 | instant crash, then retry | `exitCode=1` recorded for a `main` that ran 1 s; the retry pod is also reordered and has CUDA |
| T2 | templateRef'd real predict; 8 canola scans, 2 models | `device=cuda`; 8/8 ok; 22–30 fps; counts match the CPU outputs |
| T3 | two predictors at once | same `runai-gpu-group`, overlapping run times, both 8/8 ok on CUDA |
| 3.7 | worst-case memory: all 8 catalog models resident, one 72-frame inference each | peak 2,843 MiB allocated / 4,350 MiB reserved, against 7,488 MiB usable; about 15–20 MiB per resident model |
| 3.6 | the probed template vs the committed one (offline) | parsed specs equal; identical `podSpecPatch` |

T1 covers a retry after failure. A retry after preemption or eviction is covered by construction,
not by test: every retry is a new pod built from the same template, so the same patch applies.

## Alternatives considered

- **Whole GPU: `nvidia.com/gpu: 1` on `main`.** Live-tested and working (`gpu-probe-117-whole`:
  a full A40 on `main`, `cuda True`), but it gives up fractional sharing, allowing one predictor
  per GPU. Kept as the **fallback** if the reorder ever breaks. It would be a separate fix PR:
  1. set `pipeline-gpu` to `"1"` in the live ConfigMap **and** in the yaml first;
  2. remove `gpu-memory`, `gpu-fraction-container-name` and the `podSpecPatch`;
  3. update `check_manifests.py` (its `gpu-memory`, `GPU_SLICE_*`, `podSpecPatch` and sidecar
     assertions), `check_docs.py` (which requires both GPU mechanisms in seven docs), and this
     requirement with its co-schedule scenario.
- **Annotation only.** Live-tested and ignored on 2.22. Kept alongside the reorder for ≥ 2.24.
- **Leave it on CPU and wait for the upgrade.** The results are correct, but it's about 10–15x
  slower, and each predictor holds an unused 0.18-GPU slice (up to 1.44 of the lab's 2-GPU quota
  across 8 slots). Rejected.

## Risks

- **The reorder could silently stop working.** If a future Argo version stopped applying
  `podSpecPatch` as a strategic merge, or ordered containers differently, `wait` would get the GPU
  again and predict would fall back to CPU without any error. `check_manifests.py` asserts that the
  patch is present, not what it does.
  - Mitigations: a re-probe after every Argo or Run:ai upgrade (task 7.3 and the template
    comment); the `device=` troubleshooting check in the runai skill and ci-debug; and predict's
    CPU-fallback guard (task 7.1).
- **CUDA out-of-memory under the slice: low.** 7,488 MiB is usable. Predict never evicts a loaded
  model (`sleap_roots_predict/warm_worker.py:70,138`), but probe 3.7 showed that a resident model
  costs only about 15–20 MiB. Peak memory is set by the largest single inference pass: 2,843 MiB
  allocated and 4,350 MiB reserved, with every catalog model resident, so the headroom is about
  1.7x in the worst case.
  - That probe used flat synthetic frames, and activation memory doesn't depend on image content.
  - The catalog has 8 cards today. A larger model added later would change the peak, so re-run
    3.7's probe when the registry grows.
  - Rollback trigger: task 6.4. The fix for an out-of-memory failure is a larger `gpu-memory`,
    with `pipeline-gpu`/`GPU_SLICE_*` retuned.
- **A malformed patch fails late.** Argo's `validate.go` never inspects `podSpecPatch`, so a broken
  patch passes `argo lint` and submit. It fails only when the pod is created ("Error applying
  PodSpecPatch"; the node Errors and no pod is created). `check_manifests.py`'s exact-value
  assertion is the only earlier gate.
- **Argo 4.1's init-less layout.** It is opt-in; the default `legacyLayout` is unaffected. It
  replaces `wait` with a `supervisor` container, still appended before `main`. Our
  `$setElementOrder` names `wait`, so `supervisor` would keep the first position and take the
  slice silently. Re-probe after any Argo upgrade (task 7.3), and confirm the init-less layout is
  off.
- **A future mutating webhook that inserts a container first**, such as a service-mesh proxy,
  would also take the slice. The same re-probe guards against it.
- **`main` now starts before `wait`.** T1 showed that an instant crash is still recorded.
- **Someone removes the patch as cosmetic.** Guarded by the "DO NOT remove" comment on it and by
  the `check_manifests.py` assertion.
- **A Workflow-level `podSpecPatch` is added later.** It would be applied before ours, and ours
  would still decide the order. Bloom has none today.
- **CPU and GPU results will coexist.** Scans already predicted on CPU are not recomputed:
  `device` is deliberately excluded from predict's idempotency key (`warm_worker.py:205-212`), so
  only scans that are new or otherwise changed run on GPU. Their outputs can differ slightly
  (T2: `scan_577` lateral has 524 instances on GPU against 523 on CPU). Each result records its
  inference `device`, so the two groups can be told apart. A forced recompute would need a
  separate decision.
- **Untested: more than two predictors on one GPU.** The accounting allows about 5 slices per
  A40, and slices share compute without isolation. T3 measured two; the 22–30 fps figure is for
  one or two per GPU.
- **The cluster is nearly full.** On 2026-10-03, 59 of 64 GPUs were allocated. That isn't caused
  by this change, but node-pinned probes can sit Unschedulable (T3's first attempt did).
