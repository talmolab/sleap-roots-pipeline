---
description: Verify the development environment can run this repo's checks
---

# Validate Development Environment

Check that the tools this repo's commands rely on are present. Run after cloning, after
switching machines, or when `/test` or `/lint` fails unexpectedly.

This repo has no package manifest or lockfile — there is nothing to install. The checks below
are for the tools that drive the scripts. **Run them from Git Bash** (in PowerShell, `bash` is
the WSL launcher — see `/test`).

## Checks

```bash
# 1. Right shell: bash must be Git Bash, not the WSL launcher (System32\bash.exe)
uname -s                     # expect MINGW64_NT-…, not Linux

# 2. uv — runs the assertion suites in an isolated interpreter (never pip install into base)
uv --version

# 3. The assertion suites run on uv's interpreter (needs only uv; PyYAML is fetched by uv)
uv run --no-project --with pyyaml bash -c 'command -v python'   # expect …/uv/cache/…, not /usr/bin
uv run --no-project --with pyyaml bash scripts/check_all.sh     # = /test

# 4. OpenSpec CLI (global install)
openspec --version
openspec validate --all --strict

# 5. GitHub CLI authenticated (for /pr-description, /copilot-review, /review-pr)
gh auth status
gh repo view --json nameWithOwner -q .nameWithOwner

# 6. argo in WSL (for /lint) — argo is not installed on Windows
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; argo version --short'
wsl -e bash scripts/lint_manifests.sh                           # = /lint

# 7. Cluster identities (only for check_cluster_drift.sh, argo submit, kubectl) — existence
#    only, never print a kubeconfig or token. argo-user = operator actions; bloom-pipeline =
#    pod logs (argo-user cannot read them). See docs/cluster-identities.md.
wsl -e bash -c 'for k in runai-busch-lab-argo-user bloom-pipeline-busch-lab; do test -s ~/.kube/kubeconfig-$k.yaml && echo "$k kubeconfig present" || echo "$k kubeconfig MISSING"; done'
```

## Common fixes

| Symptom | Fix |
|---|---|
| `uname -s` says `Linux`, or `check_manifests.py` FAILs `gate accepts every all-{0,3} combination` | you're running from PowerShell/cmd, where `bash` is WSL — use Git Bash (`/test`) |
| `uv` not found | install uv (see https://docs.astral.sh/uv/) |
| `ModuleNotFoundError: yaml` | you ran the script with the base Python — use the `uv run --no-project --with pyyaml` form, from Git Bash |
| `openspec` not found | `npm install -g @fission-ai/openspec` |
| `gh` not authenticated | `gh auth login` |
| `lint_manifests.sh` exits `127` | `argo` isn't on the WSL PATH — see `.claude/skills/runai/SKILL.md` §1a |
| kubeconfig missing | see `.claude/skills/runai/SKILL.md` and `docs/cluster-identities.md` for which identity to use |
| `wsl: Processing /etc/fstab with mount -a failed.` | harmless WSL startup noise; ignore if the command's own output follows |
| `Wsl/Service/WSAETIMEDOUT` on a cluster call | WSL or VPN networking; check VPN, retry, or `wsl --shutdown` and retry |

## Related Commands

- `/test` — assertion suites
- `/lint` — manifest lint
