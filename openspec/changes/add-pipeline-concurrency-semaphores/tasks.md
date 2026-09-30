# Tasks: add-pipeline-concurrency-semaphores

## 1. Manifests

- [ ] 1.1 Add `sleap-roots-pipeline-semaphores.yaml`: ConfigMap `sleap-roots-pipeline-semaphores`,
  namespace `runai-busch-lab`, label `project: busch-lab`, data `pipeline-gpu: "5"`,
  `pipeline-stage-in: "5"`, with a header comment on semantics, deploy order and live retuning.
  Validate: `python -c "import yaml; yaml.safe_load(open('sleap-roots-pipeline-semaphores.yaml'))"`.
- [ ] 1.2 Add `synchronization.semaphores[{configMapKeyRef: {name: sleap-roots-pipeline-semaphores,
  key: pipeline-gpu}}]` to the `predictor` template, with a comment on the v3.6.7 semantics
  (slot held across retries and backoff; waiting node has no pod; missing key → Error).
  Validate: `bash scripts/lint_manifests.sh` (WSL, offline).
- [ ] 1.3 Same on the `images-downloader` template with key `pipeline-stage-in`.
  Validate: `bash scripts/lint_manifests.sh`.
- [ ] 1.4 Confirm `lint_manifests.sh`'s `sleap-roots-*-template.yaml` glob does not pick up the
  ConfigMap file. Validate: its "Linting N manifests" count is unchanged from `main` (6: the Workflow plus five templates).

## 2. Launcher

- [ ] 2.1 In `runai_run_pipeline.sh`, before the template loop, create the ConfigMap only if
  `kubectl get configmap sleap-roots-pipeline-semaphores -n "$NAMESPACE" --ignore-not-found -o name`
  prints nothing; abort if that `get` fails; never update it.
  Update the header's manual-steps comment to list the create step first.
  Validate: `bash -n runai_run_pipeline.sh`; task 3.1's launcher assertions.

## 3. Offline checks

- [ ] 3.1 `scripts/check_manifests.py`: assert each ADDED scenario (both refs; keys resolve; values
  are integers ≥ 1; `pipeline-gpu` ≤ 10) and the launcher
  scenario (create-if-absent before the loop; no `apply`/`replace`/`edit` of the ConfigMap).
  Validate: `bash scripts/check_all.sh` passes; then temporarily set `pipeline-gpu: "11"` and
  confirm it fails, and revert.
- [ ] 3.2 `scripts/check_cluster_drift.sh`: compare the live ConfigMap's `data` with the repo's and
  report a missing ConfigMap or a differing value as drift (exit 1). Validate: `bash -n`; live run
  in task 5.3.

## 4. Docs

- [ ] 4.1 `docs/cluster-identities.md`: add the gate, its limits and how to retune it live, next to
  the GPU-quota section. Validate: `python scripts/check_docs.py`.
- [ ] 4.2 Annotate A4 design §9 with what was built (template-level, two keys, busch-lab not
  talmo-lab). Validate: `python scripts/check_docs.py`.
- [ ] 4.3 `openspec/project.md`: drop "the Argo semaphore" from A4's still-open list, and note under
  External Dependencies that `runai_run_pipeline.sh` also needs a working `KUBECONFIG` for its
  ConfigMap step. Validate: `grep -n "semaphore" openspec/project.md` shows no still-open claim.
- [ ] 4.4 `openspec validate add-pipeline-concurrency-semaphores --strict`.

## 5. Deploy and live verification (each step needs the owner's go-ahead)

- [ ] 5.1 Confirm no `sleap-roots-pipeline` Workflow is in flight: `argo list -n runai-busch-lab`.
- [ ] 5.2 `kubectl create -f sleap-roots-pipeline-semaphores.yaml`, then `argo template update` the
  downloader and predictor templates.
- [ ] 5.3 `wsl -e bash scripts/check_cluster_drift.sh` exits 0.
- [ ] 5.4 Lock test: set both keys to `"1"` live; submit two small manual runs directly
  (`argo submit sleap-roots-pipeline.yaml --parameter scan-ids=<ids with real images> --labels
  purpose=srp98-lock-test -n runai-busch-lab`; manual runs carry no `environment` label, so refer
  to them by name or by this label, never by an unscoped selector); confirm the second run's
  downloader, then its predictor, sits `Pending` with `Waiting for
  runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/<key> lock` and has no pod; both runs
  finish `Succeeded`.
- [ ] 5.5 Restore both keys to `"5"`; re-run `check_cluster_drift.sh`, exit 0.

## 6. After merge

- [ ] 6.1 Draft the roadmap update (A4 row, Sequencing, Close-the-loop checklist) for the owner's
  approval.
- [ ] 6.2 Draft (do not file) a bloomctl follow-up issue: a deterministic 404 on stage-in should not
  be indistinguishable from a transient failure, so the downloader's retries stop spending attempts
  on it.
- [ ] 6.3 Draft (do not file) a Bloom follow-up issue: a Workflow waiting on a semaphore is
  `Running` in Argo (its step is `Pending`), so Bloom's run panel shows a queued batch as a slow
  one; surface the lock wait.
- [ ] 6.4 Draft (do not file) a follow-up to confirm the workflow-controller's service account can
  read ConfigMaps in `runai-busch-lab` (cluster-scoped RBAC is Forbidden to `argo-user`, so only
  task 5.4's live lock test evidences it), and record the result in `docs/cluster-identities.md`.
- [ ] 6.5 Draft (do not file) a follow-up to remove the unmaintained `local-WSL2-*` manifests and
  `local_run_pipeline_first_time.sh` (see #21), with the `project.md` and README references to them.
