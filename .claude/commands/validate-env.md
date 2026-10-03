---
description: Verify the development environment can run this repo's checks
---

# Validate Development Environment

Check that the tools this repo's commands rely on are present. Run after cloning, after
switching machines, or when `/test` or `/lint` fails unexpectedly.

This repo has no package manifest or lockfile — there is nothing to install. The checks below
are for the tools that drive the scripts.

## Checks

```bash
# 1. uv — runs the assertion suites in an isolated interpreter (never pip install into base)
uv --version

# 2. The assertion suites run (needs only uv + PyYAML, fetched by uv)
uv run --no-project --with pyyaml bash scripts/check_all.sh

# 3. OpenSpec CLI (global install)
openspec --version
openspec validate --all --strict

# 4. GitHub CLI authenticated (for /pr-description, /copilot-review, /review-pr)
gh auth status
gh repo view --json nameWithOwner -q .nameWithOwner

# 5. argo in WSL (for /lint) — argo is not installed on Windows
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; argo version --short'
wsl -e bash scripts/lint_manifests.sh

# 6. Cluster access (only for check_cluster_drift.sh, argo submit, kubectl) — existence only,
#    never print a kubeconfig or token
wsl -e bash -c 'test -s ~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml && echo "argo-user kubeconfig present"'
```

## Common fixes

| Symptom | Fix |
|---|---|
| `uv` not found | install uv (see https://docs.astral.sh/uv/) |
| `ModuleNotFoundError: yaml` | you ran the script with the base Python — use the `uv run --no-project --with pyyaml` form |
| `openspec` not found | `npm install -g @fission-ai/openspec` |
| `gh` not authenticated | `gh auth login` |
| `lint_manifests.sh` exits `127` | `argo` isn't on the WSL PATH — see `.claude/skills/runai/SKILL.md` §1a |
| kubeconfig missing | see `.claude/skills/runai/SKILL.md` and `docs/cluster-identities.md` for which identity to use |
| `wsl: Processing /etc/fstab with mount -a failed.` | harmless WSL startup noise; ignore if the command's own output follows |

## Related Commands

- `/test` — assertion suites
- `/lint` — manifest lint
