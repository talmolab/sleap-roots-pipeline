# A4 Argo Workflow — predict→traits PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **This repo is declarative Argo/RunAI YAML — there is no pytest; a task's "test" is `argo lint`, a WSL2 dry-run, or a real cluster submit.** Pairs with an OpenSpec change per `/new-feature`.

**Goal:** A per-scan Argo workflow that runs **warm-predict → traits** end-to-end on the RunAI cluster over a pre-staged reference scan on `/hpi/hpi_dev`, submitted directly from an internal machine (no Bloom, no Tailscale), producing valid `{scan_key}.result.json` `ResultEnvelope`s on the shared mount.

**Architecture:** Rewrite the existing 3-stage `models-downloader → predictor → trait-extractor` Workflow into a 2-stage `predictor(warm) → trait-extractor` DAG that consumes two new GHCR producer containers, dropping the models-downloader (models now load in-process from the wandb registry). Storage stays hostPath-on-`/hpi/hpi_dev` (shared across GPU nodes). Write-back, batching/fan-out, dedup, resume-hardening, automated stage-in, and notify are **later slices**.

**Tech Stack:** Argo Workflows YAML, RunAI (`runai-talmo-lab`), GHCR images, `argo` CLI, WSL2 local dry-run.

## Global Constraints
- Namespace `runai-talmo-lab`; label `project: talmo-lab`. **Submit path (corrected at run time):** the `runai_run_pipeline.sh` launcher needs the in-cluster Argo Server `gpu-master:8888` + `ARGO_TOKEN` (unreachable from operator boxes), so the PoC submitted in **Kubernetes mode** via the argo-user kubeconfig (`argo submit … -n runai-talmo-lab`).
- Shared storage is hostPath onto `/hpi/hpi_dev/...` (node-independent NFS). Keep cluster (`*.yaml`) and local (`local-WSL2-*.yaml`) variants in sync.
- Producers are **filesystem-only**. Predict needs `WANDB_API_KEY`. Keep `securityContext {privileged: true, runAsUser: 0}` and RunAI annotations (`gpu-fraction`, `preemptible`) as in the current templates.
- Pin producer images by immutable `sha-<sha>`/digest tag (not `latest`) — per the A4 design's per-run pin requirement.

