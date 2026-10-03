---
description: Lint the Argo manifests (check-only) — the Workflow together with every template it references
---

# Lint

Check that the Workflow and its WorkflowTemplates are valid Argo and that every `templateRef`
resolves to a file in this repo. **Check-only** — it lints a temporary copy and never modifies
the tracked files.

## Command

```bash
# From the repo root, in PowerShell or Git Bash — argo is installed only in WSL
wsl -e bash scripts/lint_manifests.sh
```

Expect `✔ no linting errors found!`. Exit `127` means `argo` is not on the PATH of the shell the
script ran in — see `.claude/skills/runai/SKILL.md` §1a for where it lives.

## Why the wrapper, not bare `argo lint`

Bare `argo lint --offline sleap-roots-pipeline.yaml sleap-roots-*-template.yaml` reports
`couldn't find workflow template …` on this valid tree — a namespace mismatch between the
Workflow and the templates. The wrapper lints a temp copy without it. The full explanation, and
why the real file must keep its `metadata.namespace`, is in the `scripts/lint_manifests.sh`
header and `openspec/project.md` (Testing Strategy).

## What lint does and does not catch

| Catches | Does not catch |
|---|---|
| Argo schema errors | this repo's conventions (priority classes, quota labels, retry shape, pins) — `/test` |
| a DAG task whose `templateRef` has no matching file here | what is **registered** in the cluster — `wsl -e bash scripts/check_cluster_drift.sh` (`NOT REGISTERED`) |

There is no formatter, type checker, or shell linter configured in this repo.

## Related Commands

- `/test` — the assertion suites (`check_all.sh`)
- `/pre-merge` — full gate before opening a PR
- `/ci-debug` — debug a failing Argo workflow run
