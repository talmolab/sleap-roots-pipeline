# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a WSL2 dry-run
(no pytest). Full rationale + deferred items in `design.md` and
`docs/superpowers/specs/2026-07-28-a4-batch-stage-write-back-design.md`.

## 1. Images-downloader template (new)

- [ ] 1.1 Create `sleap-roots-images-downloader-template.yaml`: image
  `ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd`; `args: ["cyl",
  "batch-download-for-predict", "/workspace/images_input", "--scan-ids",
  "{{workflow.parameters.scan-ids}}"]`; `env: [{name: HOME, value: /home/bloom}]`; mounts
  `images-input-dir` at `/workspace/images_input` and a `bloom-credentials` Secret at
  `/home/bloom/.bloom/credentials.txt` (`subPath: credentials.txt`, `readOnly: true`);
  `priorityClassName: interactive-preemptible`; `retryStrategy` (limit 2); no
  `privileged`/`runAsUser: 0`.
- [ ] 1.2 `argo lint --offline sleap-roots-images-downloader-template.yaml` → no errors.

## 2. Write-back template (new)

- [ ] 2.1 Create `sleap-roots-write-back-template.yaml`: same image/env/credential-mount pattern as
  1.1; `args: ["cyl", "batch-ingest-result", "/workspace/input", "--predictions-dir",
  "/workspace/predictions"]`; mounts `traits-output-dir` at `/workspace/input` and
  `predictions-output-dir` at `/workspace/predictions`.
- [ ] 2.2 `argo lint --offline sleap-roots-write-back-template.yaml` → no errors.

## 3. DAG rewrite

- [ ] 3.1 Edit `sleap-roots-pipeline.yaml`: add `arguments.parameters: [{name: scan-ids, value:
  ""}]`; add a `bloom-credentials` Secret volume (`secretName: bloom-pipeline-credentials`); add
  `images-downloader` as the DAG root and `write-back` as the final task; `predictor` depends on
  `images-downloader`; `write-back` depends on `trait-extractor`. Existing `images-input-dir`/
  `predictions-output-dir`/`traits-output-dir` hostPath volumes unchanged.
- [ ] 3.2 Inspect the DAG's `tasks` list: confirm exactly four tasks and the dependency chain
  matches `images-downloader → predictor → trait-extractor → write-back` (manifest-field check,
  matching `per-batch-pipeline`'s "Four-stage per-batch DAG" scenario).
- [ ] 3.3 `argo lint --offline sleap-roots-pipeline.yaml` → no errors (note: offline lint cannot
  cross-resolve `templateRef`s against unregistered `WorkflowTemplate` files — full cross-resolution
  happens after `argo template create`/`kubectl apply`, in task 6).

## 4. Launcher

- [ ] 4.1 Edit `runai_run_pipeline.sh`: add `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` to the registered `TEMPLATES` list.
- [ ] 4.2 Inspect `TEMPLATES`: confirm it lists all four template files (matching
  `per-batch-pipeline`'s "Launcher registers all four templates" scenario).

## 5. Local WSL2 parity

- [ ] 5.1 Edit `local-WSL2-sleap-roots-pipeline.yaml`: drop the stale leftover `models-downloader`
  task and its `models-input-dir`/`models-output-dir` volumes (left over from before the cluster
  side dropped this stage); add `images-downloader`/`write-back` tasks matching the cluster DAG's
  dependency chain; add the `scan-ids` parameter.
- [ ] 5.2 Create `local-WSL2-sleap-roots-images-downloader-template.yaml` and
  `local-WSL2-sleap-roots-write-back-template.yaml`: same `bloomctl` image/args as the cluster
  templates, but the credential volume is a `hostPath` bind-mount of a real local
  `~/.bloom/credentials.txt` (not a Kubernetes Secret) — mirror `mount/path parity, not template
  names`, per this repo's own local-vs-cluster convention (`openspec/project.md`).
- [ ] 5.3 `argo lint --offline` on both new local template files and the edited local pipeline file
  → no errors.

## 6. Real local WSL2 dry-run (primary acceptance gate)

- [ ] 6.1 Register the four local templates (`kubectl apply -f <file> -n argo` per
  `local_run_pipeline_first_time.sh`'s existing pattern) and confirm `images-downloader` actually
  authenticates using the bind-mounted `~/.bloom/credentials.txt` and stages real frames for a real
  scan-id.
- [ ] 6.2 Submit the local Workflow with a real `scan-ids` value (`argo submit
  local-WSL2-sleap-roots-pipeline.yaml --parameter scan-ids=<real-scan-id> -n argo`); confirm all
  four DAG nodes go green and `write-back` reports a successful (or idempotent-skip) ingest.
  Record the run result here once done.
- [ ] 6.3 Separately, confirm `batch-download-for-predict --scan-ids ""` (the parameter's empty
  default) behaves as "empty input → exit 0," not a CLI parse error — determines whether an
  unparameterized dry-submit is a safe sanity check going forward. Note the actual behavior found.

## 7. Validate + close out

- [ ] 7.1 `openspec validate add-per-batch-argo-workflow --strict` → valid.
- [ ] 7.2 Re-lint all touched/new manifests (cluster + local) offline, clean.
- [ ] 7.3 `/pr-description`; open PR referencing A4 EPIC (talmolab/sleap-roots-pipeline#10) and this
  change-id; note the WSL2 dry-run result; leave the deferred items (semaphore, per-run path
  isolation, image-tag lifecycle, dev-personal hostPath, Bloom trigger route, producer
  Argo-readiness, notification) tracked, not silently dropped.