## Container interface contracts (consumed — defined here, satisfied by the producer slices)
- **Predict** (predict #27, `ghcr.io/talmolab/sleap-roots-predict:sha-4a70e59978cffbf2b144b5b20cb08f8d12ef633f`): `docker run <predict-image> <in_scan_dir> <out_dir>`, env `WANDB_API_KEY`; loads models once. **Input = a nested tree** `{scan_key}/<frames>` + `{scan_key}.scan_metadata.json` (sidecar authored by stage-in, not predict). Per scan writes `<out_dir>/{scan_key}/{scan_key}.predictions.json` + named per-root `.slp` **and copies the sidecar verbatim forward** into `out/{scan_key}/` (**D1** — makes predict's output a self-contained trait-extractor input tree); GPU. Bakes `SRP_PREDICT_CODE_SHA` → `predict_code_sha`.
- **Traits** (sleap-roots #257, `ghcr.io/talmolab/sleap-roots-trait-extractor:sha-bb2199c`): `docker run <traits-image> <in_dir> <out_dir>` (ENTRYPOINT `["python","-m","trait_extractor"]` baked → args are the two dirs only); reads predict's `out/{scan_key}/` tree (`{scan}.predictions.json` + `{scan}.scan_metadata.json` + `.slp`), writes `{scan_key}.result.json`; CPU. Bakes `SRT_TRAITS_CODE_SHA` → `traits_code_sha`.

## External prerequisites (block the end-to-end run, not the manifest authoring)
- predict #24 — warm-batch predict container CLI + image (does not exist yet).
- sleap-roots #256 — trait-extractor GHCR image (in progress).
- A `wandb-api-key` k8s secret in `runai-talmo-lab` (Task 6).
- A pre-staged reference scan on `/hpi/hpi_dev` with a hand-authored `{scan}.scan_metadata.json` sidecar (Task 7).

## File Structure
- Modify `sleap-roots-predictor-template.yaml` — GHCR predict image; args `<in> <out>`; `WANDB_API_KEY` env from secret; drop the `models_input` mount.
- Modify `sleap-roots-trait-extractor-template.yaml` — GHCR trait-extractor image; args = the two dirs; drop the `python /workspace/src/main.py` prefix (ENTRYPOINT baked).
- Modify `sleap-roots-pipeline.yaml` — 2-stage DAG (drop models-downloader); volumes for staged-images / predictions / results.
- Modify `runai_run_pipeline.sh` — drop `models-downloader-template.yaml` from `TEMPLATES`.
- Modify the `local-WSL2-*` variants to match (predictor, trait-extractor, pipeline).
- Create `openspec/changes/add-per-scan-argo-workflow/` (proposal, tasks, design, spec delta for a `per-scan-pipeline` capability).

---

### Task 1: OpenSpec proposal for the per-scan workflow

**Files:** Create `openspec/changes/add-per-scan-argo-workflow/{proposal.md,tasks.md,design.md,specs/per-scan-pipeline/spec.md}`

- [ ] **Step 1:** `/openspec:proposal add-per-scan-argo-workflow` — scope: rewrite the DAG to `predict(warm)→traits`, drop models-downloader, consume the two GHCR containers; explicitly defer write-back/batching/dedup/resume/notify/auto-stage-in. Reference the A4 design doc.
- [ ] **Step 2:** Spec delta `## ADDED Requirements` with a requirement "Per-scan workflow runs warm-predict then traits over a staged scan dir" + a `#### Scenario:` asserting a cluster submit yields `{scan}.result.json` on the mount.
- [ ] **Step 3:** `openspec validate add-per-scan-argo-workflow --strict` → passes.
- [ ] **Step 4:** Commit. `git add openspec/changes/add-per-scan-argo-workflow && git commit -m "openspec: propose add-per-scan-argo-workflow"`

### Task 2: Predictor template → warm GHCR predict

**Files:** Modify `sleap-roots-predictor-template.yaml`

- [ ] **Step 1:** Replace the container: image `→` the predict #24 GHCR image pinned by `sha-<sha>` (placeholder `ghcr.io/talmolab/sleap-roots-predict:sha-PENDING` until #24 publishes — Task 8 pins the real digest); `args: ["<mountPath in>", "<mountPath out>"]` (drop the legacy `python /workspace/src/main.py` + `models_input` arg); add `env: [{name: WANDB_API_KEY, valueFrom: {secretKeyRef: {name: wandb-api-key, key: WANDB_API_KEY}}}]`; **remove** the `models-output-dir`→`/workspace/models_input` volumeMount. Keep `resources.limits.nvidia.com/gpu: 1`, `retryStrategy`, `securityContext`, and the `gpu-fraction`/`preemptible` annotations.

```yaml
      container:
        image: ghcr.io/talmolab/sleap-roots-predict:sha-4a70e59978cffbf2b144b5b20cb08f8d12ef633f
        imagePullPolicy: Always
        args: ["/workspace/images_input", "/workspace/output"]
        env:
          - name: WANDB_API_KEY
            valueFrom: { secretKeyRef: { name: wandb-api-key, key: WANDB_API_KEY } }
        volumeMounts:
          - { name: images-input-dir, mountPath: /workspace/images_input }
          - { name: predictions-output-dir, mountPath: /workspace/output }
        securityContext: { privileged: true, runAsUser: 0 }
        resources: { limits: { nvidia.com/gpu: 1 } }
```

- [ ] **Step 2:** Lint. Run: `argo lint sleap-roots-predictor-template.yaml` → **Expected:** `lint successful` (or the offline schema check passes).
- [ ] **Step 3:** Commit. `git commit -am "feat(predict-template): warm GHCR predict, drop models dir"`

### Task 3: Trait-extractor template → GHCR image

**Files:** Modify `sleap-roots-trait-extractor-template.yaml`

- [ ] **Step 1:** Set image `ghcr.io/talmolab/sleap-roots-trait-extractor:sha-bb2199c` (sleap-roots #257, **shipped** — real immutable tag); set `args: ["/workspace/input", "/workspace/output"]` (drop the `python /workspace/src/main.py` prefix — the image's `ENTRYPOINT` is `["python","-m","trait_extractor"]`). Keep the two volumeMounts, `retryStrategy`, `securityContext`, `preemptible`.

```yaml
      container:
        image: ghcr.io/talmolab/sleap-roots-trait-extractor:sha-bb2199c
        imagePullPolicy: Always
        args: ["/workspace/input", "/workspace/output"]
        volumeMounts:
          - { name: predictions-output-dir, mountPath: /workspace/input }
          - { name: traits-output-dir, mountPath: /workspace/output }
        securityContext: { privileged: true, runAsUser: 0 }
```

- [ ] **Step 2:** Lint. Run: `argo lint sleap-roots-trait-extractor-template.yaml` → **Expected:** passes.
- [ ] **Step 3:** Commit. `git commit -am "feat(traits-template): pull GHCR trait-extractor, python -m entry"`

### Task 4: DAG → 2-stage predict→traits

**Files:** Modify `sleap-roots-pipeline.yaml`

- [ ] **Step 1:** Remove the `models-downloader` task and the `predictor.dependencies: [models-downloader]`; make `predictor` the DAG root and `trait-extractor` depend on it. Remove the now-unused `models-input-dir` / `models-output-dir` volumes; keep `images-input-dir` (staged scan images), `predictions-output-dir`, `traits-output-dir` on their `/hpi/hpi_dev` hostPaths.

```yaml
  templates:
    - name: pipeline
      dag:
        tasks:
          - name: predictor
            templateRef: { name: sleap-roots-predictor-template, template: predictor }
          - name: trait-extractor
            templateRef: { name: sleap-roots-trait-extractor-template, template: trait-extractor }
            dependencies: [predictor]
```

- [ ] **Step 2:** Lint. Run: `argo lint sleap-roots-pipeline.yaml` → **Expected:** passes (templateRefs resolve offline or the lint warns only on missing templates — acceptable pre-registration).
- [ ] **Step 3:** Commit. `git commit -am "feat(pipeline): 2-stage predict->traits DAG, drop models-downloader"`

### Task 5: Submit script + local variants

**Files:** Modify `runai_run_pipeline.sh`; `local-WSL2-sleap-roots-predictor-template.yaml`, `local-WSL2-sleap-roots-trait-extractor-template.yaml`, `local-WSL2-sleap-roots-pipeline.yaml`

- [ ] **Step 1:** In `runai_run_pipeline.sh`, drop `"models-downloader-template.yaml"` from the `TEMPLATES=(...)` array (keep predictor + trait-extractor).
- [ ] **Step 2:** Mirror Tasks 2–4 into the `local-WSL2-*` variants (same image/args/DAG changes; keep their local hostPaths/CPU predict per the existing local pattern).
- [ ] **Step 3:** Lint each changed local manifest: `argo lint local-WSL2-sleap-roots-pipeline.yaml` etc. → **Expected:** passes.
- [ ] **Step 4:** Commit. `git commit -am "chore(run): drop models-downloader from submit; sync local-WSL2 variants"`

### Task 6: WANDB secret (infra, one-time)

- [ ] **Step 1:** Create the secret the predict step reads: `kubectl -n runai-talmo-lab create secret generic wandb-api-key --from-literal=WANDB_API_KEY=$WANDB_API_KEY` (run once on the internal machine; do NOT commit the key). Verify: `kubectl -n runai-talmo-lab get secret wandb-api-key`.

### Task 7: Pre-stage a reference scan (infra, PoC input)

- [ ] **Step 1:** Stage one reference scan in the **nested** `discover_scans` layout under the `images-input-dir` hostPath on `/hpi/hpi_dev`: `{scan_key}/<frames>` + `{scan_key}.scan_metadata.json` (hand-author the sidecar: `image_ids`, `images_checksum`, `params={species,mode,age}` — cylinder scan, so `mode=cylinder`). The sidecar goes in **predict's input** dir; predict copies it forward into its output (D1), so the traits container sees it — you do **not** stage it into the predictions dir. Verify from a cluster pod or the internal machine.

### Task 8: Pin real image digests + end-to-end cluster submit (primary acceptance gate)

**Blocked on:** ~~predict #24 image published~~ ✅ (predict #27), ~~sleap-roots #256 image published~~ ✅ (sleap-roots #257) — both shipped. Remaining blocker = Tasks 6–7 (wandb secret + staged scan) + both GHCR packages pullable by the cluster SA.

- [x] **Step 1:** Both `:sha-PENDING` tags replaced with the real published immutable tags — predict `sha-4a70e59978cffbf2b144b5b20cb08f8d12ef633f` (predict #27, digest `@sha256:68a0ba12…be0` in the template comment) and traits `sha-bb2199c` (sleap-roots #257).
- [ ] **Step 2:** Ensure both GHCR packages are **pullable** by the cluster (public or an `imagePullSecret` on the SA) — the traits package is private on first push (#256 flags this).
- [ ] **Step 3:** Submit. Run: `bash runai_run_pipeline.sh` → **Expected:** templates register; the Workflow submits; `predictor` acquires a GPU and writes `{scan}.predictions.json` + `.slp` to the predictions dir; `trait-extractor` runs and writes `{scan}.result.json` to the traits dir; both nodes succeed.
- [ ] **Step 4:** Verify the output on `/hpi/hpi_dev`: each `{scan_key}.result.json` parses as a `sleap-roots-contracts` `ResultEnvelope` with `provenance.contract_version == "0.1.0a3"` and a matching `scan_key`. This is the PoC acceptance gate.

### Task 9: Validate + PR

- [ ] **Step 1:** `openspec validate add-per-scan-argo-workflow --strict` → passes.
- [ ] **Step 2:** Re-lint all changed manifests (`argo lint`).
- [ ] **Step 3:** `/pr-description`; open the PR referencing the A4 EPIC (#10) + the OpenSpec change; note the PoC run result; leave write-back/batching/dedup/resume/notify/auto-stage-in as tracked follow-on slices.

---

## Deferred to later slices (not this plan)
- **Write-back step** (bloomcli ingest → `insert_cyl_result_envelope`) — RPC **now accepts `0.1.0a3`** (bloom #393 ✅ / PR #399, prefix-tolerant `contract_version` match); gated only on the ingest CLI bloom #397.
- **Automated stage-in** (bloomctl `--scan-id` container + the ScanMetadata sidecar producer) — replaces the manual Task 7.
- **Batching + fan-out + Argo semaphore + RunAI-quota concurrency**, **cluster-side dedup skip**, **resume hardening** (atomic writes, checksum-verified skip, attempt cap), **notify** — the A4 hardening slice.
- **Producer Argo-readiness (both producers, reconcile uniformly):** empty-input → exit 0 (silent-green), exit-non-zero-on-any-scan-fail → whole-batch retry, and SIGTERM/graceful-preempt. Tracked for traits as [sleap-roots #259](https://github.com/talmolab/sleap-roots/issues/259); **predict has the identical behaviour** (`run_batch` `ok=True` on empty, non-zero on any fail) — resolve the exit-code/empty-input/SIGTERM policy the same way for both. See design §8.
- **The Bloom trigger + `pipeline_runs`** (bloom repo, gated on #404) and **push transport (Tailscale)** — separate plans.
