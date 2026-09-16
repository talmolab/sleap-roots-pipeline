## Why

`runai_run_pipeline.sh:23` hardcodes `NAMESPACE="runai-talmo-lab"`, but the Workflow it submits
declares `metadata.namespace: runai-busch-lab` (`sleap-roots-pipeline.yaml:28`). This pipeline has
targeted busch-lab only since 2026-08-13. So a hand-run launcher registers all four
WorkflowTemplates into, and submits against, the wrong namespace — silently, because both
namespaces are real and the operator's `argo-user` identity has rights in each.

The launcher's namespace is not covered by any existing requirement. The spec's
`Launcher registers all four templates` asserts only the contents of its `TEMPLATES` list, so
nothing today prevents the launcher and the manifest disagreeing about where the pipeline runs.

**Bloom's dispatch path is unaffected**, verified rather than assumed:

- `salk-bloom` contains zero references to `runai_run_pipeline.sh` (grep across `*.py`, `*.yml`,
  `*.yaml`, `*.md`). Bloom's `dispatch_worker.py` POSTs Workflow CRDs to the Kubernetes API
  directly; it never invokes this script.
- `services/workflows/k8s_client.py:48-49` resolves the namespace from `WORKFLOWS_K8S_NAMESPACE`
  (defaulting to `runai-busch-lab`) and then *overwrites* `body["metadata"]["namespace"]` at line
  227, because the Kubernetes API rejects a submission whose body namespace disagrees with the
  URL's namespace segment. Even this repo's `metadata.namespace` does not reach Bloom.

So this is an operator-path-only change.

Separately, `models-downloader-template.yaml` is dead. The DAG is `images-downloader` →
`predictor` → `trait-extractor` → `write-back`; the launcher does not register a
models-downloader template, and the spec's four-template requirement excludes it. The file carries
a stale `project: talmo-lab` label and has no consumer.

## What Changes

- Change `runai_run_pipeline.sh`'s namespace from `runai-talmo-lab` to `runai-busch-lab`, as a
  plain literal. An env-var override was drafted and removed: `argo submit -n <ns>` does not
  redirect a submission (verified — `--server-dry-run -n runai-talmo-lab` still yields
  `metadata.namespace = runai-busch-lab`), so an override could only have moved the template
  registrations away from the namespace the Workflow still runs in.
- Update that script's stale header comment block (lines 6-13), which instructs the reader to
  export `~/.kube/kubeconfig-runai-talmo-lab.yaml` and run every `argo template update` against
  `-n runai-talmo-lab`.
- Delete `models-downloader-template.yaml`.

**BREAKING**: none for automated dispatch (see Why). For a human running the launcher, the target
namespace changes from `runai-talmo-lab` to `runai-busch-lab` — which is the correction, not a
regression: submitting into talmo-lab was already wrong for this pipeline, and the Workflow it
submits has declared `runai-busch-lab` all along. Anyone who genuinely needs another project must
edit `metadata.namespace` in the manifest and register that project's templates and secrets first;
there is deliberately no environment-variable shortcut, because one cannot work (see What Changes).

## Impact

- **Modified capability:** `per-batch-pipeline` — the `Launcher registers all four templates`
  requirement gains a namespace assertion and one new scenario.
- **⚠️ Delta collision, coordinated:** PR #60 (issue #56, exit-code gate) RENAMES this same
  requirement to `Launcher registers every workflow template` and adds a fifth template. Agreed
  with that session: **#60 merges first**, then this delta is rebased onto the renamed requirement
  so the archiver does not end up with an orphan.
- **Affected code:** `runai_run_pipeline.sh`; `models-downloader-template.yaml` (deleted).
- **Shipped in the same PR but outside this change's scope** (documentation and hygiene, no
  orchestration behaviour): `docs/cluster-identities.md` (new), `README.md`, `openspec/project.md`,
  `.gitignore`, `bloom-pipeline-serviceaccount.yaml` (comments only),
  `.claude/commands/{ci-debug,docs-review,review-openspec,review-pr}.md`,
  `.claude/skills/runai/SKILL.md`, `openspec/specs/per-batch-pipeline/spec.md` (stale
  `project: talmo-lab` label corrected), and two `docs/superpowers/` files.
- **Untouched:** `sleap-roots-pipeline.yaml` (already correct), all four
  `sleap-roots-*-template.yaml` files, and every `local-WSL2-*` variant — the local Docker-Desktop
  DAG still runs its own models-downloader stage, tracked as
  [#61](https://github.com/talmolab/sleap-roots-pipeline/issues/61).
- **No external prerequisite.** All four WorkflowTemplates are already registered in
  `runai-busch-lab`, and `argo lint sleap-roots-pipeline.yaml` passes clean against that namespace
  (verified live 2026-09-15 under the `argo-user` kubeconfig).
