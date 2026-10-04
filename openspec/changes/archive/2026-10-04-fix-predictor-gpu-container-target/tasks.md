# Tasks: fix-predictor-gpu-container-target

**Status (2026-10-04).** Complete. PR #124 merged as `1615d5a`; the template was deployed
2026-10-04 03:06 UTC; the first prod run passed (6.3); follow-ups are filed (§7). This file is
archived by PR B.

**History.** §1–§2 and 3.1 implemented and tested the original annotation-only design. 3.1 showed
the annotation is ignored on this cluster (Run:ai 2.22.64), so §2R added the `podSpecPatch`
reorder. Where a ticked task's text predates that, it is marked *superseded*.

## Conventions

- **Checks** means running all three of these, each of which must exit 0:
  - `wsl -e bash scripts/lint_manifests.sh`
  - `uv run --with pyyaml python scripts/check_manifests.py`
  - `uv run --with pyyaml python scripts/check_docs.py`

  Run these from Git Bash or WSL, not PowerShell. Under PowerShell, `shutil.which("sh")` finds
  nothing, and `shutil.which("bash")` finds the WSL launcher (`C:\Windows\System32\bash.exe`), so
  `check_manifests.py`'s gate assertions run inside WSL and fail spuriously. This is pre-existing
  (task 7.4).
- **Identities** (see `docs/cluster-identities.md`). Run all of these inside WSL.
  - `argo-user` (`KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml`) registers
    templates and submits and deletes Workflows.
  - `bloom-pipeline` (`KUBECONFIG=~/.kube/kubeconfig-bloom-pipeline-busch-lab.yaml`) reads pod logs:
    `kubectl logs <pod> -c main`.
  - No identity can `kubectl exec` into an Argo step pod.
- **PRs.**
  - PR A covers §0–§5. Its body says "Part of #117", never `Fixes`.
  - PR B is the post-deploy PR, task 6.5.
  - Close #117 after PR B merges.
  - After PR A merges, run `/cleanup-merged` steps 1–4 only. Archiving happens in PR B.

## TDD order

This repo's test harness is `scripts/check_manifests.py` and `scripts/check_docs.py`. Every manifest
or doc edit below follows red → green → refactor:

1. write the failing assertion;
2. run it, and see it fail **for the right reason**, recording the output;
3. make the edit;
4. see the run go green;
5. clean up while it stays green.

Live behavior is the acceptance test. Its red baseline (task 0.1) is recorded before any fix, and §3
turns it green. Each red→green pair is one commit, with the red output in the commit body.

## 0. Red baseline (acceptance test, already observed)

- [x] 0.1 Record the failing live behavior in this file, from the x68sv evidence captured 2026-10-02:
  - **Pod spec** (`sleap-roots-pipeline-x68sv-predictor-3954024924`):
    - `wait` has `NVIDIA_VISIBLE_DEVICES` from ConfigMap `…-runai-sh-gpu-0`;
    - `main` and `init` have `void`.
  - **Log:** the two `Loaded inference model … device=cpu` lines from #117.

  Validate: the excerpt is pasted under this task. No cluster action is needed, because the pod is
  already read.

  Evidence (read 2026-10-02 with `kubectl get pod -o yaml` as `bloom-pipeline`; secrets omitted):
  ```yaml
  # pod annotations
  gpu-memory: "8192"
  received-resource-type: Fraction
  runai/shared-gpu-configmap: sleap-roots-pipeline-x68sv-jg7fhgv-runai-sh-gpu
  # spec.containers[0] (name: wait, image argoexec:v3.6.7)
  - name: NVIDIA_VISIBLE_DEVICES
    valueFrom: {configMapKeyRef: {key: RUNAI-VISIBLE-DEVICES, name: sleap-roots-pipeline-x68sv-jg7fhgv-runai-sh-gpu-0}}
  #   + RUNAI_GPU_MEMORY_LIMIT=8192000000, envFrom ...-runai-sh-gpu-0-evar,
  #     mounts /etc/ld.so.preload, /etc/runai.d/{memory,pod_uuid,route}, /runai/shared
  # spec.containers[1] (name: main, image sleap-roots-predict:sha-79939eec...)
  - name: NVIDIA_VISIBLE_DEVICES
    value: void
  # spec.initContainers[0] (name: init)
  - name: NVIDIA_VISIBLE_DEVICES
    value: void
  ```
  Predict log (from #117):
  ```
  2026-10-02 18:16:39 | Loaded inference model | type=bottomup | backbone=unet | nodes=4 | device=cpu | batch_size=4 | ...
  2026-10-02 18:16:44 | Loaded inference model | type=bottomup | backbone=unet | nodes=6 | device=cpu | batch_size=4 | ...
  ```

## 1. Manifest: assertions first (red)

- [x] 1.1 **Red.** In `scripts/check_manifests.py`, add assertions for every manifest clause of the
  scenario "Predictor requests a fractional GPU at the pod level":
  - `gpu-fraction-container-name` is `"main"`;
  - there is no `gpu-fraction` annotation;
  - neither `resources.limits` nor `resources.requests` contains `nvidia.com/gpu`;
  - `schedulerName` is `runai-scheduler`;
  - `securityContext` has neither `privileged: true` nor `runAsUser: 0`;
  - the template is a `container:` template (not `script` or `containerSet`) whose `container.name`
    is absent or `main`.

  Also update the script header's run line to `uv run --with pyyaml python scripts/check_manifests.py`.
  Run it against the **unchanged** template.
  Validate: it exits 1, and the **only** failing assertion is the `gpu-fraction-container-name` one.
  The other clauses already hold today. A different failure means the test is wrong, so fix it
  before going on. Record the output.

  Red, recorded 2026-10-02 (template unchanged):
  ```
  FAIL  predictor names main as its GPU-fraction container: got None, expected 'main'
  === 1 FAILED, 106 passed ===
  ```

## 2. Manifest: green, then refactor

- [x] 2.1 **Green.** In `sleap-roots-predictor-template.yaml`, add `gpu-fraction-container-name: "main"`
  to `spec.templates[predictor].metadata.annotations`, next to `gpu-memory: "8192"`. Write the comment
  beside it as the **canonical** explanation, which the other docs point to:
  - RunAI's default target is `spec.containers[0]`, which is Argo's `wait`;
  - every other container gets `NVIDIA_VISIBLE_DEVICES=void`;
  - this is #117.

  Validate: Checks pass. Commit 1.1 and 2.1 together, with the 1.1 red output in the commit body.

  Green, recorded 2026-10-02: `=== ALL 107 ASSERTIONS PASS ===`; `check_docs.py` reports all 38
  assertions passing; `lint_manifests.sh` reports `no linting errors found!`.
- [x] 2.2 **Refactor** (comments only; Checks stay green). Correct the template's false or dead
  comments. All of them are manifest facts; none claims runtime behavior.
  - "GPU is visible via device-plugin without privileged" (~L236);
  - "GPU comes from the gpu-memory annotation" (the `resources` comment, ~L248);
  - the three references to #25's design: L10 (a dead `openspec/changes/enable-predictor-gpu-fractions/`
    path), L21 and L243 (both an ambiguous "design.md"). Point all three at
    `openspec/changes/archive/2026-08-12-enable-predictor-gpu-fractions/design.md`.

  Validate: Checks pass, and
  `grep -n "visible via device-plugin\|changes/enable-predictor\|see design.md\|See design.md" sleap-roots-predictor-template.yaml`
  returns nothing.
