# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit (no pytest, no local WSL2 dry-run — see task 6 for why). Full rationale + deferred items in
`design.md` and `docs/superpowers/specs/2026-07-28-a4-batch-stage-write-back-design.md`.

## 1. Images-downloader template (new)

- [ ] 1.1 Create `sleap-roots-images-downloader-template.yaml`: image
  `ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd`; `args: ["cyl",
  "batch-download-for-predict", "/workspace/images_input", "--scan-ids",
  "{{workflow.parameters.scan-ids}}"]`; `env: [{name: HOME, value: /home/bloom}]`; mounts
  `images-input-dir` at `/workspace/images_input` and a `bloom-credentials` Secret at
  `/home/bloom/.bloom/credentials.txt` (`subPath: credentials.txt`, `readOnly: true`);
  `labels: {project: talmo-lab}` (matches `predictor`/`trait-extractor`'s RunAI quota
  attribution); `priorityClassName: interactive-preemptible`; `retryStrategy` (limit 2); no
  `privileged`/`runAsUser: 0`.
- [ ] 1.2 `argo lint --offline sleap-roots-images-downloader-template.yaml` → no errors.
- [ ] 1.3 Inspect the template: confirm the image tag is `sha-61959bd` (not `:latest`), `HOME` is
  set, the Secret is mounted at exactly `$HOME/.bloom/credentials.txt`, and `labels.project` is
  `talmo-lab` — matching `per-batch-pipeline`'s "Images-downloader stages a batch via bloomctl" and
  "bloomctl-based tasks pin their image and mount credentials deterministically" scenarios.

## 2. Write-back template (new)

- [ ] 2.1 Create `sleap-roots-write-back-template.yaml`: same image/env/credential-mount/label
  pattern as 1.1; `args: ["cyl", "batch-ingest-result", "/workspace/input", "--predictions-dir",
  "/workspace/predictions"]`; mounts `traits-output-dir` at `/workspace/input` and
  `predictions-output-dir` at `/workspace/predictions`.
- [ ] 2.2 `argo lint --offline sleap-roots-write-back-template.yaml` → no errors.
- [ ] 2.3 Inspect the template: same checks as 1.3, plus confirm both `traits-output-dir` and
  `predictions-output-dir` are mounted — matching `per-batch-pipeline`'s "Write-back ingests a
  batch via bloomctl" scenario.

## 3. DAG rewrite

- [ ] 3.1 Edit `sleap-roots-pipeline.yaml`: add `arguments.parameters: [{name: scan-ids, value:
  ""}]`; add a `bloom-credentials` Secret volume (`secretName: bloom-pipeline-credentials`); add
  `images-downloader` as the DAG root and `write-back` as the final task; `predictor` depends on
  `images-downloader`; `write-back` depends on `trait-extractor`.
- [ ] 3.2 In the same edit, change `images-input-dir`'s `hostPath.type` from `Directory` to
  `DirectoryOrCreate`, and update its comment: it no longer requires manual pre-staging —
  `images-downloader` now writes there automatically, and `type: Directory` would `FailedMount` on
  a path nothing has staged into yet. `predictions-output-dir`/`traits-output-dir` are otherwise
  unchanged (already `DirectoryOrCreate`).
- [ ] 3.3 Inspect the DAG's `tasks` list: confirm exactly four tasks and the dependency chain
  matches `images-downloader → predictor → trait-extractor → write-back` (manifest-field check,
  matching `per-batch-pipeline`'s "Four-stage per-batch DAG" scenario).
- [ ] 3.4 Cross-check `templateRef` resolution by hand (offline `argo lint` cannot catch a
  name/field mismatch here — it only validates each file's own schema): diff the two new tasks'
  `templateRef.name`/`template` values in `sleap-roots-pipeline.yaml` against the `metadata.name`/
  `spec.templates[].name` actually set in `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml`. Confirm exact string matches.
- [ ] 3.5 `argo lint --offline sleap-roots-pipeline.yaml` → no errors (note: doesn't cross-resolve
  `templateRef`s — that's what 3.4 and task 6 are for).

## 4. Launcher

- [ ] 4.1 Edit `runai_run_pipeline.sh`: add `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` to the registered `TEMPLATES` list.
- [ ] 4.2 Inspect `TEMPLATES`: confirm it lists all four template files (matching
  `per-batch-pipeline`'s "Launcher registers all four templates" scenario).

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
  right) and `images-downloader` schedules and starts. Its `bloomctl` auth is **expected to fail**
  until the credential from sleap-roots-pipeline#17 lands (tracked separately, in progress) — a
  clean `bloomctl` auth error here means the wiring is correct, not broken. If the credential
  happens to be ready by test time, confirm a full successful run instead. Record which outcome
  actually happened.
- [ ] 5.4 Confirm `batch-download-for-predict --scan-ids ""` (the parameter's empty default)
  behavior matches what the source implies (`parse_scan_ids_flag("")` → `[]` → exit 0, "nothing to
  stage," not a CLI parse error) — submit once with no `scan-ids` override and record the actual
  result. This determines whether an unparameterized submit is a safe no-op going forward.

## 6. Validate + close out

- [ ] 6.1 `openspec validate add-per-batch-argo-workflow --strict` → valid.
- [ ] 6.2 Re-lint all touched/new cluster manifests offline, clean.
- [ ] 6.3 `/pr-description`; open PR referencing A4 EPIC (talmolab/sleap-roots-pipeline#10) and this
  change-id. Note: this change replaces the working manual `argo submit` flow's DAG shape —
  **BREAKING** in the sense that a full run won't succeed past `images-downloader` until #17's
  credential lands (expected, not a regression — `predictor`/`trait-extractor` themselves are
  unchanged and still work identically once reached). Note the task 5 cluster-submit result, the
  updated issue #21, and leave the other deferred items (semaphore, per-run path isolation,
  image-tag lifecycle, dev-personal hostPath, Bloom trigger route, producer Argo-readiness,
  notification, empty-batch silent-green risk shared with trait-extractor/sleap-roots#259) tracked,
  not silently dropped.
