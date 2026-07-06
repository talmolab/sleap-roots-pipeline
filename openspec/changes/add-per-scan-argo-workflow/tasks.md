# Tasks

Declarative repo — a task's "test" is `argo lint`, a WSL2 dry-run, or a cluster submit (no
pytest). Detailed steps + target YAML live in
`docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`.

## 1. Predictor template → warm GHCR predict

- [ ] 1.1 Edit `sleap-roots-predictor-template.yaml`: GHCR predict image pinned by `sha-<sha>`;
  `args: ["<in>", "<out>"]`; add `WANDB_API_KEY` from `secretKeyRef` (`wandb-api-key`); remove the
  `models_input` volumeMount; keep GPU limit, `retryStrategy`, `securityContext`, annotations.
- [ ] 1.2 `argo lint sleap-roots-predictor-template.yaml` passes.

## 2. Trait-extractor template → GHCR image

- [ ] 2.1 Edit `sleap-roots-trait-extractor-template.yaml`: image
  `ghcr.io/talmolab/sleap-roots-trait-extractor` pinned by `sha-<sha>`; `args: ["<in>", "<out>"]`
  (drop the `python /workspace/src/main.py` prefix); keep the two mounts + `retryStrategy`.
- [ ] 2.2 `argo lint sleap-roots-trait-extractor-template.yaml` passes.

## 3. DAG → two-stage predict→traits

- [ ] 3.1 Edit `sleap-roots-pipeline.yaml`: remove the `models-downloader` task and its two model
  volumes; make `predictor` the root and `trait-extractor` depend on it.
- [ ] 3.2 `argo lint sleap-roots-pipeline.yaml` passes.

## 4. Launcher + local parity

- [ ] 4.1 Edit `runai_run_pipeline.sh`: drop `models-downloader-template.yaml` from `TEMPLATES`.
- [ ] 4.2 Reconcile mount/path drift in the `local-WSL2-*` variants (do not mirror template names /
  retryStrategy — those deliberately differ); `argo lint` each changed local manifest.

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