- [x] 2.3 **Mutation checks**, not committed. Run the script against each of these temporary
  template edits, restoring the template after each one:
  - the annotation removed;
  - the annotation set to `"wait"`;
  - `container.name: predict` added;
  - `nvidia.com/gpu: 1` added to `limits`.

  Validate: each run exits 1 and names the right assertion, and `git diff` is clean afterwards.
  Paste the output into PR A's body.

  Recorded 2026-10-02 (the template was restored byte-for-byte after each run):
  ```
  annotation removed       FAIL  predictor names main as its GPU-fraction container: got None
  annotation = "wait"      FAIL  predictor names main as its GPU-fraction container: got 'wait'
  container.name: predict  FAIL  predictor container name is absent or main: got 'predict'
  nvidia.com/gpu: 1        FAIL  predictor requests no whole nvidia.com/gpu: got ['limits']
  ```

## 2R. Manifest: the reorder that works on Run:ai 2.22 (red → green)

Added 2026-10-03, after 3.1 showed the annotation alone is ignored on this cluster (2.22.64) and the
reorder suite in §3 passed.

- [x] 2.4 **Red.** In `check_manifests.py`, assert that the predictor's `podSpecPatch` parses as
  JSON and equals `{"$setElementOrder/containers":[{"name":"main"},{"name":"wait"}]}`.
  Validate: run against the template without the patch. Recorded 2026-10-03: exactly one failure,
  `FAIL  predictor podSpecPatch orders main before wait: got None …`, with
  `=== 1 FAILED, 107 passed ===`.
- [x] 2.5 **Green.** Add that `podSpecPatch` to the predictor template, and rewrite the canonical
  annotation comment so it says what's true:
  - the annotation needs Run:ai ≥ 2.24 and is kept for after the upgrade;
  - the `podSpecPatch` is what works today;
  - a "DO NOT remove as cosmetic" warning goes on the patch.

  Validate: Checks pass. Recorded: `=== ALL 108 ASSERTIONS PASS ===` from Git Bash,
  `lint_manifests.sh` reports no errors, and the template blob was `706f7068`. After the round-3
  comment rewording it is `a76960e1`: comments only, parsing equal.
- [x] 2.6 **Mutation checks**, not committed. Each mutation failed the new assertion, and the
  template was restored byte-for-byte afterwards:
  ```
  podSpecPatch removed   FAIL … got None
  order reversed         FAIL … got {'$setElementOrder/containers': [{'name': 'wait'}, {'name': 'main'}]}
  invalid JSON           FAIL … got 'unparseable: Expecting property name enclosed in double quotes …'
  ```

## 3. Live verification (needs explicit user approval; uses the shared busch-lab GPU quota)

Rules for every probe:

- **Pin the evidence to a template version.** Record `git rev-parse HEAD` and
  `git hash-object sleap-roots-predictor-template.yaml` alongside it. Any later commit that changes
  the predictor's `metadata`, `container` or `podSpecPatch` (anything beyond comments)
  invalidates §3. In that case, re-run the reorder probe and T2 from §3R, then 3.6's offline
  equivalence check.
- **Probe manifests** are throwaway files in the session scratchpad. Each one has a fixed name
  (delete the previous Workflow of the same name before a resubmit) and an `activeDeadlineSeconds`.
  Lint each with `wsl -e bash -c 'argo lint --offline <file>'` before submitting, and paste each
  into PR A's body.
