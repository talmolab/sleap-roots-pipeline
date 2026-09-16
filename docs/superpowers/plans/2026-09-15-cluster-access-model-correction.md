# Cluster Access Model Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the false cluster access model in `docs/cluster-identities.md`, close the matching gap in the runai skill, and annotate the plan step that seeded the error.

**Architecture:** Three independent, separately committable documentation tasks, ordered by blast radius. Task 1 is the substantive correction to the authoritative onboarding doc. Task 2 closes the same gap in the runai skill. Task 3 annotates the upstream plan so the error cannot be re-seeded. Task 4 is the verification sweep. No file depends on another task's output, so they can be executed in any order — but Task 1 establishes the wording the others reference.

**Tech Stack:** Markdown only. No manifests change, so there is no `argo lint` surface and no test harness. Verification is grep-based plus cross-document consistency reading.

**Spec:** `docs/superpowers/specs/2026-09-15-cluster-access-model-audit-design.md`

## Global Constraints

- **This repo is PUBLIC.** Document credential *names* and *paths* only — env var names, kubeconfig filenames, secret object names. Never a token, CA cert, kubeconfig body, password, or bearer value, not even truncated.
- Target namespace is `runai-busch-lab` (project `busch-lab`). `runai-talmo-lab` is live but is not this pipeline's target since 2026-08-13.
- Never state an RBAC fact in documentation that has not been verified live. Where a fact cannot be verified, say so explicitly and say why.
- Do not modify `README.md`. Its identity wording at `:42-43` is already correct and is the phrasing this change mirrors.
- Do not modify `.claude/skills/runai/SKILL.md` §1a. It is already correct and more precise than a replacement would be.
- Do not modify dated session records other than the single annotation in Task 3.
- Commit messages end with: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## Task 1: Correct `docs/cluster-identities.md`

**Files:**
- Modify: `docs/cluster-identities.md` (six edits, detailed below)

**Interfaces:**
- Consumes: nothing.
- Produces: the "Two auth planes" section and its table, which Task 2's §1 bullet cross-references by name, and which Task 3's annotation points at indirectly via the design doc.

- [ ] **Step 1: Add the two-planes pointer to the intro**

Find (lines 3-5):

```markdown
Three different identities are involved in running this pipeline on the Salk cluster, and picking
the wrong one produces failures that don't look like permission problems. This page says what each
one is, what it can actually do, and how to get access.
```

Replace with:

```markdown
Three different identities are involved in running this pipeline on the Salk cluster, and picking
the wrong one produces failures that don't look like permission problems. This page says what each
one is, what it can actually do, and how to get access. It also covers the two separate sign-ins
sitting behind them — Kubernetes RBAC and RunAI SSO — which are not interchangeable.
```

- [ ] **Step 2: Insert the `Two auth planes` section**

Insert immediately before the line `## The three identities`, after the "Namespace throughout:" paragraph:

```markdown
## Two auth planes

Kubernetes RBAC and RunAI's own identity are separate. A tool may need one or both:

| Tool | Shared `argo-user` kubeconfig | Per-person RunAI SSO |
|---|---|---|
| `argo` | required | no |
| `kubectl` | required | no |
| `runai` | required | **also required** |
| RunAI console | n/a | required |

The kubeconfig is shared across the project. RunAI SSO is per person, and it is not automatic: a
new person must be added to the `busch-lab` RunAI project by the cluster admin or a project owner
before they can sign in.

The failure this prevents: with no SSO session, `runai` commands fail while `argo` keeps working
against the same namespace from the same shell. That does not look like an auth problem. Sign in
with `runai login remote-browser`, then confirm with `runai whoami`.

```

- [ ] **Step 3: Strengthen the verification line**

Find (lines 18-20, before the code fence):

```markdown
Both the `bloom-pipeline` and `argo-user` rows were verified live on **2026-09-15** with
`kubectl auth can-i` run under each identity's own kubeconfig — not inferred from a manifest. Rerun
the checks before relying on them; RBAC is cluster-admin-mutable:
```

Replace with:

```markdown
Both the `bloom-pipeline` and `argo-user` rows were verified live on **2026-09-15** with
`kubectl auth can-i` run under each identity's own kubeconfig — every cell, not a spot-check, and
not inferred from a manifest. Rerun the checks before relying on them; RBAC is
cluster-admin-mutable:
```

- [ ] **Step 4: Replace the false console paragraph**

Find (lines 98-102):

```markdown
**There is no per-person RunAI console access.** Work is driven from the `argo` / `runai` CLI
against a kubeconfig. If you need a new identity, `bloom-pipeline-serviceaccount.yaml` is the
precedent to copy — a ServiceAccount plus a namespace-scoped Role and RoleBinding — and the cluster
admin applies it. Note from experience that the applied result may differ from what the manifest
requests, so verify with `auth can-i` once you have it.
```

Replace with:

