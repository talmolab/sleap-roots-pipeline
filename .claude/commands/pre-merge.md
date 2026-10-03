---
description: Full pre-merge gate — assertion suites, manifest lint, OpenSpec, docs — with PR creation and review triage.
---

Run every local check, create or update the PR, and prepare for merge. This repo has no CI
(no `.github/workflows/`), so **nothing runs these checks unless you do**.

## Phase 1: Tests

1. **Assertion suites.** Run `/test` (from Git Bash — see `/test` for why not PowerShell).
   Every assertion must pass. Every behavior the branch changes should have an assertion that
   was seen red first (`/tdd`) — check that the branch adds one, or say why not.

## Phase 2: Lint

2. **Manifest lint.** Run `/lint` (required if any `*.yaml` manifest changed).

## Phase 3: Live acceptance (only if the change claims live behavior)

3. **Pre-merge evidence.** If the change claims something only the cluster shows (GPU
   allocation, scheduling, quota), confirm the red baseline is recorded and — if a pre-merge
   probe was run — that it used a throwaway Workflow with the edited template **inlined**.
   **Do not register templates from this branch**: `runai-busch-lab` is shared by Bloom
   staging and production. Registration and the green re-run happen after merge, from `main`
   (`/tdd`, "Live acceptance tests"); list them in the PR as `[ ]` post-merge items.

## Phase 4: Documentation

4. **Docs review.** Run `/docs-review` if the change touches README, `openspec/project.md`,
   `docs/bloom-integration/roadmap.md`, or a claim the docs repeat (template names, mount paths,
   image pins, namespaces). `check_docs.py` covers only the claims it asserts; it is not a full
   review.

## Phase 5: OpenSpec Verification

5. **Check proposal status** (if this branch has an active OpenSpec change):
   ```bash
   openspec list
   openspec validate <change-id> --strict
   openspec validate --all --strict
   ```
   - Verify `openspec/changes/<change-id>/tasks.md` — all items should be `- [x]`, or the open
     ones are explicitly post-merge (e.g. a live deploy) and named in the PR.
   - After merge, archive via `/cleanup-merged` (uses the CLI — never a manual `git mv`).

## Phase 6: Pull Request

6. **Create or update the PR.**
   - Run `/pr-description` to generate the PR body.
   - Push and create it:
     ```bash
     git push -u origin $(git branch --show-current)
     gh pr create --base main --head $(git branch --show-current) \
       --title "<type>: <descriptive title>" --body-file <body.md>
     ```

## Phase 7: Review Feedback

7. **Triage Copilot comments.** Run `/copilot-review`.
8. **Adversarial review.** Run `/review-pr <PR#>` and address every BLOCKING and IMPORTANT finding.
9. **Plan fixes for complex issues** with `superpowers:brainstorming`; fix test-first, push, and
   re-run Phases 1–2.

## Phase 8: Changelog

10. **Update changelog.** Run `/update-changelog` if the change is user-visible.

## Phase 9: Final Verification

11. **Final gate** (Git Bash — `/test` + `/lint` + OpenSpec in one line):
    ```bash
    git fetch origin main
    git merge-base --is-ancestor origin/main HEAD && echo "up to date with main"
    uv run --no-project --with pyyaml bash scripts/check_all.sh && wsl -e bash scripts/lint_manifests.sh && openspec validate --all --strict
    ```

## Output Format

```markdown
## Pre-Merge Check Results

- [x/!/ ] Tests (check_all.sh): N + M assertions pass; new assertions seen red first
- [x/!/ ] Lint (lint_manifests.sh): PASS / N/A (no manifest changed)
- [x/!/ ] Live acceptance: baseline recorded; inlined probe green / post-merge (listed in PR) / N/A
- [x/!/ ] Docs: current / updated
- [x/!/ ] OpenSpec: all tasks complete / N/A
- [x/!/ ] PR: #N created/updated
- [x/!/ ] Copilot + review-pr: no blockers / X addressed
- [x/!/ ] Changelog: updated / N/A

Status: READY TO MERGE
```

`[!]` = a pre-existing problem on `main`, not introduced here — link its issue.

Merge command:
```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
```

Post-merge: merging does **not** update the cluster. If templates changed, register them from
`main` by hand — `argo template update`, or `create` for a template that doesn't exist yet — with
the drift check and rollback copy in `/tdd` ("Live acceptance tests"). If the Workflow's
`volumes`, `entrypoint`, `serviceAccountName` or DAG changed, also update Bloom's vendored copy
and pin (see the header of `sleap-roots-pipeline.yaml`). Then run `/cleanup-merged`.

## When to Skip Phases

Say why when you skip one:

- **Docs-only PR** — skip lint and live acceptance; still run `/test` (`check_docs.py` asserts on docs).
- **Image-pin bump** — skip live acceptance only if the producing repo's own tests cover the image.

## Related Commands

- `/test` — assertion suites
- `/lint` — manifest lint
- `/tdd` — red → green loop
- `/docs-review` — documentation review
- `/copilot-review` — triage GitHub Copilot inline comments
- `/review-pr` — adversarial multi-lens PR review
- `/update-changelog` — maintain the changelog
- `/pr-description` — generate the PR body
- `/cleanup-merged` — post-merge branch cleanup + OpenSpec archive