- **Check quota before each submit.** List running GPU pods and their priorities:
  `kubectl get pods -n runai-busch-lab --field-selector=status.phase=Running -o custom-columns=NAME:.metadata.name,MEM:.metadata.annotations.gpu-memory,FRAC:.metadata.annotations.gpu-fraction,PRI:.spec.priorityClassName`.
  Also list non-pipeline workloads with `runai workload list -p busch-lab` (the WSL runai binary).
  Predictors use 8 × 0.18 = 1.44 GPU, which leaves at most 0.56 GPU for other non-preemptible work
  (`sleap-roots-pipeline-semaphores.yaml` header).
  - 3.1 and 3.1b run at `interactive-preemptible`, so they never take non-preemptible quota.
  - 3.2 and 3.3 keep the predictor's `pipeline-gpu` semaphore, so they queue behind prod rather
    than exceed the quota.

### Tasks

How these were actually run: 3.1 ran as written and FAILED, because the annotation is ignored on
2.22, which triggered 3.5. 3.1b, 3.2, 3.3 and 3.4 then ran as the reorder suite (T1, T2, T3 and
cleanup; evidence under 3.1). T2 and T3 used a separately registered copy of the template driven by
`templateRef`, in place of inlining, which tests the path Bloom uses. 3.6 re-tests the final
committed template.

