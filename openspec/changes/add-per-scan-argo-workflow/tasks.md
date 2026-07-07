# Tasks

Declarative repo — a task's "test" is `argo lint`, a WSL2 dry-run, or a cluster submit (no
pytest). Detailed steps + target YAML live in
`docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`.

## 1. Predictor template → warm GHCR predict

- [x] 1.1 Edit `sleap-roots-predictor-template.yaml`: GHCR predict image
  `ghcr.io/talmolab/sleap-roots-predict:sha-4a70e59978cffbf2b144b5b20cb08f8d12ef633f` (predict #27,
  **shipped** — real immutable tag; tighten to `@sha256:68a0ba12…be0` when public); `args: ["<in>", "<out>"]`; add
  `WANDB_API_KEY` from `secretKeyRef` (`wandb-api-key`); remove the `models_input` volumeMount; keep
  GPU limit, `retryStrategy`, `securityContext`, annotations.
- [x] 1.2 `argo lint --offline sleap-roots-predictor-template.yaml` → ✔ no errors.

## 2. Trait-extractor template → GHCR image

- [x] 2.1 Edit `sleap-roots-trait-extractor-template.yaml`: image
  `ghcr.io/talmolab/sleap-roots-trait-extractor:sha-bb2199c` (sleap-roots #257, **shipped** — real
  immutable tag; tighten to `@sha256:<digest>` at run time when the package is public); `args:
  ["<in>", "<out>"]` (dropped the `python /workspace/src/main.py` prefix); kept the two mounts +
  `retryStrategy`. Image bakes `SRT_TRAITS_CODE_SHA` → non-empty `traits_code_sha`.
- [x] 2.2 `argo lint --offline sleap-roots-trait-extractor-template.yaml` → ✔ no errors.
- [ ] 2.3 **Wiring reconciliation (sleap-roots #259):** exit-code vs `retryStrategy` (any-scan-fail
  retries the whole batch), empty-`/in` silent-green, and driver SIGTERM. Decide at write-back/
  hardening time (distinct exit codes / `continueOn` / per-scan fan-out + empty-input guard).
  Noted in the template.

## 3. DAG → two-stage predict→traits

- [x] 3.1 Edit `sleap-roots-pipeline.yaml`: removed the `models-downloader` task + its two model
  volumes; `predictor` is the root; `trait-extractor` depends on `predictor`.
- [x] 3.2 Templates lint clean offline; the Workflow's `templateRef` resolves only against a cluster
  with the templates registered (offline `argo lint` cannot cross-resolve local `WorkflowTemplate`
  files) — full lint happens after `argo template create` in the launcher, before submit.

## 4. Launcher + local parity

- [x] 4.1 Edit `runai_run_pipeline.sh`: dropped `models-downloader-template.yaml` from `TEMPLATES`.
- [ ] 4.2 **Deferred → #21** (local dev testing needs a local k8s cluster). The `local-WSL2-*`
  variants stay on the old 3-stage flow until then; not required for this change (the PoC runs on
  the cluster). WSL2 has no GPU, so what local testing exercises for the predict stage is an open
  question tracked in #21.

## 5. Infra prerequisites (one-time, external)

- [x] 5.1 Created the wandb secret via the **RunAI console** (Credentials → Generic secret, **Project
  scope** `talmo-lab`, key `WANDB_API_KEY`). ⚠️ RunAI prefixes the k8s secret name: asset
  `wandb-api-key` → secret **`genericsecret-wandb-api-key`**, so the predictor template's
  `secretKeyRef.name` must reference the prefixed name (not the bare asset name).
- [x] 5.2 Staged reference scan `scan_6791737` (rice / cylinder / age 3; 72 `.jpg` frames + an authored
  `scan_6791737.scan_metadata.json` sidecar) under `…/pipeline_orchestration_tests/a4_poc/input/`; the
  workflow hostPaths point at `a4_poc/{input,predictions,traits}`.

## 6. End-to-end run (primary acceptance gate — blocked on producer images)

- [x] 6.1 **Digest pin ✅ applied** — predict `sha-4a70e599…` (predict #27) + traits `sha-bb2199c`
  (sleap-roots #257) pinned in both templates. Both GHCR packages verified **PUBLIC / pullable**
  (anonymous manifest `HTTP 200`) → no `imagePullSecret` needed. Predict image is **8.9 GB** (~7 min
  cold pull on a fresh node; cached thereafter — re-runs start instantly).
- [x] 6.2 **Ran end-to-end** via `argo submit` in **Kubernetes mode** through the `argo-user`
  kubeconfig (the `runai_run_pipeline.sh` launcher needs `ARGO_TOKEN`/the in-cluster Argo Server,
  unavailable from here). Workflows `sleap-roots-pipeline-4m2zg` + `b7x7t` **Succeeded** in ~2m34s:
  predictor on a GPU (`gpu-node3`), trait-extractor on CPU, both DAG nodes green. Required
  `priorityClassName: interactive-preemptible` on the predictor — the 20-GPU deserved quota was full
  (`NonPreemptibleOverQuota`); the `preemptible: "true"` annotation alone does **not** set this.
- [x] 6.3 **Acceptance gate PASSED.** `scan_6791737.result.json` (135 KB) parses as a `ResultEnvelope`:
  `contract_version 0.1.0a3`, `scan_key scan_6791737`, **918 traits**, 72 `image_ids`; provenance
  `predict_code_sha 4a70e599` + `traits_code_sha bb2199c` **both match the pinned images** — the
  provenance chain is intact end-to-end (the input to idempotent write-back).

## 7. Validate + close out

- [x] 7.1 `openspec validate add-per-scan-argo-workflow --strict` → valid.
- [ ] 7.2 Re-lint all changed manifests; `/pr-description`; open the PR referencing A4 EPIC
  (talmolab/sleap-roots-pipeline#10); note the run result; leave the deferred slices tracked.
