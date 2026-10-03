---
description: Generate a comprehensive PR description from the current diff, with a three-state verification checkbox convention.
---

Use this command when opening a pull request to document what changed and what was verified.

> **This repo** is declarative Argo/RunAI YAML + shell launchers with no build step (see
> `openspec/project.md`). "Verification" means the assertion suites (`/test` →
> `scripts/check_all.sh`), manifest lint (`/lint` → `scripts/lint_manifests.sh`), OpenSpec
> validation, and — for behavior only the cluster shows — a real cluster submit compared
> against a recorded red baseline.

## Quick Commands

```bash
# View current PR
gh pr view

# View PR diff
gh pr diff

# List changed files
gh pr diff --name-only

# Check CI status (none configured yet — will report no checks)
gh pr checks
```

## Checkbox Convention (READ FIRST)

Use a three-state convention for verification checkboxes — don't tick `[x]` out of habit:

- `[x]` — Verified green. You ran the command and it passed.
- `[!]` — Pre-existing issue on `main`. This PR introduces no new failure. Link the issue tracking the baseline problem.
- `[ ]` — Not yet verified, or doesn't apply.

Example:
```
- [x] `check_all.sh` passes — new assertion `predictor directs its GPU slice at the main container` seen red first (got None)
- [x] `lint_manifests.sh` passes
- [x] `openspec validate <change-id> --strict` passes
- [!] Local WSL2 dry-run not possible — `local_run_pipeline_first_time.sh` is broken for the current DAG (#21), not introduced here
- [ ] Cluster submit (not run yet — templates not registered until after merge)
```

## PR Description Template

```markdown
## Summary

[Brief 1-2 sentence description of what this PR does and why.]

## Changes

- [Bullet list of specific changes]
- [Group related changes together]
- [Use present tense: "Add X", "Fix Y", "Update Z"]

## OpenSpec Change

- Change ID: `<change-id>`
- Affected capabilities: `<capability-1>`, `<capability-2>`
- Delta types: ADDED / MODIFIED / REMOVED
- All `tasks.md` items complete: yes/no

(If this PR is too small for an OpenSpec proposal — typo, comment, image-tag bump — say "No OpenSpec change: <reason>".)

## Verification

- [ ] `uv run --no-project --with pyyaml bash scripts/check_all.sh` passes
- [ ] New/changed behavior has an assertion that was seen red before the fix (name it), or N/A
- [ ] `wsl -e bash scripts/lint_manifests.sh` passes (or N/A — no manifest changed)
- [ ] `openspec validate <change-id> --strict` passes
- [ ] Cluster (`*.yaml`) and local (`local-WSL2-*.yaml`) variants kept in sync (or N/A)
- [ ] Live acceptance: cluster submit re-run green against the recorded baseline (or stated why not / when)
- [ ] No `ARGO_TOKEN` / secrets committed or echoed

## Breaking Changes

- [ ] No breaking changes
- [ ] Breaking changes documented below with migration path

[If breaking changes — e.g. renamed WorkflowTemplate, changed mount path, new required
parameter — describe what breaks for existing runs and how to migrate.]

## Related Issues

Closes #[issue number]
Related to #[issue number]

## Reviewer Notes

[Any specific concerns, trade-offs, or areas to focus on — e.g. scheduling/quota impact,
storage-path assumptions, roadmap A4 alignment.]
```

## GitHub CLI Tips

```bash
# Create PR with heredoc body (preferred — keeps formatting)
gh pr create --title "feat: <descriptive title>" --body "$(cat <<'EOF'
## Summary
...
EOF
)"

# Create PR with body from a file
gh pr create --title "feat: ..." --body-file pr-description.md

# Edit PR description
gh pr edit --body "Updated description"
```

## Related Commands

- `/pre-merge` — run the full local gate before opening a PR
- `/review-pr` — adversarial multi-lens review of this PR
- `/copilot-review` — fetch and triage GitHub Copilot inline comments
- `/cleanup-merged` — post-merge cleanup workflow
