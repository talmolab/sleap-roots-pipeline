# Tasks

Declarative repo — a task's "test" is `argo lint`, a script/manifest field inspection, or a real
cluster submit.

`runai_run_pipeline.sh` has no dry-run flag of its own — running it registers/updates all four
WorkflowTemplates and submits a real Workflow, and since `runai-busch-lab` is shared by Bloom
staging and production, an `argo template update` there is not a side effect to trigger casually.
(`argo submit` does support `--dry-run`/`--server-dry-run`; `argo template create` supports
neither, which is what blocks a full dry run.)

It can still be **observed safely** by putting a stub `argo` first on `PATH`, which makes every
argo call a no-op and lets the script run end to end. That is how task 1.3/1.4 below were
verified — by execution, not just by field assertion:

```bash
S=$(mktemp -d); printf '#!/bin/bash
echo "[stub] argo $*"
exit 0
' > "$S/argo"; chmod +x "$S/argo"
PATH="$S:$PATH" ARGO_TOKEN=stub ./runai_run_pipeline.sh          # expect: runai-busch-lab
PATH="$S:$PATH" NAMESPACE=runai-talmo-lab ./runai_run_pipeline.sh  # expect: runai-talmo-lab
rm -f workflow_logs_*.txt   # the script writes one per run
```

## 1. Launcher namespace default

- [x] 1.1 Change `runai_run_pipeline.sh:23` from `NAMESPACE="runai-talmo-lab"` to
  `NAMESPACE="${NAMESPACE:-runai-busch-lab}"`, with a comment stating it must match
  `sleap-roots-pipeline.yaml`'s `metadata.namespace` and showing the override form.
- [x] 1.2 Update the stale header comment block (lines 6-13): kubeconfig filename
  `~/.kube/kubeconfig-runai-talmo-lab.yaml` → `~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml`,
  and every `-n runai-talmo-lab` in that block → `-n runai-busch-lab`.
- [x] 1.3 Validate: `grep -n 'NAMESPACE="${NAMESPACE:-runai-busch-lab}"' runai_run_pipeline.sh`
  returns one hit, and `grep -c 'runai-talmo-lab' runai_run_pipeline.sh` returns `1` (the override
  example only).
- [x] 1.4 Validate the two agree: the value from 1.3 equals
  `grep -m1 '^  namespace:' sleap-roots-pipeline.yaml | awk '{print $2}'`.
- [x] 1.5 Validate by **execution** with a stub `argo` (see header). Confirmed 2026-09-15: with
  no `NAMESPACE` set the script prints `Using namespace: runai-busch-lab` and every argo call
  carries `-n runai-busch-lab`; with `NAMESPACE=runai-talmo-lab` both switch to talmo-lab. Both
  spec scenarios exercised for real.
- [x] 1.6 Found while doing 1.5: `workflow_logs_*.txt` (written once per run, documented in the
  README's folder structure) was not gitignored. Added, since these hold streamed `argo logs`
  output.

## 2. Delete the dead models-downloader template

- [x] 2.1 `git rm models-downloader-template.yaml`.
- [x] 2.2 Validate nothing in the **cluster path** references it:
  `grep -rn 'models-downloader-template' --include='*.sh' --include='*.yaml' --include='*.md' .`
  **Actual result:** two live hits remain, both deliberate —
  `local-WSL2-models-downloader-template.yaml:4` (`metadata.name: models-downloader-template`) and
  `local-WSL2-sleap-roots-pipeline.yaml:41` (a `templateRef` to it). Those are the separate
  Docker-Desktop path in namespace `argo`, which still runs a models-downloader stage; the deletion
  does not affect them and in fact removes a `metadata.name` collision between the two files. The
  local↔cluster divergence is tracked as
  [#61](https://github.com/talmolab/sleap-roots-pipeline/issues/61). Neither launcher's `TEMPLATES`
  list nor the README folder-structure block ever referenced the deleted file.

## 3. Static validation

- [x] 3.1 Lint all five remaining manifests **online** (`argo` is WSL-only at
  `/usr/local/bin/argo`; `KUBECONFIG` must be set or `templateRef`s cannot resolve):

  ```bash
  wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
  export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
  cd /mnt/c/repos/sleap-roots-pipeline; \
  for f in sleap-roots-pipeline.yaml sleap-roots-images-downloader-template.yaml \
           sleap-roots-predictor-template.yaml sleap-roots-trait-extractor-template.yaml \
           sleap-roots-write-back-template.yaml; do echo "--- $f"; argo lint "$f"; done'
  ```

  Expected: all five clean.

  **Cluster-free alternative (preferred — no VPN needed).** Offline lint matches `templateRef` on
  (namespace, name); the Workflow declares `namespace: runai-busch-lab` and the templates declare
  none, so the lookup misses. Strip it from a temp copy and all five resolve:

  ```bash
  T=$(mktemp -d); cp sleap-roots-*.yaml "$T/"
  sed -i '/^  namespace: runai-busch-lab$/d' "$T/sleap-roots-pipeline.yaml"
  argo lint --offline "$T"/sleap-roots-*.yaml     # -> no linting errors found!
  ```

  Never strip that line from the real file. Any error other than the namespace miss is real.

  **Result 2026-09-15:** all five `no linting errors found!` against `runai-busch-lab` under the
  `argo-user` kubeconfig, including `sleap-roots-pipeline.yaml`.

## 4. Validate and close out

- [x] 4.1 `openspec validate fix-launcher-namespace --strict` → valid.
- [ ] 4.2 `/pr-description`; open the PR referencing this change-id. State in the body that the
  behaviour change affects hand-run launches only, citing `k8s_client.py:48-49` and `:227` as the
  evidence that Bloom's dispatch path resolves and overwrites the namespace itself.
