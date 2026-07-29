# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit (no pytest, no local WSL2 dry-run — see task 6 for why). Full rationale + deferred items in
`design.md` and `docs/superpowers/specs/2026-07-28-a4-batch-stage-write-back-design.md`.

## 1. Images-downloader template (new)

- [x] 1.1 Create `sleap-roots-images-downloader-template.yaml`: image
  `ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd`; `args: ["cyl",
  "batch-download-for-predict", "/workspace/images_input", "--scan-ids",
  "{{workflow.parameters.scan-ids}}"]`; `env: [{name: HOME, value: /home/bloom}]`; mounts
  `images-input-dir` at `/workspace/images_input` and a `bloom-credentials` Secret at
  `/home/bloom/.bloom/credentials.txt` (`subPath: credentials.txt`, `readOnly: true`);
  `labels: {project: talmo-lab}` (matches `predictor`/`trait-extractor`'s RunAI quota
  attribution); `priorityClassName: interactive-preemptible`; `retryStrategy` (limit 2); no
  `privileged`/`runAsUser: 0`.
- [x] 1.2 `argo lint --offline sleap-roots-images-downloader-template.yaml` (run via WSL, where the
  `argo` CLI actually lives per the `runai` skill — not on Windows Git Bash PATH) → ✔ no linting
  errors found.
- [x] 1.3 Inspected the template (`grep`): image tag is `sha-61959bd`, `HOME` is set, the Secret is
  mounted at exactly `/home/bloom/.bloom/credentials.txt`, `labels.project` is `talmo-lab` —
  matches `per-batch-pipeline`'s "Images-downloader stages a batch via bloomctl" and "bloomctl-based
  tasks pin their image and mount credentials deterministically" scenarios.

## 2. Write-back template (new)

- [x] 2.1 Create `sleap-roots-write-back-template.yaml`: same image/env/credential-mount/label
  pattern as 1.1; `args: ["cyl", "batch-ingest-result", "/workspace/input", "--predictions-dir",
  "/workspace/predictions"]`; mounts `traits-output-dir` at `/workspace/input` and
  `predictions-output-dir` at `/workspace/predictions`.
- [x] 2.2 `argo lint --offline sleap-roots-write-back-template.yaml` (via WSL) → ✔ no linting
  errors found.
- [x] 2.3 Inspected the template: same checks as 1.3, plus confirmed both `traits-output-dir` and
  `predictions-output-dir` are mounted — matches `per-batch-pipeline`'s "Write-back ingests a
  batch via bloomctl" scenario.

## 3. DAG rewrite

- [x] 3.1 Edited `sleap-roots-pipeline.yaml`: added `arguments.parameters: [{name: scan-ids, value:
  ""}]`; added a `bloom-credentials` Secret volume (`secretName:
  genericsecret-bloom-staging-pipeline-credentials` — updated after the credential was actually
  provisioned via the RunAI console, following the same `genericsecret-` prefix convention as
  `WANDB_API_KEY`, with an explicit `-staging` suffix so a later production credential can't
  collide with/overwrite this one); added `images-downloader` as the DAG root and `write-back` as
  the final task; `predictor` depends on `images-downloader`; `write-back` depends on
  `trait-extractor`.
- [x] 3.2 In the same edit, changed `images-input-dir`'s `hostPath.type` from `Directory` to
  `DirectoryOrCreate`, and updated its comment: it no longer requires manual pre-staging —
  `images-downloader` now writes there automatically. `predictions-output-dir`/`traits-output-dir`
  unchanged (already `DirectoryOrCreate`).
- [x] 3.3 Inspected the DAG's `tasks` list (`grep`): exactly four tasks, dependency chain matches
  `images-downloader → predictor → trait-extractor → write-back` — matches `per-batch-pipeline`'s
  "Four-stage per-batch DAG" scenario.
- [x] 3.4 Cross-checked `templateRef` resolution by hand: both new tasks'
  `templateRef.name`/`template` values in `sleap-roots-pipeline.yaml` exactly match the
  `metadata.name`/`spec.templates[].name` set in `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` — confirmed via `grep`, no mismatch.
