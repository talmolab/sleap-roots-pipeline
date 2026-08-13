# Add ARGO_WORKFLOW_NAME env var to images-downloader + write-back

## Why

Closes [#38](https://github.com/talmolab/sleap-roots-pipeline/issues/38), part of the
cross-repo chain tracked in [#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37).
`bloomctl` (`salk-bloom` [#653](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/653)/
[PR #655](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/655), open/unmerged)
already reads `ARGO_WORKFLOW_NAME` for `RunManifest.pipeline_run_id`, but neither template sets
it, so it always falls back to a `local-<hex>` placeholder even inside a real Argo run.

## What Changes

- Add an `ARGO_WORKFLOW_NAME` env var to both templates' container `env:` blocks, sourced from
  Argo's built-in `{{workflow.name}}` variable (unique per submission — already used as a manual
  test/traceability key by this program since 2026-07-07).
- **Manifest-visibility decision (confirmed with user 2026-08-12):** do NOT add a new
  `images-input-dir` volume mount to `write-back`'s template — see `design.md` for the full
  reasoning and the copy-forward alternative recorded there. The actual copy-forward code is
  **out of scope for this change**.
- No `bloomctl`/`salk-bloom` code changes here — this is a template-only, non-code change.

## Impact

- Affected specs: `per-batch-pipeline` (modifies the existing "bloomctl-based tasks pin their
  image and mount credentials deterministically" requirement to also cover workflow-identity env).
- Affected files: `sleap-roots-images-downloader-template.yaml`,
  `sleap-roots-write-back-template.yaml`.
- No application code, no new volumes, no change to the DAG or existing `args`.