```markdown
**Secrets are created in the RunAI console, not with `kubectl`.** No kubeconfig identity here can
create one — `bloom-pipeline` has no `secrets` access at all, and `argo-user` returns **no** for
`get`, `list` and `create` alike (verified 2026-09-15). Use Credentials → Generic secret in the
console, Project-scoped to `busch-lab`. RunAI prefixes the resulting Kubernetes Secret name with
`genericsecret-`, which is why the manifests reference `genericsecret-wandb-api-key` rather than the
asset name you typed. This needs your own RunAI SSO access — see
[Two auth planes](#two-auth-planes).

**If you need a new Kubernetes identity**, `bloom-pipeline-serviceaccount.yaml` is the precedent to
copy — a ServiceAccount plus a namespace-scoped Role and RoleBinding — and the cluster admin applies
it. Note from experience that the applied result may differ from what the manifest requests, so
verify with `auth can-i` once you have it.
```

- [ ] **Step 5: Record the template-registration verification**

Find (in "Getting access", the paragraph beginning "**Your WorkflowTemplates must be registered"):

```markdown
`create` and `update`. This is the real prerequisite, not the credential.
```

Replace with:

```markdown
`create` and `update`. This is the real prerequisite, not the credential.

As of **2026-09-15** all four `sleap-roots-*` templates are registered in `runai-busch-lab`, and the
registered `sleap-roots-predictor-template` matches this repo's file exactly — same image pin, same
`secretKeyRef`, same `priorityClassName`, same `gpu-memory`. No drift. Re-check with
`argo template get <name> -n runai-busch-lab -o yaml` before assuming the cluster matches `main`.
```

- [ ] **Step 6: Correct the quota line**

Find (line 126):

```markdown
**The GPU quota is 2, and it is often fully used.** Always set `priorityClassName` explicitly:
```

Replace with:

```markdown
**The GPU deserved quota is 2, and it is often fully used.** Work can run above that quota
preemptibly — that is what the `interactive-preemptible` tier below buys. Always set
`priorityClassName` explicitly:
```

- [ ] **Step 7: Add measured evidence to the production-dispatch claim**

Find (lines 115-118):

```markdown
**`runai-busch-lab` is shared by Bloom staging *and* production**, distinguished only by an
environment label stamped on each submitted Workflow, and a production dispatch deployment is live
in it. An `argo template update` therefore affects both environments' future dispatches, not just
your next run. Don't update the `sleap-roots-*` templates unless you mean to.
```

Replace with:

```markdown
**`runai-busch-lab` is shared by Bloom staging *and* production**, distinguished only by an
environment label stamped on each submitted Workflow, and a production dispatch deployment is live
in it — verified **2026-09-15**, `bloom_v2_prod-cyl-pipeline-worker-1` and
`bloom_v2_prod-cyl-status-poller-1` both `Up 6 days` on `bloom-dev.salk.edu`, alongside the staging
pair. ("Live" means the dispatcher process is running, not that anything is driving it — no
frontend targets prod yet.) An `argo template update` therefore affects both environments' future
dispatches, not just your next run. Don't update the `sleap-roots-*` templates unless you mean to.
```

- [ ] **Step 8: Verify the false claims are gone and nothing else broke**

Run:

```bash
grep -n "no per-person RunAI console access" docs/cluster-identities.md
grep -n "GPU quota is 2" docs/cluster-identities.md
```

Expected: both return nothing (exit 1).

Run:

```bash
grep -c "^## " docs/cluster-identities.md
```

Expected: `7`. It was `6` before this change (`The three identities`, `Submit vs. report back`,
`What isn't verified`, `Getting access (new Bloom-side developer)`, `Namespace facts that bite`,
`Related`); `Two auth planes` is the seventh, and must sort before `The three identities`.

- [ ] **Step 9: Read the section back for internal consistency**

Read the whole of `docs/cluster-identities.md`. Confirm: the `Two auth planes` anchor link in Step 4
resolves to the heading added in Step 2 (`#two-auth-planes`); the intro's promise of "two separate
sign-ins" is delivered by that section; and no remaining sentence implies a kubeconfig grants
console or `runai` access.

- [ ] **Step 10: Commit**

```bash
git add docs/cluster-identities.md
git commit -m "docs: correct the cluster access model in cluster-identities

The doc claimed there is no per-person RunAI console access and that runai
runs against a kubeconfig. Both halves are false: console access is
per-person via SSO, and runai needs that SSO session in addition to the
shared kubeconfig. README.md already documented the correct split, so the
two docs contradicted each other.

Also records what the audit measured: every RBAC cell re-verified, the
predictor template's zero drift against this repo, the production
dispatcher's uptime, and the quota being a deserved quota rather than a cap.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Close the same gap in the runai skill

**Files:**
- Modify: `.claude/skills/runai/SKILL.md` (§1 only — §1a and §8 are not touched)

**Interfaces:**
- Consumes: the wording established in Task 1's `Two auth planes` section.
- Produces: nothing other tasks rely on.

- [ ] **Step 1: State both requirements in §1**

Find (the line under `## 1. WSL command execution pattern`):

