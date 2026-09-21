# Add executable assertions for the cluster access model

## Why

`docs/cluster-identities.md` is the authoritative onboarding doc for cluster access. Until this
change it stated:

> **There is no per-person RunAI console access.** Work is driven from the `argo` / `runai` CLI
> against a kubeconfig.

Both halves are wrong. Per-person RunAI console access exists via SSO, and the `runai` CLI requires
that SSO session *in addition to* the shared `argo-user` kubeconfig. `README.md` documented a
different (also incomplete) split while linking to this doc, so the two contradicted each other in
the repo's two most-read operator documents.

The wrong sentence is the symptom. The defect is that **access-model claims in this repo are prose
nobody can re-run.** `scripts/check_manifests.py` already exists for exactly this reason — its
docstring says every "Validate:" step "has historically been prose that nobody could re-run" — but
its 53 assertions cover manifests only. Nothing checks that the access documentation agrees with
itself, or with the manifests it describes.

That gap is not hypothetical. A first attempt at this correction (PR #74) introduced four *new*
false claims, including a "No drift" assertion that was falsified within hours, and shipped a
verification step that checked only the half of the claim where the two documents already agreed —
an acceptance test that could not fail. Prose verification steps do not catch prose defects.

## What Changes

- **Correct the access model** in `docs/cluster-identities.md`: replace the false sentence with a
  two-auth-planes model (Kubernetes RBAC via the shared kubeconfig vs. per-person RunAI SSO),
  carrying explicit provenance.
- **Correct `README.md`**, whose `runai` auth cell omits `KUBECONFIG` entirely and whose identity
  sentence partitions one credential per tool. Both misstate `runai`, which needs both.
- **Complete `.claude/skills/runai/SKILL.md` §1**, which presents the `KUBECONFIG` export as the
  whole auth story and leaves `runai login remote-browser` in a troubleshooting table.
- **Add `scripts/check_docs.py`** — executable assertions over the documentation, in the same shape
  and exit convention as `check_manifests.py`, wired into `scripts/lint_manifests.sh`. Assertions
  cover: the retracted claims do not reappear; the two auth planes are stated consistently across
  all three documents; documented template counts match the manifests actually present; and the
  documented priority classes match the templates.
- **Annotate the superseded plan bullets** that seeded the false claim, so resuming that plan by
  checkbox cannot re-introduce it.

## Impact

- Affected specs: `cluster-access-docs` (new capability)
- Affected code: `docs/cluster-identities.md`, `README.md`, `.claude/skills/runai/SKILL.md`,
  `scripts/check_docs.py` (new), `scripts/lint_manifests.sh`,
  `docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md`
- No manifest changes; no orchestration behavior changes; no change to `per-batch-pipeline`.
- Deliberately **not** in scope: `sleap-roots-pipeline.yaml` hardcodes
  `genericsecret-bloom-staging-pipeline-credentials`, so a production-dispatched Workflow mounts the
  *staging* Bloom credential. That is a real gap originating in this repo (not, as an earlier draft
  claimed, in `salk-bloom`, which only vendors a byte-identical copy). It is tracked by #17 and
  needs a manifest change, not a documentation one — this change adds one sentence pointing at it.
