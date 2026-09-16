# Cluster access model: correction and claim audit

**Date:** 2026-09-15
**Branch:** `fix-cluster-access-model-docs`
**Status:** design, pending implementation

## Problem

`docs/cluster-identities.md` is the authoritative onboarding doc for cluster access. It states:

> **There is no per-person RunAI console access.** Work is driven from the `argo` / `runai` CLI
> against a kubeconfig.

Both halves are false. Per-person RunAI console access exists via SSO, and the `runai` CLI needs
that SSO session in addition to the kubeconfig. `README.md:42-43` already documents the correct
split and links to `cluster-identities.md`, so the two docs currently contradict each other.

The false sentence originates in
`docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md:600`, where it appears
as an unsourced assertion in the Task-4 spec for the "Getting access" section. It was never
reported by anyone; it was inferred and then shipped.

That is the real defect. The doc applies a verification discipline to exactly two of its ~40
claims — the RBAC table ("verified live on 2026-09-15 with `kubectl auth can-i` ... not inferred
from a manifest") and the `## What isn't verified` section for `bloom-workflow`. Every other claim,
including the false one, carries no provenance. A claim with no provenance is one nobody can check,
and this is what that costs.

## Ground truth

Two authentication planes. A tool may need one or both.

| Tool | Shared `argo-user` kubeconfig | Per-person RunAI SSO |
|---|---|---|
| `argo` | required | no |
| `kubectl` | required | no |
| `runai` | required | **also required** |
| RunAI console | n/a | required |

Confirmed by the repo owner, 2026-09-15. Console access is per-person but not automatic: a new
person must be added to the `busch-lab` RunAI project by the cluster admin or a project owner. Once
they have it, creating RunAI Generic secrets is self-service — no cluster-admin round-trip.

This matters because the two planes fail differently. A missing SSO session breaks `runai` while
`argo` keeps working against the same namespace from the same shell, which does not look like an
auth problem.

## Audit results

Every claim in `docs/cluster-identities.md` was checked. Method and outcome per group:

### Measured live, 2026-09-15

| Claim | Method | Result |
|---|---|---|
| `argo-user` row, all 12 cells (plus `list`/`create secrets`) | `kubectl auth can-i` under its own kubeconfig | exact, no corrections |
| `bloom-pipeline` row, all 20 cells | `kubectl auth can-i` under its own kubeconfig | exact, no corrections |
| `argo submit -n` does not redirect a submission | `argo submit --server-dry-run -n runai-talmo-lab` | reproduced: namespace resolves to `runai-busch-lab` |
| Stage templates registered in the namespace | `argo template list -n runai-busch-lab` | all four present |
| Registered predictor template matches this repo | `argo template get` vs. the file | zero drift: image pin, `secretKeyRef`, `priorityClassName`, `gpu-memory` all identical |
| Production dispatcher is live | `docker ps` on `bloom-dev.salk.edu` | prod pair `Up 6 days`; staging pair `Up 3 hours` |

`argo-user` additionally returns **no** for `create secrets`, which is the direct evidence that
Generic secrets are a console action rather than a `kubectl` one.

### Derived from code

`serviceAccountName: bloom-workflow` (`sleap-roots-pipeline.yaml:39`); predictor
`priorityClassName: high` against `interactive-preemptible` on the three CPU stages; exactly three
`hostPath` volumes, all `type: Directory`; `salk-bloom`'s `build_workflow_body` overriding only
scan-ids, labels, `ttlStrategy` and namespace, with volumes passing through unmodified.

### Reported by the repo owner, 2026-09-15

- `genericsecret-wandb-api-key` and `genericsecret-bloom-staging-pipeline-credentials` both exist
  in `runai-busch-lab`.
- The three `a4_poc/` `hostPath` directories are present and accessible from the GPU cluster.
- The GPU quota of 2 is a *deserved* quota — work can burst above it preemptibly.

### Not verifiable

`bloom-workflow`'s permissions. It is a pod-mounted ServiceAccount, nobody holds a kubeconfig for
it, and `get serviceaccounts` returns **no** under both other identities. The existing
`## What isn't verified` section already states this correctly and stays as-is.

## Decisions

1. **Keep the identity table at three rows.** Those are the identities *workloads run as*, all
   namespace-scoped k8s RBAC, all re-verified today. The per-person SSO login is a human operator
   identity on a different plane; bolting it into that table would conflate the two things this
   change exists to separate. It gets its own subsection instead, placed before the table so the
   table is read in context.

2. **Correct the `runai` skill additively.** Its `export KUBECONFIG=... && runai <command>` pattern
   is correct — `runai` does need the kubeconfig. It is only incomplete: it never says an active
   SSO session is equally required, and it demotes `runai login remote-browser` to a
   troubleshooting-table row. Promote it into §1 as the auth model. No command examples change.

3. **Do not touch `README.md`, and do not re-document `kubectl`'s WSL location.** An earlier draft
   of this design proposed both, on the belief that `kubectl` being at `~/bin/kubectl` and absent
   from the non-login WSL PATH was undocumented. It is documented — `.claude/skills/runai/SKILL.md`
   §1a records it, with the PATH export and a warning that concluding a tool is uninstalled from a
   non-login shell "is a mistake that has actually been made here." That mistake was then made again
   during this audit, which is a discovery problem, not a documentation gap; §1a is already correct
   and more precise than a replacement would be. `README.md` likewise already delegates to the skill
   for exact locations. Both stay untouched.

4. **Leave dated session records alone, with one exception.** The 2026-08-07 handoff's
   "cluster-admin-only to create" gloss is stale, but it quotes an admin accurately ("no *kubectl*
   identity of yours can create secrets" — still true) and is a record of what was known then. It
   stays untouched. Owner's decision: fix living docs only.

   The exception is `docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md:600`,
   which seeded the false sentence. That plan is not a dead record: its work shipped in PR #62, but
   all 55 of its checkboxes are still unticked, so it reads as unexecuted. Anyone resuming it by
   checkbox would rewrite the false sentence — which is how it got shipped the first time. It gets a
   one-line superseded annotation matching the one already at line 352 of the same file
   (`⚠️ SUPERSEDED — do not execute this step as written`, added by PR #69), so this follows an
   existing convention in this exact file rather than introducing one.

5. **No OpenSpec change.** Nothing in `openspec/specs/` changes by a byte — no capability, no
   requirement, no orchestration behavior. `/new-feature` carves out docs-only work.

## Changes

**`docs/cluster-identities.md`**

- Delete the false sentence.
- Add a `Two auth planes` subsection carrying the table above, plus how a new person gets console
  access (added to the `busch-lab` project) and the resulting failure mode.
- Split the provisioning paragraph in two: Generic secrets are self-service in the console, with
  the `genericsecret-` name-prefix consequence; ServiceAccount/Role/RoleBinding still needs the
  cluster admin.
- Re-date the table's verification line to 2026-09-15 and state that both rows were re-confirmed
  cell-for-cell, not spot-checked.
- Refine the quota line to "deserved quota 2, burstable preemptibly".
- Note the predictor template's confirmed zero drift against this repo, and the prod dispatcher's
  measured uptime behind the template-update warning.

**`.claude/skills/runai/SKILL.md`**

- §1 only: state both requirements — the explicit `KUBECONFIG` it already gives, *and* an active
  SSO session. Promote `runai login remote-browser` from the §8 troubleshooting table into §1 as
  the auth model. §1a is already correct and is not touched.

**`README.md`** — no change. Its identity wording at `:42-43` is already correct and becomes the
phrasing `cluster-identities.md` mirrors; it already delegates CLI locations to the runai skill.

**`docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md`**

- A superseded annotation at line 600 only. The surrounding plan text is left exactly as written.

## Out of scope

Other dated plans and specs, including the 2026-08-07 handoff;
`docs/bloom-integration/roadmap.md`; the `-staging` credential name
hardcoded in the vendored manifest (a real gap for production dispatch, but a code change in
`salk-bloom`, not a docs correction).

## Verification

No manifests change, so there is no `argo lint` surface. Verify by: re-grepping for the stale
phrasings and confirming zero hits in living docs; reading `README.md` and `cluster-identities.md`
together to confirm they now agree; and confirming every remaining claim in the doc is traceable to
one of the four provenance categories above.