- [x] 3.5 `argo lint --offline sleap-roots-pipeline.yaml` (via WSL) → 1 error:
  `templates.pipeline.tasks.images-downloader couldn't find workflow template
  "sleap-roots-images-downloader-template" in namespace "runai-talmo-lab"`. This is the same known
  limitation the archived `add-per-scan-argo-workflow` change documented (offline lint can't
  cross-resolve `templateRef`s against a namespace where the templates aren't registered) — not a
  new bug; 3.4's manual name cross-check already confirmed the reference is correct. Full
  cross-resolution happens after `argo template create`/`update`, in task 5.

## 4. Launcher

- [x] 4.1 Edited `runai_run_pipeline.sh`: added `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` to the registered `TEMPLATES` list.
- [x] 4.2 Inspected `TEMPLATES` (`grep`): lists all four template files, `bash -n` syntax-clean —
  matches `per-batch-pipeline`'s "Launcher registers all four templates" scenario.

## 5. Real cluster submit (primary acceptance gate — no local dry-run, see below)

**Why not a local WSL2 dry-run:** checked live — this machine's Docker Desktop Kubernetes node
(`desktop-control-plane`) has no `nvidia.com/gpu` in its `allocatable`/`capacity` at all, so
`predictor` cannot schedule locally regardless of anything this change does. The `local-WSL2-*`
variants are also already known-stale relative to the cluster's GHCR contract (tracked separately,
issue #21 — updated with this change's specifics, not touched here). This change validates
directly against the real RunAI cluster instead.

- [ ] 5.1 Register all four templates on the cluster via `runai_run_pipeline.sh` (or `argo
  template create`/`update` directly, per the script's own documented Kubernetes-mode fallback).
- [ ] 5.2 Submit with **two or more** real `scan-ids` (comma-separated) — not a single scan — to
  actually exercise batch behavior, since that's the point of this change. `argo submit
  sleap-roots-pipeline.yaml --parameter scan-ids=<id1>,<id2> -n runai-talmo-lab`.
- [ ] 5.3 Confirm the DAG structure resolves correctly at submit time (proves 3.4's cross-check was
  right) and `images-downloader` schedules and starts. The `genericsecret-
  bloom-staging-pipeline-credentials` Secret now exists with real values (sleap-roots-pipeline#17
  resolved for staging), so a **full successful run is the expected outcome** — confirm
  `images-downloader` actually authenticates and stages real frames. If it instead fails at the
  `bloomctl` auth step, that's a real bug to investigate (e.g. the RunAI console's multi-line value
  got mangled, or the `secretName`/key don't actually match what the console produced), not an
  expected gap. Record the actual result either way.
- [ ] 5.4 Confirm `batch-download-for-predict --scan-ids ""` (the parameter's empty default)
  behavior matches what the source implies (`parse_scan_ids_flag("")` → `[]` → exit 0, "nothing to
  stage," not a CLI parse error) — submit once with no `scan-ids` override and record the actual
  result. This determines whether an unparameterized submit is a safe no-op going forward.

## 6. Validate + close out

- [x] 6.1 `openspec validate add-per-batch-argo-workflow --strict` → valid.
- [x] 6.2 Re-linted all touched/new cluster manifests via WSL's `argo` CLI (v3.6.5) + `bash -n` on
  the launcher: both new templates lint clean; `sleap-roots-pipeline.yaml` hits the expected
  unregistered-`templateRef` error only (see 3.5) — no other issues.
- [ ] 6.3 `/pr-description`; open PR referencing A4 EPIC (talmolab/sleap-roots-pipeline#10) and this
  change-id. Note: this change replaces the working manual `argo submit` flow's DAG shape —
  **BREAKING** in the sense that a full run won't succeed past `images-downloader` until #17's
  credential lands (expected, not a regression — `predictor`/`trait-extractor` themselves are
  unchanged and still work identically once reached). Note the task 5 cluster-submit result, the
  updated issue #21, and leave the other deferred items (semaphore, per-run path isolation,
  image-tag lifecycle, dev-personal hostPath, Bloom trigger route, producer Argo-readiness,
  notification, empty-batch silent-green risk shared with trait-extractor/sleap-roots#259) tracked,
  not silently dropped.
