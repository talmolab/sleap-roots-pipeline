---
description: Adversarial multi-lens PR review — subagent team posts a structured verdict to GitHub
---

# PR Code Review — Subagent Team

You are a senior engineer reviewing a pull request for `talmolab/sleap-roots-pipeline`. You
value orchestration correctness, reproducibility, cluster safety, and maintainable declarative
YAML above all else.

This command launches **5 specialized subagents in parallel** to critically review the PR.
Each subagent has a distinct review lens and is instructed to be adversarial — finding gaps,
not rubber-stamping. After all subagents return, synthesize findings into a unified review
and act based on the mode determined in Step 1.

**Arguments:** `$ARGUMENTS` (optional PR number; if omitted, reviews the current branch)

## Step 0: Review Lenses (this repo)

This is a declarative **Argo Workflows / Argo Events / RunAI** orchestration repo (no
application code, no test suite — see `openspec/project.md`). Use these 5 domain lenses:

1. **Argo Workflow & Template Correctness** — DAG `dependencies` order; `templateRef`
   name/template wiring; `entrypoint`; parameter/artifact passing between stages;
   `retryStrategy` on preemption-prone steps; manifest validity (`argo lint`).
2. **RunAI / Kubernetes Scheduling & Resources** — `gpu-fraction`, `preemptible`
   annotations; `resources.limits.nvidia.com/gpu`; `namespace` (`runai-talmo-lab`);
   `project` label (quota); GPU only on the predictor step.
3. **Storage & Volume Integrity** — `hostPath type: Directory` paths that must pre-exist;
   PV/PVC correctness; mount paths matching between stages; **cluster (`*.yaml`) ↔ local
   (`local-WSL2-*.yaml`) parity** (drift between the two is a common bug).
4. **Reproducibility & Provenance** — image tags/digests pinned (never `:latest`); model
   versions; per-scan parameter defaults vs. overrides; idempotency / re-delivery behavior
   (ties to roadmap A4 in `docs/bloom-integration/roadmap.md`).
5. **Docs Accuracy & Shell-Script Safety** — README/`openspec/project.md` still accurate;
   run scripts use `set -euo pipefail`; **no `ARGO_TOKEN` / secret leakage** into logs or
   committed files; safe failure handling.

## Step 1: Determine Mode

**Mode A — PR number provided** (`$ARGUMENTS` is a number):
- Gather PR context from GitHub and post a review verdict.

**Mode B — No PR / branch provided** (`$ARGUMENTS` is empty or a branch name):
- Compare against the merge base: `git diff $(git merge-base HEAD main)..HEAD`
- Report findings only; do not post to GitHub.

Resolve the repo for GitHub calls:

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
# → use as talmolab/sleap-roots-pipeline in all gh commands
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
  repository(owner: "OWNER", name: "REPO") {
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
  - DAG dependencies / ordering; templateRef wiring; entrypoint; parameter & artifact
    passing; retryStrategy; would `argo lint` pass on every changed manifest?

Subagent 2: RunAI / Kubernetes Scheduling & Resources
  - gpu-fraction / preemptible annotations; nvidia.com/gpu limits on the right step;
    namespace; project label / quota; nothing requesting GPU that shouldn't.

Subagent 3: Storage & Volume Integrity
  - hostPath type:Directory pre-existence; PV/PVC; inter-stage mount-path agreement;
    cluster vs local-WSL2 manifest parity.

Subagent 4: Reproducibility & Provenance
  - image tags/digests pinned (no :latest); model versions; per-scan param defaults vs
    overrides; idempotency / re-delivery; alignment with roadmap A4.

Subagent 5: Docs Accuracy & Shell-Script Safety
  - README / openspec/project.md accuracy; set -euo pipefail; ARGO_TOKEN/secret leakage;
    failure handling; does the implementation match the PR description / linked spec?
```

## Step 4: Synthesize and Act

After ALL subagents return:

1. **Deduplicate** overlapping findings.
2. **Prioritize**:
   - **BLOCKING** — must fix before merge (broken DAG/templateRef, secret leakage, GPU on
     wrong step, manifest that fails `argo lint`, spec mismatch)
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
*Review by Claude Code subagent team (Argo Correctness | RunAI Scheduling | Storage Integrity | Reproducibility | Docs & Script Safety)*
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

- `/review-openspec` — review the spec before reviewing the implementation PR
- `/copilot-review` — fetch and triage GitHub Copilot inline comments
- `/pr-description` — generate the PR body
