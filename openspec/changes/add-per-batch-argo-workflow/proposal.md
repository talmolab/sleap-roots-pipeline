## Why

The DAG is still the A4 PoC's hardcoded two-stage `predictor → trait-extractor` flow against one
fixed, manually pre-staged scan directory. `bloomctl` now has batch-capable stage-in/write-back
commands (`batch-download-for-predict` / `batch-ingest-result`,
[bloom #532](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/532)) — this change
wires them in as the pipeline's missing first and last stages, turning it into a real four-task
per-batch pipeline: `images-downloader → predictor → trait-extractor → write-back`.

Grounded in the approved design:
`docs/superpowers/specs/2026-07-28-a4-batch-stage-write-back-design.md`.

Deliberately **deferred to later changes**: the Argo semaphore for concurrent-batch concurrency
(design §9 of `2026-07-06-a4-request-driven-pipeline-design.md`), per-run path isolation (still
reuses the fixed `a4_poc` hostPath paths), moving off the interim `sha-61959bd` image tag, the
dev-personal hostPath convention, the Bloom-side trigger route/`cyl_pipeline_runs` tables/dispatch
worker, producer Argo-readiness reconciliation (predict #26 / sleap-roots #259), and notification
(#18). This change is the runnable four-stage core, submitted manually via
`argo submit --parameter scan-ids=...`.

## What Changes

- **Rewrite the DAG** (`sleap-roots-pipeline.yaml`) to four stages: `images-downloader` (root) →
  `predictor` → `trait-extractor` → `write-back`. Add a `scan-ids` Workflow parameter and a
  `bloom-credentials` Secret volume. `predictor`/`trait-extractor` templates are unchanged.
- **New `sleap-roots-images-downloader-template.yaml`**: runs `bloomctl cyl
  batch-download-for-predict <images-input-dir> --scan-ids {{workflow.parameters.scan-ids}}`,
  image `ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd`.
- **New `sleap-roots-write-back-template.yaml`**: runs `bloomctl cyl batch-ingest-result
  <traits-output-dir> --predictions-dir <predictions-output-dir>`, same image.
- Both new templates set `HOME=/home/bloom` explicitly (the image's runtime user has no
  deterministic home dir otherwise) and mount a `bloom-credentials` Secret at
  `/home/bloom/.bloom/credentials.txt` — a placeholder reference; the actual credential is being
  provisioned in a parallel `salk-bloom` session (sleap-roots-pipeline#17) and this change does not
  depend on it landing first.
- **Launcher** (`runai_run_pipeline.sh`): register the two new template files.
- **Local parity**: sync `local-WSL2-sleap-roots-pipeline.yaml` to the same four-stage shape
  (dropping its stale leftover `models-downloader` task, left over from before the cluster side
  dropped it), add matching `local-WSL2-*-template.yaml` files. Local credentials use a `hostPath`
  bind-mount of a real `~/.bloom/credentials.txt`, not a Kubernetes Secret, so a WSL2 dry-run can
  genuinely exercise both new `bloomctl` commands end-to-end.

## Impact

- **New capability:** `per-batch-pipeline` (supersedes `per-scan-pipeline`).
- **Removed capability:** `per-scan-pipeline` — its two-task/single-hardcoded-scan requirements no
  longer hold. Single-scan support isn't lost; it's a batch of size 1 through the new pipeline.
- **Affected code:** `sleap-roots-pipeline.yaml`, two new cluster template files, two new
  `local-WSL2-*` template files, `local-WSL2-sleap-roots-pipeline.yaml`, `runai_run_pipeline.sh`.
  `sleap-roots-predictor-template.yaml`/`sleap-roots-trait-extractor-template.yaml` are untouched.
- **External prerequisites (block a live cluster run, not the manifest change or its validation):**
  the `bloom-pipeline-credentials` Secret must exist with real values (tracked separately,
  sleap-roots-pipeline#17, in progress). This change's validation target is `argo lint` + a real
  local WSL2 dry-run, not a live cluster run — see `tasks.md`.
