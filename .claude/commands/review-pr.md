---
description: Adversarial multi-lens PR review — subagent team posts a structured verdict to GitHub
---

# PR Code Review — Subagent Team

You are a senior engineer reviewing a pull request for this repo (`$REPO`, resolved in Step 1).
You value orchestration correctness, test discipline, reproducibility, cluster safety, and
maintainable declarative YAML above all else.

This command launches **5 specialized subagents in parallel** to critically review the PR.
Each subagent has a distinct review lens and is instructed to be adversarial — finding gaps,
not rubber-stamping. After all subagents return, synthesize findings into a unified review
and act based on the mode determined in Step 1.

**Arguments:** `$ARGUMENTS` (optional PR number; if omitted, reviews the current branch)

## Step 0: Review Lenses (this repo)

This is a declarative **Argo Workflows / Argo Events / RunAI** orchestration repo (no
application code; the test harness is `scripts/check_manifests.py` + `scripts/check_docs.py`,
run by `/test` — see `openspec/project.md`). Use these 5 domain lenses. For a PR that touches no
manifests (commands/docs only), keep five subagents but point lenses 1–3 at what that PR can
actually break (e.g. template fidelity, whether documented commands run, cross-doc consistency)
and say so in the review footer.

1. **Argo Workflow & Template Correctness** — DAG `dependencies` order; `templateRef`
   name/template wiring; `entrypoint`; `retryStrategy` on preemption-prone steps; manifest
   validity (`wsl -e bash scripts/lint_manifests.sh`). NB: this pipeline passes data **via shared volume mounts, not
   Argo parameters/artifacts** — verify output-mount(stage N) == input-mount(stage N+1)
   rather than hunting for param wiring.
2. **RunAI / Kubernetes Scheduling & Resources** — `gpu-fraction`, `nvidia.com/gpu` on the
   predictor only; `namespace` (`runai-busch-lab`) / `project` (`busch-lab`) quota. NB:
   preemptibility is governed by `priorityClassName` (`interactive-preemptible` < 100 =
   preemptible), **not** the `preemptible: "true"` annotation the templates carry.
3. **Storage & Volume Integrity** — `hostPath type: Directory` paths that must pre-exist
   (cluster: `/hpi/hpi_dev/...`); mount-path agreement between stages; **cluster (`*.yaml`)
   ↔ local (`local-WSL2-*.yaml`) *path* parity**. The locals are CPU-only counterparts with
   deliberately different template names/retry/no-GPU — reconcile mounts/paths, not template
   names (PV/PVC is local-test-only).
4. **Tests & TDD Discipline** — every behavior the PR changes has a `check(...)` in
   `scripts/check_manifests.py` / `scripts/check_docs.py` that fails without the fix (revert the
   fix and confirm — the commit body should quote the red FAIL line); `/test` passes from Git
   Bash; negative cases asserted, not only the happy value; live-only claims cite a recorded
   baseline, and no template was registered from the unmerged branch (`/tdd`); OpenSpec
   `tasks.md` was red-first.
5. **Reproducibility, Docs Accuracy & Shell-Script Safety** — image tags/digests pinned (never
   `:latest`); model versions; idempotency / re-delivery (roadmap A4 in
   `docs/bloom-integration/roadmap.md`); README/`openspec/project.md` still accurate (grep for
   each changed claim repo-wide); run scripts use `set -euo pipefail`; **no `ARGO_TOKEN` /
   secret leakage** into logs or committed files; safe failure handling.

## Step 1: Determine Mode

**Mode A — PR number provided** (`$ARGUMENTS` is a number):
- Gather PR context from GitHub and post a review verdict.

**Mode B — No PR / branch provided** (`$ARGUMENTS` is empty or a branch name):
- Compare against the merge base: `git diff $(git merge-base HEAD main)..HEAD`
- Report findings only; do not post to GitHub.

Resolve the repo for GitHub calls:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
# → use "$REPO" in all gh commands; never hardcode the owner/name
```

## Step 2: Gather Context

Run in parallel:

```bash
# Mode A only — PR metadata
gh pr view $PR_NUMBER --json title,body,baseRefName,headRefName,author,labels,files

# Mode A only — full diff
gh pr diff $PR_NUMBER

# Mode A only — CI status
gh pr checks $PR_NUMBER

# Mode A only — existing automated review comments
gh api graphql -f query='
query {
  repository(owner: "'"${REPO%%/*}"'", name: "'"${REPO##*/}"'") {
    pullRequest(number: '$PR_NUMBER') {
      reviews(first: 10) {
        nodes {
          author { login }
          comments(first: 50) {
            nodes { path line body }
          }
        }
      }
    }
  }
}
' --jq '.data.repository.pullRequest.reviews.nodes[].comments.nodes[] | "File: \(.path):\(.line)\n\(.body)"'