- [x] 3.1 **Cheap probe: GPU visibility and the real memory ceiling.** Submit Workflow
  `gpu-probe-117-a`:
  - one step, with `serviceAccountName: bloom-workflow`;
  - the predictor's pinned image and the same pod annotations and `schedulerName`;
  - `priorityClassName: interactive-preemptible`;
  - no `retryStrategy`, no volumes, no secrets;
  - `activeDeadlineSeconds: 900`.

  Use `command:` rather than `args:`, because the image ENTRYPOINT is
  `python -m sleap_roots_predict`; `python` is on PATH via `/app/.venv/bin`. The command is
  `[python, -c, <script>]`, with this script:
  ```python
  import os, sys, time, torch
  print("NVIDIA_VISIBLE_DEVICES", os.environ.get("NVIDIA_VISIBLE_DEVICES"))
  print("RUNAI_GPU_MEMORY_LIMIT", os.environ.get("RUNAI_GPU_MEMORY_LIMIT"))
  ok = torch.cuda.is_available(); print("cuda", ok, flush=True)
  if not ok: sys.exit(2)
  print("device", torch.cuda.get_device_name(0), flush=True)
  time.sleep(90)  # window to read the Running pod's spec and annotations
  bufs, mib = [], 0
  try:
      while mib < 16384:
          bufs.append(torch.empty(64 * 2**20, dtype=torch.uint8, device="cuda")); mib += 64
      print("NO LIMIT up to 16384 MiB"); sys.exit(3)
  except torch.OutOfMemoryError:
      print("OOM enforced after", mib, "MiB"); sys.exit(0)
  ```

  Validate. Record the following here.
  - **While the pod is Running:**
    - `main`'s `NVIDIA_VISIBLE_DEVICES` is a `configMapKeyRef` to `…-runai-sh-gpu-1`, and `main`
      carries `RUNAI_GPU_MEMORY_LIMIT` and `/etc/ld.so.preload`;
    - `wait` is `void`;
    - the `runai-allocated-gpu-memory` annotation;
    - `init`'s value, as an observation only.
  - **Log:** `cuda True`, then `OOM enforced after <N> MiB`, with exit 0. N is the real usable
    ceiling, CUDA context excluded. Record it, and compare it with the 7,813 and 8,192 MiB
    candidates.
  - **Other outcomes go to 3.5:**
    - exit 2 means no GPU;
    - exit 3 means no enforcement, which matters for co-tenant risk;
    - any other non-zero exit means the limiter killed the process or the preload broke Python.
  **Result, 2026-10-02: FAILED. The annotation is ignored on this cluster.** Template pin
  `HEAD=a1f83c2` (local tag `backup/117-annotation-only`; the same template blob is in this branch's annotation commit), blob `ee5676b6`. Workflow `gpu-probe-117-a` landed on `gpu-node7` and Failed after
  20 s.
  - The pod **carries** `gpu-fraction-container-name: main` and `gpu-memory: "8192"`, and
    `received-resource-type: Fraction`.
  - RunAI still mutated `spec.containers[0]`, which is `wait`. It got `NVIDIA_VISIBLE_DEVICES` from
    ConfigMap `gpu-probe-117-a-b5x9d8k-runai-sh-gpu-0`, plus the `-0-evar` envFrom and the `-0-vol`
    mounts.
  - `main` and `init` both have `NVIDIA_VISIBLE_DEVICES: void`.
  - `main`'s log reads `NVIDIA_VISIBLE_DEVICES void`, `RUNAI_GPU_MEMORY_LIMIT None`, `cuda False`,
    with exit 2.

  The probe Workflow is deleted, and no probe ConfigMaps are left. The local RunAI CLI is
  `runai-cli/2.26.24`; the cluster's control-plane version is unknown, and documentation for the
  CLI version does not establish what the server supports. Per 3.5: stopped, nothing registered.
  The design premise is falsified, so the proposal must be revised before going any further.

  Follow-up findings and the reorder suite are in §3R.

- [x] 3.1b *Superseded: ran as T1 under the reorder, see §3R. Under the reorder the ConfigMap
  is `-gpu-0`, not `-gpu-1` as written below.* **Retry after failure.** Run 3.1's Workflow as `gpu-probe-117-a-retry`, with these
  changes:
  - `retryStrategy: {limit: 1, retryPolicy: Always}`;
  - env `ATTEMPT: "{{retries}}"`;
  - a script that runs `sys.exit(1)` when `ATTEMPT == "0"`, and otherwise prints
    `torch.cuda.is_available()` and allocates 1 GiB.

  Validate: two pods. The second pod's `main` references `…-runai-sh-gpu-1` and logs `cuda True`.
  This covers a retry after a failure, not after preemption or eviction: `argo-user` cannot delete
  pods.
- [x] 3.2 *Superseded: ran as T2 (`gpu-probe-117-b`, driven by templateRef, 2 models), see §3R;
  worst-case memory is covered by 3.7.* **Full predict on a batch.**
  1. On NFS (Z:), create `/hpi/hpi_dev/users/eberrigan/pipeline_orchestration_tests/gpu_probe_117/`,
     with `input/` and `predictions/` sub-directories. Give `predictions/` the same owner and mode
     as `a4_poc/predictions`.
  2. Pick the scans:
     - read every `*.scan_metadata.json` under `a4_poc/input`;
     - group them by (species, imaging mode), and spread the ages within each group;
     - take one scan per group (T2 used 8);
     - list the chosen `scan_key`s and the models predict resolves for them.
  3. Copy each chosen scan's sidecar and frames into `input/`. Treat `a4_poc` as read-only.
  4. Write `input/run_manifest.gpu-probe-117-b.json` in the contracts `RunManifest` shape:
     `{"schema_version": "1", "pipeline_run_id": "gpu-probe-117-b", "scan_keys": [...]}`.
     Confirm the field names against `sleap-roots-contracts`' `RunManifest` before writing.
     `pipeline_run_id` must equal the Workflow name, or predict exits 1.
  5. Submit Workflow `gpu-probe-117-b`:
     - `serviceAccountName: bloom-workflow` and `activeDeadlineSeconds: 3600`;
     - the edited predictor template **inlined unchanged**, which keeps the `pipeline-gpu`
       semaphore, `priorityClassName: high`, `retryStrategy`, the `WANDB_API_KEY` secret env and
       `ARGO_WORKFLOW_NAME`;
     - its two hostPath volumes pointed at the probe directories.

  Empty `predictions/` before any resubmit, or every scan is skipped and the evidence is vacuous.

  Validate. Record here:
  - every chosen scan has a `{scan_key}.predictions.json`;
  - one sleap-nn "Loaded inference model" line per distinct model, each with `device=cuda`. That
    line comes from sleap-nn (`inference/predictor.py`), not predict. Quote it exactly.
  - the number of distinct models, the per-scan timings, no CUDA out-of-memory error, and exit 0.

  Peak GPU memory can't be read without exec. A clean run on the batch with the most models
  available is the evidence.
- [x] 3.3 *Superseded: ran as T3 (`gpu-probe-117-e`/`-f` on `gpu-node2`), see §3R.* **Two
  concurrent pods on one GPU.** Run 3.2's setup as two Workflows, `gpu-probe-117-c`
  and `gpu-probe-117-d`:
  - each with its own `run_manifest.gpu-probe-117-{c,d}.json` (same scans) in the shared `input/`;
  - each writing to its own `predictions-c/` or `predictions-d/`;
  - both with `nodeSelector` set to the same node.

  Validate:
  - both pods carry the same `runai-gpu-group`. If they don't, record "not exercised" and resubmit;
    never mark it passed.
  - the `main` containers' `startedAt`/`finishedAt` intervals overlap;
  - both exit 0 with `device=cuda` and no CUDA out-of-memory error.
- [x] 3.4 Clean up as `argo-user`: delete every `gpu-probe-117-*` Workflow, then the
  `gpu_probe_117` directory.
  Validate: `argo list -n runai-busch-lab | grep gpu-probe-117` is empty, and the directory is gone.
- [x] 3.5 **If any probe fails:** stop. Register nothing. Report the pod spec and logs to the user,
  and decide between:
  - escalating to the cluster admins;
  - raising `gpu-memory`, for an out-of-memory failure;
  - the whole-GPU fallback in design.md.

- [x] 3.6 **Final template equals the probed template (offline).** T2 and T3 ran a copy of the
  annotation-only template (blob `ee5676b6`) with the `podSpecPatch` added. Load that copy
  (`probe117-template.yaml`, sha256 `ce7ce852…`) and the committed template (blob `706f7068`; the shipped blob is `a76960e1`, a comment-only
  rewording that parses equal, re-checked 2026-10-03) with
  `yaml.safe_load`, drop the probe-only `metadata.name` and the `metadata.annotations.probe`, and
  compare.
  Validate: recorded 2026-10-03, `probed spec == committed spec: True` and
  `podSpecPatch identical: True`. No cluster run is needed, so the live evidence in §3R applies to
  the shipped template.
- [x] 3.7 **Worst-case GPU memory (all catalog models).** Run Workflow `gpu-probe-117-models` on
  `interactive-preemptible`, with no data or volumes and with `WANDB_API_KEY`. It loads every card
  in the production catalog into one `WarmModelWorker`, which is more than any batch can resolve,
  and runs one inference per model on a synthetic 72-frame 1080x2048 video.
  Validate: recorded 2026-10-03, PASS.
  - `main` was first and held `…-runai-sh-gpu-0`; `wait` and `init` had `void`; exitCode=0.
  - 8 catalog cards, all 8 resident, everything on CUDA.
  - After card 5, 802 MiB peak allocated. From card 6 (`canola-lateral-240611_083419`), the peak
    was 2,843 MiB allocated and 4,350 MiB reserved, and it stayed there. 133 MiB allocated with
    all 8 resident means about 15–20 MiB per model.
  - The peak is set by the largest single inference pass, not by the model count. Headroom against
    7,488 MiB usable is about 1.7x. The frames were flat synthetic images, so 0 instances were
    detected; activation memory doesn't depend on content. The Workflow was deleted afterwards.

### 3R. Live results (evidence for §3)

  **Follow-up findings, 2026-10-03:**
  - **Cluster version.** `runai cluster list` reports cluster `salk` on **Run:ai 2.22.64**, with
    Kubernetes v1.32.9. The `gpu-fraction-container-name` annotation exists only "From cluster
    v2.24 onward" ([What's New 2.24](https://run-ai-docs.nvidia.com/self-hosted/2.24/getting-started/whats-new/whats-new-2-24)),
    which explains 3.1's failure.
  - **Probe `gpu-probe-117-whole`: PASS.** Setup: `nvidia.com/gpu: 1` on `main`, no fraction
    annotations, `interactive-preemptible`. The pod got `received-resource-type: Regular` and
    `runai-allocated-gpus: "1"` on `node35` (a first-time image pull took about 2.5 min). `main`'s
    log: `NVIDIA_VISIBLE_DEVICES GPU-6d5ad5f8-…`, `cuda True`, `device NVIDIA A40`, then
    `NO LIMIT up to 16384 MiB`, with exit 3 as expected (a whole GPU has no RunAI cap). Deleted.
  - **Probe `gpu-probe-117-reorder`: PASS.** Setup: `gpu-memory: "8192"` plus a template-level
    `podSpecPatch: '{"$setElementOrder/containers":[{"name":"main"},{"name":"wait"}]}'`, no
    container-name annotation, `interactive-preemptible`.
    - The pod's `spec.containers` order became `main`, then `wait`.
    - RunAI 2.22 mutated `main`, giving it `NVIDIA_VISIBLE_DEVICES` from ConfigMap
      `gpu-probe-117-reorder-qpzswj8-runai-sh-gpu-0`; `wait` has `void`.
    - `main`'s log: `NVIDIA_VISIBLE_DEVICES GPU-45ec24db-…`, `RUNAI_GPU_MEMORY_LIMIT 8192000000`,
      `cuda True`, `device NVIDIA A40`, `OOM enforced after 7488 MiB`, exit 0.
    - The Workflow reached `Succeeded`, and the node recorded `outputs.exitCode=0`, so the
      reordered `wait` still reports the exit code the gate reads.
    - Usable ceiling: **7,488 MiB** of tensor memory under the 8,192,000,000-byte (7,813 MiB)
      limit, the difference being the CUDA context. That is about 1.6x the 4,676 MiB measured
      peak.

    Deleted.

  **Reorder-mechanism suite, 2026-10-03.** Every probe used the reorder `podSpecPatch` above, and
  all of them passed. Pin: `HEAD=a1f83c2` (local tag `backup/117-annotation-only`; the same template blob is in this branch's annotation commit), template blob `ee5676b6`. T2 and T3 ran that committed
  template plus the `podSpecPatch`, registered as a separately named WorkflowTemplate
  `sleap-roots-predictor-template-probe117` and driven by `templateRef`, the way Bloom drives it,
  with the real `pipeline-gpu` semaphore, `priorityClassName: high` and `retryStrategy`. The
  template still carries `gpu-fraction-container-name`, which 2.22 ignores.
  - **T1, `gpu-probe-117-retry`: crash then retry. PASS.** `retryStrategy {limit: 1}`.
    - Attempt 0 exited 1 at once: `main` ran 18:18:08–18:18:09. The node still recorded
      `exitCode=1`.
    - Attempt 1 recorded `exitCode=0` and logged `cuda True`, `1GiB ok NVIDIA A40`.
    - Both pods were ordered `main`, `wait`, and each `main` got its own `…-runai-sh-gpu-0`
      ConfigMap; `wait` and `init` had `void`.
    - The Workflow Succeeded. This covers the retry scenario for retry-after-failure.
  - **T2, `gpu-probe-117-b`: real predict. PASS.**
    - Input: 8 canola cylinder scans covering ages 2, 3, 5, 6, 7, 9, 10 and 11 (three of them
      72-frame), copied read-only from `a4_poc`.
    - The pod ran on `gpu-node7` with `runai-allocated-gpu-memory: 8192`.
    - Two distinct models loaded, both `Loaded inference model | … | device=cuda` (sleap-nn
      log line), with `nodes=6` and `nodes=3`.
    - `Batch complete: 8 ok, 0 skipped, 0 failed`, 8/8 `*.predictions.json` written, exitCode=0,
      and no out-of-memory error or traceback.
    - Throughput was 22–30 fps (2.4–3.1 s per 72-frame pass), against about 2 fps on CPU for x68sv.
    - Parity with the earlier CPU outputs in `a4_poc/predictions`, spot-checked on 4 of the 8
      scans: frame and instance counts are identical for `scan_289`, `scan_1009` and
      `scan_12894746`. `scan_577` lateral has 524
      instances on GPU against 523 on CPU, which is expected floating-point variation.
    - The log line `frames=0` for `scan_289` lateral is real and matches CPU: the scan is age 2,
      with no laterals.
    - **Limit:** `a4_poc` holds only canola cylinder data, so this batch loaded 2 models. The
      worst-case multi-species batch, the main out-of-memory risk, is **not** exercised.
  - **T3, `gpu-probe-117-e` + `gpu-probe-117-f`: two predictors on one GPU. PASS.**
    - Both were pinned to `gpu-node2`, and both pods carry the same
      `runai-gpu-group bb9ea3dd-65f2-4a6a-949d-ae80715e1b1c`.
    - Their `main` containers overlapped: 18:43:26–18:45:32 and 18:43:27–18:45:29.
    - Both logged `device=cuda` for both models, `8 ok, 0 skipped, 0 failed`, exitCode=0, and no
      out-of-memory error.
    - Not a pass on the first attempt, and not caused by the reorder: `-c` and `-d` were
      submitted together, both pinned to `gpu-node7`. `-c` ran, but `-d` stayed
      `Unschedulable: no nodes with enough resources`, because `runai node list` showed
      `gpu-node7` at 4/4 and the cluster at 59/64 GPUs allocated. `-d` was deleted, and the test
      was rerun staggered on `gpu-node2`.
  - Cleanup: all `gpu-probe-117-*` Workflows and the probe117 template are deleted, the
    `gpu_probe_117` NFS directory is removed, and `a4_poc` is untouched (22 scans).


## 4. Docs

Each place gets a single sentence pointing to the template comment. Write them as manifest facts
("the template names `main`"), not runtime claims. 4.0 is the red step for 4.1–4.4, and the doc edits
go in one commit with it.

- [x] 4.0 **Red.** In `scripts/check_docs.py`, add regression assertions:
  - `README.md` does not contain "GPU access comes entirely from the";
  - `README.md`, `.claude/skills/runai/SKILL.md`, `openspec/project.md` and the four
    `.claude/commands` files in 4.3 each contain `gpu-fraction-container-name`;
  - no `.claude/commands` file contains "`nvidia.com/gpu` on the predictor step only".

  Run it before any doc edit.
  Validate: it exits 1, failing only on those assertions, and every pre-existing assertion still
  passes. Record the output. 4.1–4.4 then turn it green.

  Red, recorded 2026-10-02 (before any doc edit): `=== 9 FAILED, 38 passed ===`. The failures were
  the README "comes entirely from the" check, the annotation missing from all seven docs, and the
  stale checklist in `review-openspec.md` and `review-pr.md`. The first version of the stale-
  checklist assertion matched only `review-openspec.md`'s wording and missed `review-pr.md`'s two
  variants, so it was widened to a regex before the green edits. Green: `=== ALL 47 ASSERTIONS
  PASS ===`.

- [x] 4.1 `README.md`:
  - L247-249: "uses a RunAI pod-level `gpu-memory` annotation";
  - the annotation block at L352-364: add `gpu-fraction-container-name`;
  - L377-380: "GPU access comes entirely from…".

  Validate: `grep -n gpu-fraction-container-name README.md` hits all three, and the matching 4.0
  assertions pass.
- [x] 4.2 `.claude/skills/runai/SKILL.md`:
  - §4 (L108-115): add the annotation;
  - §8 Troubleshooting: add "predictor slow → `kubectl logs <pod> -c main | grep device=`".

  Validate: `grep -n gpu-fraction-container-name .claude/skills/runai/SKILL.md` hits in §4, and
  `grep -n "grep device=" .claude/skills/runai/SKILL.md` hits in §8.
- [x] 4.3 *Partly superseded by 4.6, which adds the `podSpecPatch` wording.* `.claude/commands/`:
  - `ci-debug.md:45` ("Predictor OOM / no GPU"): add the cause "`device=cpu` / `main` has
    `NVIDIA_VISIBLE_DEVICES=void`", with the fix `gpu-fraction-container-name: main`;
  - `review-pr.md:28,124` and `review-openspec.md:163`: replace "`gpu-fraction`; `nvidia.com/gpu`
    on the predictor step only" with "`gpu-memory` + `gpu-fraction-container-name: main`, no
    `nvidia.com/gpu`";
  - `docs-review.md:143`: add the annotation next to `gpu-memory`.

  Parallel-work note: a separate worktree is standardizing `.claude/commands` (it restores TDD to
  `new-feature`). Whichever lands second rebases, and keeps both sets of edits.
  Validate: `check_docs.py`'s 4.0 assertions for these files pass.
- [x] 4.4 `openspec/project.md`:
  - L35: add the annotation;
  - L40: qualify "`nvidia.com/gpu` resource limits" as local WSL2 only.

  Validate: `check_docs.py` exits 0, so 4.0 is green, and Checks pass. Commit 4.0–4.4 together, with
  the 4.0 red output in the commit body.
- [x] 4.5 Claim sweep. Grep the whole repo except `.worktrees/`, `openspec/changes/archive/` and
  `docs/bloom-integration/roadmap.md` (the roadmap goes in PR B, task 6.5), using:
  `grep -rn "GPU inference\|GPU pass\|warm GPU\|on GPU\|device-plugin\|share one physical GPU\|co-schedul\|GPU is visible"`.

  Decide each hit with this rule:
  - **leave design intent**, such as "warm GPU pod" or "predict-first runs GPU inference on
    past-window scans", which describes an ordering hazard and is true once the fix is live;
  - **correct claims about observed behavior**, such as "GPU was used" or "verified", with a dated
    note.

  Known hits to leave: template L179, L183; `sleap-roots-trait-extractor-template.yaml:59`;
  `README.md:361`; the 2026-07-06 A4 design.
  Validate: the grep command and the disposition of every hit are in PR A's body.

  Run 2026-10-02, excluding `.claude/worktrees/` too, because a parallel worktree lives there. No
  hit needs correcting:
  - A4 design (2026-07-06) L62 and L136, "warm GPU pod": design intent. Leave.
  - `openspec/specs/per-batch-pipeline/spec.md:42`, the co-schedule scenario title: scheduling, as
    verified by #25; this change's delta adds its CUDA OOM clause. Leave.
  - `README.md:239`, "device-plugin": the local WSL2 template, which is true. Leave.
  - `README.md:363`, "share one physical GPU": scheduling, verified by the `runai-gpu-group` match.
    Leave.
  - Predictor template L189 and L193, and `sleap-roots-trait-extractor-template.yaml:59`: the
    ordering hazard, design intent. Leave.
- [x] 4.6 **Reorder docs, red → green.** First, add `check_docs.py` assertions:
  - all seven GPU docs name the `podSpecPatch` reorder;
  - README no longer claims the annotation alone "direct[s] it to the predict container".

  Red, recorded 2026-10-03: `=== 8 FAILED, 47 passed ===`. Then reword README, the skill (§4 and
  the §8 troubleshooting row), `project.md`, `ci-debug` (the "runs on CPU" row now points at the
  `podSpecPatch` and a re-probe) and the three reviewer checklists. Each says the annotation takes
  effect only from Run:ai 2.24.
  Green: `=== ALL 55 ASSERTIONS PASS ===`.

## 5. Pre-merge sweep

- [x] 5.1 Run Checks, then `openspec validate fix-predictor-gpu-container-target --strict`.
  Validate: everything exits 0.
- [x] 5.2 Run `git fetch && git diff --stat origin/main...HEAD`.
  Validate, by manual comparison: the list holds only proposal.md Impact's files and the change
  folder. 3.6's equivalence check still holds for the head template: re-run it if the template's
  `metadata`, `container` or `podSpecPatch` changed after 3.6.
- [x] 5.3 Rebase onto `origin/main`, which has PR #121's `.claude/commands` standardization and
  #122, then re-run Checks.
  Validate: the rebase is conflict-free (a trial `git merge-tree` showed none), and all Checks pass,
  including `check_docs.py`'s `podSpecPatch` and annotation assertions over the rebased command
  files.

  Recorded 2026-10-03: rebased onto `origin/main` `7ba5b65`, with #121 and #122 included. All 7 doc
  edits applied cleanly in a three-way merge. `check_all.sh` passes at each of the 4 commits;
  `lint_manifests.sh` reports no errors; `openspec validate --strict` passes. That run covered the
  first 4 commits; the PR's /review-pr pass re-ran `check_all` at all 5. The diff against
  `origin/main` is 14 files: the change folder plus the Impact list. The rebuilt template and
  check scripts are byte-identical to the pre-rewrite snapshot, so 3.6 still holds.

## 6. Deploy (needs explicit user approval)

- [x] 6.1 **Before merging PR A**, record the rollback ref.
  - Run `git fetch` and note `origin/main`'s sha.
  - From a worktree checked out at that sha, run `wsl -e bash scripts/check_cluster_drift.sh`.
  - Write "rollback ref: `<sha>`" in PR A's body.

  Validate: the drift check reports every template IN SYNC, which proves the live cluster equals
  the rollback ref.

  Recorded: rollback ref `7ba5b65`, the merge-base, written in PR #124's body. The drift check was
  **not** run from a `7ba5b65` worktree before merge. Instead, it ran from merged `main`
  (`1615d5a`) just before 6.2, and reported only `sleap-roots-predictor-template` as DRIFT. Its
  diff was exactly the annotation and `podSpecPatch` lines; the other four templates and the
  semaphore ConfigMap were IN SYNC. Since `1615d5a` changes only that template from `7ba5b65`, the
  live cluster matched the rollback ref.
- [x] 6.2 **After merge**, from merged `main`:
  1. run `check_cluster_drift.sh`, and expect only the predictor to show DRIFT;
  2. register only this template:
     `wsl -e bash -c 'export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; argo template update /mnt/c/repos/sleap-roots-pipeline/sleap-roots-predictor-template.yaml -n runai-busch-lab'`.
     Never use `runai_run_pipeline.sh`: it re-registers all five templates and then submits a
     Workflow.

  Workflows already running keep their stored template, so no drain is needed.
  Validate: `check_cluster_drift.sh` reports everything IN SYNC.

  Recorded: registered 2026-10-04 03:06 UTC from `main` `1615d5a`, as `argo-user`. Afterwards the
  drift check printed `cluster is IN SYNC with the repo`, and `argo template get` showed
  `gpu-fraction-container-name: main`, `gpu-memory: "8192"` and the `podSpecPatch`.
- [x] 6.3 On the first Bloom Workflow **submitted after 6.2** that predicts at least one scan,
  record in #117:
  - the Workflow name;
  - that the pod's `spec.containers[0].name` is `main`;
  - that `main`'s `NVIDIA_VISIBLE_DEVICES` is a `configMapKeyRef` to `…-runai-sh-gpu-0`, and that
    `wait` is `void`;
  - `runai-allocated-gpu-memory`, and the node's `outputs.exitCode`;
  - the sleap-nn `device=` lines, and the number and species of the distinct models in the batch;
  - that there is no CUDA out-of-memory error;
  - for any retried predictor pod, the same container-order and `void` checks.

  Validate: the #117 comment shows `main` first, a `configMapKeyRef` for `main`, and `device=cuda`
  for every model. If any of those is missing, go to 6.4.

  Recorded: PASS on `sleap-roots-pipeline-cqc5b`, Bloom cyl-pipeline run 3, submitted 2026-10-04
  ~17:13 UTC. Posted to #117 (issuecomment-5982615497).
  - The predictor pod ran on `gpu-node7` with `received-resource-type: Fraction`.
  - `spec.containers[0]` was `main`, with `NVIDIA_VISIBLE_DEVICES` from
    `sleap-roots-pipeline-cqc5b-wztb7ss-runai-sh-gpu-0`; `wait` and `init` had `void`.
  - `runai-allocated-gpu-memory` read `0` on the completed pod; it was not captured while Running.
  - Two models, `nodes=4` and `nodes=6`, both `device=cuda`. These are the same two models x68sv
    ran on CPU. Species are not recorded here.
  - `Batch complete: 3 ok, 0 skipped, 0 failed`; no CUDA out-of-memory error; no retries.
  - Each 72-frame pass took 3.2–6.2 s.
  - All five stages Succeeded with `exitCode=0`, the exit gate included.
- [x] 6.4 **Rollback.**
  - Roll back when any of these happens:
    - predict hits a CUDA out-of-memory error;
    - predictor nodes Error with "Error applying PodSpecPatch", or never create a pod;
    - predictor pods fail admission or stay Pending because of the annotation or the
      `podSpecPatch`;
    - the exit code isn't recorded, or the Workflow hangs after `main` exits (the reordered `wait`
      regressed).
  - Do **not** roll back on `device=cpu`. The rollback ref is also CPU, so rolling back would fix
    nothing. Leave the template deployed, then go to 3.5 and the whole-GPU fallback in design.md.
  - Rollback command:
    `git show <rollback-sha>:sleap-roots-predictor-template.yaml > /tmp/pred-rollback.yaml`, then
    `argo template update /tmp/pred-rollback.yaml -n runai-busch-lab` (argo-user, in WSL).

  Validate: `argo template get sleap-roots-predictor-template -n runai-busch-lab -o yaml | grep -E 'gpu-fraction-container-name|podSpecPatch'`
  returns nothing. The drift check shows the predictor as DRIFT until a revert PR lands. If the
  rollback isn't needed, mark this task N/A.

  N/A: 6.3 passed and no trigger fired.
- [x] 6.5 **PR B**, only if 6.4 did not fire, titled
  `docs: record #117 deploy and roadmap; archive fix-predictor-gpu-container-target`. It contains:
  - the evidence from 6.1–6.4 in this file;
  - 7.1's issue URL;
  - a dated roadmap entry with the root cause and the evidence from §3 and 6.3;
  - correction markers on the 2026-08-05 #25 entry's "Live-cluster validated" sentence (L2475),
    and on the L940, L971 and L2164 GPU wording, decided by 4.5's rule;
  - `openspec archive fix-predictor-gpu-container-target --yes`, then `git add -A`.

  Validate: `openspec validate --specs --strict` exits 0, and
  `grep -c '\- \[ \]' openspec/changes/archive/*fix-predictor-gpu-container-target/tasks.md`
  returns 0.

  Done on branch `docs/roadmap-117-deployed`:
  - a 2026-10-04 status-log entry and a clause in the frontier paragraph;
  - a dated correction on the #25 entry's "Live-cluster validated";
  - markers on the 2026-10-02 "now gets a GPU pass" sentence and on the parity-run note, which
    were observed-behavior claims that ran on CPU at the time.

  Left unchanged by 4.5's rule, because they describe design intent or hazards that are true once
  the fix is live: "past-window scans run GPU inference" (an ordering hazard) and "uninterruptible
  GPU inference" (SIGTERM design). The line numbers in this task predate #122 and #125.

## 7. Follow-up (before 6.5)

- [x] 7.1 File the CPU-fallback guard in `sleap-roots-predict`: warn, or fail behind a flag, when
  `device="auto"` resolves to `cpu` while `NVIDIA_VISIBLE_DEVICES` is set and is not `void`. Link
  it from #117.
  Validate: record the issue URL here.

  Filed: https://github.com/talmolab/sleap-roots-predict/issues/52
- [x] 7.2 Send the cluster admins the drafted note. It covers the cluster version (2.22.64), the
  probe results, the reorder now in use, a request for the timeline to upgrade to Run:ai ≥ 2.24,
  and whether they object to the reorder.
  Validate: record the date sent and the reply here.

  Sent 2026-10-04 by the repo owner. It includes the corrected `init` + `spec.containers` wording
  and the first prod run. The reply is pending and will be tracked on #127, which owns the
  post-upgrade decision.
- [x] 7.3 File a follow-up issue covering upgrades:
  - after any Argo or Run:ai upgrade, re-run the reorder probe from §3R (and, for Argo ≥ 4.1,
    confirm the init-less `supervisor` layout is off);
  - once the cluster runs Run:ai ≥ 2.24, re-run it with the reorder removed to confirm the
    annotation alone works, then decide whether to drop the `podSpecPatch`;
  - re-run 3.7 whenever a model is added to the registry.

  Validate: record the issue URL here.

  Filed: https://github.com/talmolab/sleap-roots-pipeline/issues/127
- [x] 7.4 File an issue: under PowerShell, `check_manifests.py` picks the WSL `bash.exe` launcher
  (`shutil.which`). The fix is to prefer Git-for-Windows bash, or to fail loudly on a `System32`
  path.
  Validate: record the issue URL here.

  Filed: https://github.com/talmolab/sleap-roots-pipeline/issues/128
