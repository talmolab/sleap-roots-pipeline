# Design — executable assertions for the cluster access model

## Context

`docs/cluster-identities.md` shipped a false access-model claim, and `README.md` shipped a
different incomplete one, while linking to each other. The correction is small. The interesting
question is why prose review did not catch it, and why a first attempt made it worse.

That first attempt is documented here because it is the evidence for the design. PR #74 audited
every claim in the doc, re-verified 32 RBAC cells live, reproduced the namespace-redirect
behavior — and still introduced four new false claims, because it was built on a `main` that was
19 minutes stale and never fetched. It also shipped a verification step that read only the half
of the claim where the two documents already agreed. Its own reviewers scored it 6, 3, 8, 6, 6.

## Ground truth

Two authentication planes; a tool may need one or both. Confirmed with the repo owner,
2026-09-15.

| Tool / surface | Kubernetes kubeconfig | Per-person RunAI SSO |
|---|---|---|
| `argo` | required | no |
| `kubectl` | required | no |
| `runai` | required | **also required** |
| RunAI console | no — browser SSO only | required |

Project membership gates what you can *see and do* in `busch-lab`; Salk SSO authenticates you
regardless. Creating RunAI Generic secrets is self-service for anyone with console access.

## The measurement was wrong too

After the docs were corrected, the RBAC numbers themselves turned out to be wrong — not stale,
*mis-measured*. `kubectl auth can-i get pods/log` does not ask about the log subresource. Everything
after the slash is parsed as a resource **name**, so the query asks "can I get a pod named `log`"
and simply mirrors bare `pods` access. Measured 2026-09-16 under both kubeconfigs:

| Query | `argo-user` | `bloom-pipeline` |
|---|---|---|
| `get pods/log` (slash) | yes | yes |
| `get pods --subresource=log` | **no** | yes |
| `create pods/exec` (slash) | yes | no |
| `create pods --subresource=exec` | **no** | no |
| `create pods` (bare) | yes | no |

The slash form tracks the bare-`pods` row exactly in both columns, which is the tell. Corrected:
**`argo-user` cannot read logs and cannot exec; `bloom-pipeline` can read logs; nobody can exec.**
Every other cell held on re-measurement — only the two subresource cells moved.

This is the sharpest instance of the pattern this change exists to address. The earlier audit ran
32 `auth can-i` queries, reported "every cell, not a spot-check", and was believed *because* it
was live-verified. Running a command is not the same as running the right command, and a confident
provenance stamp on a wrong measurement is worse than no stamp — it ends further questioning. The
assertions now guard the command as well as the conclusion: the doc may not contain an
`auth can-i` example using the slash form, and may not restate the claims it produced.

## Decisions

1. **Assertions, not prose.** Every claim this change makes about the docs is an assertion in
   `scripts/check_docs.py`, in the same shape as the existing `check_manifests.py`. The harness was
   negative-tested — an injected regression exits 1 — because a check whose failure mode is
   "everything is fine" is worse than none, a principle `check_manifests.py` already states about
   its own gate assertions.

2. **No claim about the live cluster, ever, in a doc in this repo.** PR #74 asserted "No drift"
   against the registered predictor template. It was true when measured and false within the hour:
   the namespace was re-registered from a newly merged `main`. A shared, mutable namespace cannot
   be described in present tense by a file in version control. The doc now points at
   `scripts/check_cluster_drift.sh` and [#58](https://github.com/talmolab/sleap-roots-pipeline/issues/58)
   instead, and an assertion forbids the parity phrasings from returning.

3. **The identity table stays at three rows; the *count* gets qualified.** The three are Kubernetes
   RBAC identities that workloads run as. The SSO login is a human identity on the other plane, so
   adding a fourth row would conflate exactly what this change separates. But leaving the ordinal
   bare made the document assert "three" while introducing a fourth identity concept 20 lines
   earlier. Heading and intro now say *three Kubernetes identities*, which is what makes "three"
   true. An earlier draft also wrote that the sign-ins sit "behind" the three identities — a
   containment this design explicitly denies; removed, and asserted against.

4. **`README.md` is in scope.** An earlier draft asserted it was "already correct" and set a
   *do not modify* constraint, then wrote a verification step that checked only the SSO column —
   the one column where the two documents agreed. README's `runai` row named SSO and omitted
   `KUBECONFIG`, and its identity sentence assigned one credential per tool. Both corrected, and
   an assertion now compares the kubeconfig column, which is where the disagreement actually was.

5. **The runai skill fix is additive.** `runai` genuinely needs the kubeconfig *and* SSO, so §1's
   existing `export KUBECONFIG=… && runai …` pattern is correct and only incomplete. §1a already
   documents `kubectl`'s WSL location correctly — better than a replacement would have — and is
   untouched. A draft of this change proposed re-documenting it in two more files on the mistaken
   belief it was missing; dropped.

6. **All three false bullets in the drift plan are annotated, not just one.** Annotating only the
   bullet that caused this work would be provenance theater. Line 599 (`bloom-pipeline` has no
   `pods/log` — contradicted by this repo's own verified table) and line 605 (already corrected by
   #60) are marked too. They use that file's *bullet* convention — inline `⚠️ **Corrected <date>:**`,
   per #60 at line 605 — not line 352's blockquote form, which is for steps. An earlier draft
   claimed to match line 352 and did not; the assertion accepts either marker and checks only that
   the claim is marked.

7. **Quota wording states what is true of this pipeline.** 2 is a *deserved* quota and preemptible
   work may exceed it — but the predictor is the only GPU-requesting stage and runs non-preemptible
   `high`, so at 2/2 it waits rather than bursts. A draft attributed bursting to the
   `interactive-preemptible` tier, whose stages request no GPU at all. #60's correction of the
   unset-priority-class claim is preserved untouched.

## Out of scope, with one sentence in the doc

`sleap-roots-pipeline.yaml:90` hardcodes `genericsecret-bloom-staging-pipeline-credentials`, and
`build_workflow_body` passes `volumes` through unmodified, so a production-dispatched Workflow
mounts the **staging** Bloom credential. This originates in *this* repo — an earlier draft
mislocated it to `salk-bloom`, which only vendors a byte-identical copy pinned to `9df1e52`.
Fixing it needs a manifest change and a per-environment mechanism that does not exist; it is
tracked by [#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17). The doc now names it
rather than documenting the mechanism and suppressing the consequence.

## Verification

`bash scripts/check_all.sh` — 53 manifest assertions and 27 documentation assertions, offline, no
`argo`, no cluster, no credentials. Live-cluster facts belong to `scripts/check_cluster_drift.sh`.