```markdown
RunAI runs in **WSL**, not Windows PowerShell, and needs an explicit KUBECONFIG:
```

Replace with:

```markdown
RunAI runs in **WSL**, not Windows PowerShell, and needs **two** things: an explicit KUBECONFIG
*and* an active SSO session. The kubeconfig is shared across the project; the SSO login is yours
personally.
```

- [ ] **Step 2: Add the SSO bullet**

Find (the first bullet under the §1 code fence):

```markdown
- `runai` is assumed on `PATH`; if your install isn't, use its absolute path (e.g.
```

Insert immediately *before* that line:

```markdown
- **The kubeconfig alone is not enough.** `runai` commands fail until you have signed in with
  `runai login remote-browser` (confirm with `runai whoami`). `argo` and `kubectl` need only the
  kubeconfig — which is why `argo` keeps working in the very shell where `runai` is failing on auth.
  See `docs/cluster-identities.md` → "Two auth planes".
```

- [ ] **Step 3: Verify**

Run:

```bash
grep -n "login remote-browser" .claude/skills/runai/SKILL.md
```

Expected: two hits — the new §1 bullet, and the pre-existing §8 troubleshooting row (which stays;
it is a correct recovery entry).

Run:

```bash
grep -n "needs an explicit KUBECONFIG" .claude/skills/runai/SKILL.md
```

Expected: nothing (exit 1).

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/runai/SKILL.md
git commit -m "docs(runai): state that runai needs an SSO session, not just a kubeconfig

Section 1 gave the KUBECONFIG export as the whole auth story and left
runai login remote-browser in the section 8 troubleshooting table. runai
needs both; argo and kubectl need only the kubeconfig.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Annotate the plan step that seeded the false claim

**Files:**
- Modify: `docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md:600`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

**Why this one dated doc is edited when the others are not:** its work shipped in PR #62, but all 55
of its checkboxes are unticked, so it reads as unexecuted. Anyone resuming it by checkbox would
rewrite the false sentence — which is how it shipped the first time. The annotation format matches
the one already at line 352 of this same file (added by PR #69).

- [ ] **Step 1: Annotate the bullet**

Find (line 600):

```markdown
   - There is no per-person RunAI console access; work is driven from the `argo`/`runai` CLI against a kubeconfig.
```

Replace with:

```markdown
   - **⚠️ SUPERSEDED — do not write this (note added 2026-09-15).** ~~There is no per-person RunAI console access; work is driven from the `argo`/`runai` CLI against a kubeconfig.~~ Both halves are false. Per-person RunAI console access exists via SSO, and `runai` needs that SSO session *in addition to* the shared kubeconfig, while `argo`/`kubectl` need only the kubeconfig. This bullet was an unsourced assertion that shipped into `docs/cluster-identities.md` and was corrected on 2026-09-15 — see `docs/superpowers/specs/2026-09-15-cluster-access-model-audit-design.md`.
```

- [ ] **Step 2: Verify the surrounding plan text is untouched**

Run:

```bash
git diff --stat docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md
```

Expected: `1 file changed, 1 insertion(+), 1 deletion(-)` — exactly one line replaced.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md
git commit -m "docs: flag the plan bullet that seeded the false console claim

The plan's work shipped in PR #62 but its checkboxes are all unticked, so
it reads as unexecuted. Resuming it by checkbox would rewrite the false
sentence. Matches the superseded-annotation convention already used at
line 352 of the same file.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Repo-wide verification sweep

**Files:**
- Modify: none. This task only verifies.

**Interfaces:**
- Consumes: all three preceding tasks.
- Produces: the evidence quoted in the PR description.

- [ ] **Step 1: Confirm zero stale claims survive in living docs**

Run from the worktree root:

```bash
grep -rn "no per-person RunAI console access" --include="*.md" . | grep -v ".worktrees/"
```

Expected: exactly one hit — the struck-through text inside Task 3's superseded annotation. No hit in
`docs/cluster-identities.md`.

- [ ] **Step 2: Confirm the two docs now agree**

Run:

```bash
grep -n "uses your own SSO login" README.md
grep -n "Per-person RunAI SSO" docs/cluster-identities.md
```

Expected: both return a hit. Read both passages and confirm they state the same split — `runai`
needs SSO, `argo`/`kubectl` do not.

- [ ] **Step 3: Confirm nothing outside scope changed**

Run:

```bash
git diff --stat main
```

Expected: exactly five files — the design doc, this plan, `docs/cluster-identities.md`,
`.claude/skills/runai/SKILL.md`, and the annotated plan. `README.md` must NOT appear.

- [ ] **Step 4: Open the PR**

Use `/pr-description`. The description must state that this is a documentation-only change with no
OpenSpec delta (no capability or requirement changes), and should carry the audit evidence: all 32
RBAC cells re-verified live under both kubeconfigs, the namespace-redirect behavior reproduced, all
four templates confirmed registered, the predictor template confirmed drift-free, and the production
dispatcher confirmed `Up 6 days`.
