# Tasks

Declarative repo — a task's "test" is `argo lint`, a WSL2 dry-run, or a cluster submit (no
pytest). Detailed steps + target YAML live in
`docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`.

## 1. Predictor template → warm GHCR predict

- [x] 1.1 Edit `sleap-roots-predictor-template.yaml`: GHCR predict image pinned by `sha-<sha>`
  (placeholder `:sha-PENDING` until predict #24 publishes); `args: ["<in>", "<out>"]`; add
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

- [ ] 5.1 Create the `wandb-api-key` secret in `runai-talmo-lab` (do not commit the key).
- [ ] 5.2 Pre-stage a reference scan (+ `{scan}.scan_metadata.json` sidecar) on `/hpi/hpi_dev`.

## 6. End-to-end run (primary acceptance gate — blocked on producer images)

- [ ] 6.1 Pin the real published digests (predict #24, sleap-roots #256) in both templates; ensure
  the GHCR packages are pullable by the cluster SA.
- [ ] 6.2 `bash runai_run_pipeline.sh` → predictor writes `{scan}.predictions.json` + `.slp`;
  trait-extractor writes `{scan}.result.json`; both DAG nodes succeed.
- [ ] 6.3 Verify each `{scan}.result.json` on the mount parses as a `ResultEnvelope` with
  `provenance.contract_version == "0.1.0a3"` and a matching `scan_key`.

## 7. Validate + close out

- [ ] 7.1 `openspec validate add-per-scan-argo-workflow --strict` passes.
- [ ] 7.2 Re-lint all changed manifests; `/pr-description`; open the PR referencing A4 EPIC
  (talmolab/sleap-roots-pipeline#10); note the run result; leave the deferred slices tracked.