# Mode B only — branch diff against merge base
git diff $(git merge-base HEAD main)..HEAD
```

Also read any OpenSpec proposal linked in the PR body (look for `openspec/changes/` paths).

## Step 3: Launch Subagent Review Team

Launch ALL 5 subagents **in a single message** (parallel execution). Embed the full diff,
PR description, CI status, and any automated review comments in each prompt. Each subagent
MUST read the actual manifests/scripts it needs using Read/Grep tools — do not rely on
summaries.

For each subagent, construct a prompt that includes:

- The subagent's specific lens and checklist (from Step 0)
- The full PR diff (or branch diff in Mode B)
- The PR description / branch summary
- CI status (Mode A only)
- Any existing automated review comments (Mode A only)
- Instructions to read source files as needed and return findings in BLOCKING / IMPORTANT /
  SUGGESTION tiers, plus an overall score (1–10) with justification

**Subagent assignments:**

```
Subagent 1: Argo Workflow & Template Correctness
  - DAG dependencies / ordering; templateRef wiring; entrypoint; inter-stage data via
    shared volume mounts (NOT Argo params/artifacts) — output-mount(N)==input-mount(N+1);
    retryStrategy; does `wsl -e bash scripts/lint_manifests.sh` pass?

Subagent 2: RunAI / Kubernetes Scheduling & Resources
  - gpu-fraction; nvidia.com/gpu limits on the right step; namespace (runai-busch-lab) /
    project (busch-lab) quota; preemptibility via priorityClassName (interactive-preemptible),
    NOT the preemptible annotation; nothing requesting GPU that shouldn't.

Subagent 3: Storage & Volume Integrity
  - hostPath type:Directory pre-existence (cluster /hpi/hpi_dev/...); inter-stage mount-path agreement;
    cluster vs local-WSL2 manifest parity.

Subagent 4: Tests & TDD Discipline
  - each changed behavior has an assertion in check_manifests.py / check_docs.py that fails
    without the fix (revert and confirm); run /test from Git Bash; negative cases; live-only
    claims cite a recorded baseline and nothing was registered from the branch; tasks.md red-first.

Subagent 5: Reproducibility, Docs Accuracy & Shell-Script Safety
  - image tags/digests pinned (no :latest); model versions; idempotency / re-delivery;
    README / openspec/project.md accuracy (grep each changed claim repo-wide); set -euo
    pipefail; ARGO_TOKEN/secret leakage; failure handling; does the implementation match the
    PR description / linked spec?
```

## Step 4: Synthesize and Act

After ALL subagents return:

1. **Deduplicate** overlapping findings.
2. **Prioritize**:
   - **BLOCKING** — must fix before merge (broken DAG/templateRef, secret leakage, GPU on
     wrong step, manifest that fails `lint_manifests.sh`, failing `check_all.sh`, changed
     behavior with no assertion, spec mismatch)
   - **IMPORTANT** — should fix before merge (cluster/local drift, unpinned image, missing
     retryStrategy)
   - **SUGGESTION** — optional improvements
3. **Determine verdict**:
   - `APPROVE` — no blocking issues, important items are minor
   - `REQUEST_CHANGES` — any blocking issues present
   - `COMMENT` — no blocking issues but important items worth noting

**Mode A — post review to GitHub:**

> GitHub does not allow requesting changes or approving your own PRs.
> Always attempt the desired action first; if it fails with "Can not request changes on your
> own pull request" or "Can not approve your own pull request", automatically fall back to
> `--comment` with the same body and a note at the top indicating the intended verdict.

```bash
BODY="$(cat <<'EOF'
## Review Summary

[2-3 sentence overall assessment]

## Blocking Issues

[Must fix before merge — or "None"]

## Important Issues

[Should fix before merge — or "None"]

## Suggestions

[Optional improvements — or "None"]

---
*Review by Claude Code subagent team (Argo Correctness | RunAI Scheduling | Storage Integrity | Tests & TDD | Reproducibility, Docs & Script Safety)*
EOF
)"

# REQUEST_CHANGES (fall back to --comment on own-PR error):
gh pr review $PR_NUMBER --request-changes -b "$BODY" 2>&1 || \
  gh pr review $PR_NUMBER --comment -b "$(printf '> **Verdict: REQUEST_CHANGES** (posted as comment — GitHub does not allow requesting changes on your own PR)\n\n%s' "$BODY")"

# APPROVE (fall back to --comment on own-PR error):
gh pr review $PR_NUMBER --approve -b "$BODY" 2>&1 || \
  gh pr review $PR_NUMBER --comment -b "$(printf '> **Verdict: APPROVE** (posted as comment — GitHub does not allow approving your own PR)\n\n%s' "$BODY")"

# COMMENT (no fallback needed):
gh pr review $PR_NUMBER --comment -b "$BODY"
```

**Mode B — report only:**

Print the synthesized review. Do not call `gh pr review`.

5. Show the user the full synthesized review. In Mode A, also show the GitHub link.

## Related commands

- `/test`, `/lint` — run the suites and manifest lint locally before reviewing
- `/pre-merge` — full pre-merge gate
- `/review-openspec` — review the spec before reviewing the implementation PR
- `/copilot-review` — fetch and triage GitHub Copilot inline comments
- `/pr-description` — generate the PR body
