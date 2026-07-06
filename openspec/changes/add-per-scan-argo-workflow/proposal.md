## Why

The pipeline is the legacy three-stage `models-downloader → predictor → trait-extractor`
DAG pulling GitLab images. The A4 roadmap target replaces this with per-scan orchestration
built on GHCR producers that load models in-process. This change lands the **first A4 step in
this repo**: rewrite the DAG to a **two-stage warm-predict → traits** flow that consumes two
new GHCR producer containers and **drops the models-downloader stage** (models now load
in-process from the wandb registry inside the warm predictor).

Grounded in the approved design + plan:
- `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` (§3 predict-all/traits stages)
- `docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`

Deliberately **deferred to later changes** (each its own OpenSpec change): the write-back
step, automated stage-in, batching/fan-out, Argo-semaphore + RunAI-quota concurrency,
cluster-side dedup, resume hardening, notification, the Bloom request trigger + `pipeline_runs`,
and the Tailscale/push transport. This change is the runnable predict→traits core, submitted
manually from an internal machine over a pre-staged scan.

## What Changes

- **Rewrite the DAG** (`sleap-roots-pipeline.yaml`) to two stages: `predictor` (root) →
  `trait-extractor` (depends on `predictor`). Remove the `models-downloader` task and its
  `models-input-dir` / `models-output-dir` volumes.
- **Predictor** (`sleap-roots-predictor-template.yaml`): pull the warm-batch GHCR predict image
  (`sleap-roots-predict` #24), pinned by digest/`sha-<sha>`; args `["<in_dir>", "<out_dir>"]`;
  add a `WANDB_API_KEY` env from a `wandb-api-key` secret; **remove the `models_input` mount**;
  keep the GPU limit, `retryStrategy`, `securityContext`, and RunAI annotations.
- **Trait-extractor** (`sleap-roots-trait-extractor-template.yaml`): pull
  `ghcr.io/talmolab/sleap-roots-trait-extractor` (`sleap-roots` #256), pinned by digest/`sha-<sha>`;
  args = the two dirs only (the image `ENTRYPOINT` is `["python","-m","trait_extractor"]`).
- **Launcher** (`runai_run_pipeline.sh`): drop `models-downloader-template.yaml` from the
  registered `TEMPLATES`.
- **Local parity**: reconcile mount/path drift in the `local-WSL2-*` variants (template names +
  `retryStrategy` deliberately differ — do not mirror those).

## Impact

- **New capability:** `per-scan-pipeline`.
- **Affected code:** `sleap-roots-pipeline.yaml`, `sleap-roots-predictor-template.yaml`,
  `sleap-roots-trait-extractor-template.yaml`, `runai_run_pipeline.sh`, the `local-WSL2-*`
  variants. (`models-downloader-template.yaml` is dropped from the flow.)
- **External prerequisites (block the run, not the manifest change):** the two producer images
  published + pullable (predict #24, sleap-roots #256); a `wandb-api-key` k8s secret in
  `runai-talmo-lab`; a pre-staged reference scan (+ `{scan}.scan_metadata.json` sidecar) on
  `/hpi/hpi_dev`.
- **Contract dependency:** the container invocation/args/output format defined here must match
  what predict #24 and sleap-roots #256 actually expose; reconcile if either refines its interface.
