# Tasks

## 1. Image pins (do first — the wiring is inert without them)

- [ ] 1.1 Bump `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` from `bloomctl:sha-3659705` to `sha-0614889`, and record
  in the file comment that this build carries both bloom#830's partial-success exit code and
  bloom#774's per-scan status marking.
  **Validate:** both files grep to the new tag; `sha-0614889`'s digest matches
  `sha256:e39b4746e68b4405d1d91899e358aee5a2badf1a9b8f103cd6971d28881a7cc5` via a GHCR manifest
  query (do not derive the tag from `git rev-parse --short` — the CI runner abbreviates to 7 chars).
- [ ] 1.2 Bump `sleap-roots-predictor-template.yaml` to
  `sha-e025e309230de52cef0ccffa199048fe1dbd1b24` (predict#42's manifest forward-copy).
  **Validate:** digest matches `sha256:4d4064c6…` via GHCR; note predict uses full 40-char sha tags.
- [ ] 1.3 Leave `sleap-roots-trait-extractor-template.yaml`'s `sha-689cffb` pin unchanged, and
  correct its stale comment claiming an empty `/in` exits `0` (sleap-roots#266 closed that; it now
  exits `1` with no manifest, `3` with one).
  **Validate:** `git diff 689cffb origin/main` in `sleap-roots` shows OpenSpec docs only, confirming
  the built image is unchanged.

## 2. The exit-gate template

- [ ] 2.1 Add `sleap-roots-exit-gate-template.yaml`: one `exit-gate` template declaring an
  `inputs.parameters` entry for the producers' codes, running the already-pinned `bloomctl` image
  (reused to avoid a new supply-chain dependency), comparing each code against `{0, 3}` and exiting
  non-zero otherwise. Emit the offending stage and code to stderr so a failure is diagnosable from
  the pod log alone.
  **Validate:** `argo lint sleap-roots-exit-gate-template.yaml`.
- [ ] 2.2 Cover the empty/unresolved-parameter case explicitly — an empty code must be treated as a
  failure, never silently skipped.
  **Validate:** run the gate's comparison locally against `"0,3,0"`, `"0,1,0"`, `"0,,0"` and `""`;
  expect exit 0, non-zero, non-zero, non-zero.

## 3. DAG wiring

- [ ] 3.1 Add `continueOn: {failed: true}` to the `images-downloader`, `predictor` and
  `trait-extractor` tasks in `sleap-roots-pipeline.yaml`. Do not add it to `write-back`.
  **Validate:** manifest assertion — exactly three tasks carry `continueOn`, none carries
  `continueOn.error`.
- [ ] 3.2 Add the `exit-gate` DAG task depending on `write-back`, passing the three producers'
  `{{tasks.<name>.exitCode}}` values as `arguments.parameters`.
  **Validate:** `argo lint sleap-roots-pipeline.yaml`; confirm no task declares `depends` and that
  `exit-gate` is the only task no other task depends on.
- [ ] 3.3 Extend the file's header comment: record that the gate is the DAG's only leaf and
  therefore determines the Workflow phase, and that every producer referenced by the gate must
  remain an ancestor of it or the Workflow will hang on an unresolvable reference.
  **Validate:** comment present and mentions both constraints.

## 4. Launcher

- [ ] 4.1 Register `sleap-roots-exit-gate-template.yaml` in `runai_run_pipeline.sh`'s `TEMPLATES`.
  **Validate:** `bash -n runai_run_pipeline.sh`; the list contains all five templates.

## 5. Live verification (staging, `A4-PIPELINE-E2E-TEST`)

Announce before starting — this shares the 2-GPU `busch-lab` quota, the `A4-PIPELINE-E2E-TEST`
scans and the `a4_poc` NFS paths with any other in-flight work. Note prod and staging share the
`runai-busch-lab` namespace, so `argo template update` affects both.

- [ ] 5.1 `argo template update` all five templates against `runai-busch-lab`, then confirm the
  registered copies match this repo (no drift-check exists — #58).
  **Validate:** `argo template get` for each; diff against the local file.
- [ ] 5.2 **Poison-scan scenario.** Re-run 2026-09-01's scenario 3: one scan whose `cyl_images` row
  points at never-uploaded object-storage content, plus two good scans, one batch.
  **Validate:** DAG reaches `write-back`; both good scans' `.result.json` land on the NFS mount with
  fresh mtimes and appear in `cyl_trait_sources`; the poison scan's row is `failed`; `done_count=2`,
  `failed_count=1`; Workflow `Succeeded`. Verify by artifact, not workflow status alone.
- [ ] 5.3 **Crash-injection scenario** — the load-bearing test, since swallowing real crashes is
  this design's failure mode. Submit with a deliberately malformed `scan-ids` parameter so
  `bloomctl` raises a `ClickException`/`UsageError` rather than a partial success.
  **Validate:** the gate rejects it and the Workflow ends `Failed`.
- [ ] 5.4 Confirm an unrelated leftover scan's `result.json` mtime is unchanged by either run (the
  standing leftover-contamination pass signal from #54/#55).

## 6. Cross-repo lockstep

- [ ] 6.1 After this PR merges, open the companion `salk-bloom` PR updating
  `services/workflows/vendored/sleap-roots-pipeline.yaml` to the new content and
  `services/workflows/vendored/SLEAP_ROOTS_PIPELINE_REF` to this PR's merge commit (currently
  `9df1e52`). Sequential by nature — the ref cannot be pinned before the merge commit exists.
  **Validate:** `python3 scripts/check_vendored_workflow_drift.py` passes in that PR.

## 7. Record

- [ ] 7.1 Add a roadmap status-log entry recording what was actually observed, including that the
  run reads `complete` with `failed_count > 0` rather than `partial`, and why (bloom#857). State
  plainly that a green Workflow does not mean no scans failed.
- [ ] 7.2 Confirm the three deferred follow-ups are linked from the roadmap: bloom#857, bloom#859,
  sleap-roots-predict#44.
