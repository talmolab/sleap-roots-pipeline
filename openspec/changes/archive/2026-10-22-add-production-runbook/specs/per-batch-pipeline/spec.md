## MODIFIED Requirements

### Requirement: Every producer carries the Argo workflow identity

Every batch-processing stage template SHALL set an `ARGO_WORKFLOW_NAME` environment variable
sourced from Argo's built-in `{{workflow.name}}` — `images-downloader`, `predictor`,
`trait-extractor` and `write-back` alike.

The two `bloomctl` stages already consume it. The `predictor` consumes it since its predict#47 pin
(2026-09-25): predict resolves `run_manifest.<ARGO_WORKFLOW_NAME>.json` ahead of the legacy file.
The `trait-extractor` consumes it since its sleap-roots#269 pin (`sha-e373b0f`, 2026-09-28):
traits resolves `run_manifest.<ARGO_WORKFLOW_NAME>.json` ahead of the legacy file.

The variable is required because the stage directories are fixed `hostPath`s shared by every run
in an environment. Before contracts a9, the single legacy `run_manifest.json` accumulated
`scan_keys` across those runs, so the manifest a stage was scoped by could belong to a different
run. Since a9, each run writes and reads its own `run_manifest.<ARGO_WORKFLOW_NAME>.json`;
readers still fall back to a legacy `run_manifest.json` while `allow_legacy=True`. That
scoping exists only because each stage knows its own workflow identity, so carrying the variable
remains the prerequisite for any run-scope validation. A stage that runs with no run id falls back
to the legacy name, which is why such runs must not be pointed at a shared tree.

#### Scenario: All four batch-processing templates carry ARGO_WORKFLOW_NAME

- **WHEN** the images-downloader, predictor, trait-extractor and write-back templates are inspected
- **THEN** each declares an `ARGO_WORKFLOW_NAME` entry in its container `env:`
- **AND** each such entry's `value` is exactly `"{{workflow.name}}"`
