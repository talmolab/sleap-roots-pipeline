# Tasks

Declarative repo — a task's "test" is `argo lint`, a script/manifest field inspection, or a real
cluster submit. There is no dry-run path for `runai_run_pipeline.sh` (it registers templates and
submits a real Workflow), so the launcher's default is verified by field assertion, not execution.

## 1. Launcher namespace default

- [ ] 1.1 Change `runai_run_pipeline.sh:23` from `NAMESPACE="runai-talmo-lab"` to
  `NAMESPACE="${NAMESPACE:-runai-busch-lab}"`, with a comment stating it must match
  `sleap-roots-pipeline.yaml`'s `metadata.namespace` and showing the override form.
- [ ] 1.2 Update the stale header comment block (lines 6-13): kubeconfig filename
  `~/.kube/kubeconfig-runai-talmo-lab.yaml` → `~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml`,
  and every `-n runai-talmo-lab` in that block → `-n runai-busch-lab`.
- [ ] 1.3 Validate: `grep -n 'NAMESPACE="${NAMESPACE:-runai-busch-lab}"' runai_run_pipeline.sh`
  returns one hit, and `grep -c 'runai-talmo-lab' runai_run_pipeline.sh` returns `1` (the override
  example only).
- [ ] 1.4 Validate the two agree: the value from 1.3 equals
  `grep -m1 '^  namespace:' sleap-roots-pipeline.yaml | awk '{print $2}'`.

## 2. Delete the dead models-downloader template

- [ ] 2.1 `git rm models-downloader-template.yaml`.
- [ ] 2.2 Validate nothing references it:
  `grep -rn 'models-downloader-template' --include='*.sh' --include='*.yaml' --include='*.md' .`
  returns no hits outside `docs/superpowers/`, `openspec/changes/archive/`, and `.worktrees/`.
  Remove any live reference found in the launcher's `TEMPLATES` list or the README folder-structure
  block.

## 3. Static validation

- [ ] 3.1 Lint all five remaining manifests **online** (`argo` is WSL-only at
  `/usr/local/bin/argo`; `KUBECONFIG` must be set or `templateRef`s cannot resolve):

  ```bash
  wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
  export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
  cd /mnt/c/repos/sleap-roots-pipeline; \
  for f in sleap-roots-pipeline.yaml sleap-roots-images-downloader-template.yaml \
           sleap-roots-predictor-template.yaml sleap-roots-trait-extractor-template.yaml \
           sleap-roots-write-back-template.yaml; do echo "--- $f"; argo lint "$f"; done'
  ```

  Expected: all five clean. Without VPN, fall back to `--offline` and expect exactly one error on
  `sleap-roots-pipeline.yaml` (`couldn't find workflow template ... in namespace`) — that is an
  offline-lint artifact, not a defect; passing all five files on one command line does not resolve
  it. Any *other* error is real.

## 4. Validate and close out

- [ ] 4.1 `openspec validate fix-launcher-namespace --strict` → valid.
- [ ] 4.2 `/pr-description`; open the PR referencing this change-id. State in the body that the
  behaviour change affects hand-run launches only, citing `k8s_client.py:48-49` and `:227` as the
  evidence that Bloom's dispatch path resolves and overwrites the namespace itself.
