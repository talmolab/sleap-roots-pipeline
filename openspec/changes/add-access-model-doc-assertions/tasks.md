# Tasks

Test-driven throughout: every assertion is written and **observed failing** before the
documentation it checks is corrected. `scripts/check_docs.py` is the harness, modelled on
`scripts/check_manifests.py` (same `PASS`/`FAIL` output, same exit convention).

## 1. Harness

- [ ] 1.1 Create `scripts/check_docs.py` with the same structure as `check_manifests.py`: a `ROOT`
  anchored on the repo root, a `check(label, condition)` accumulator, a summary line, `sys.exit(1)`
  on any failure. No cluster calls, no network, no credentials.
  - Validate: `python scripts/check_docs.py` runs and reports `0 assertions` without error.
- [ ] 1.2 Wire it into `scripts/lint_manifests.sh` so one command runs both suites, and a failure
  in either is fatal.
  - Validate: `sh scripts/lint_manifests.sh` invokes both; `echo $?` is `0`.

## 2. Retracted claims cannot reappear (Requirement 1, Scenario 1)

- [ ] 2.1 Add assertions that none of `docs/cluster-identities.md`, `README.md`,
  `.claude/skills/runai/SKILL.md` contains "no per-person RunAI console access", and that
  `SKILL.md` §1 does not present `KUBECONFIG` as the sole `runai` requirement.
  - Validate: run before fixing the docs — **these must FAIL**, naming `SKILL.md`.
- [ ] 2.2 Correct `.claude/skills/runai/SKILL.md` §1: state that `runai` needs the kubeconfig *and*
  an active SSO session; surface `runai login remote-browser` there (leaving the §8 troubleshooting
  row in place — this is an addition, not a move).
  - Validate: 2.1's assertions now PASS.

## 3. The three documents agree (Requirement 1, Scenario 2)

- [ ] 3.1 Add assertions that `README.md`'s `runai` auth cell names **both** `KUBECONFIG` and SSO,
  and that its identity sentence does not assign exactly one credential per tool.
  - Validate: run before fixing — **must FAIL** on `README.md:25` and `:42-43`.
- [ ] 3.2 Correct `README.md`'s `runai` row and identity sentence.
  - Validate: 3.1 PASSes.
- [ ] 3.3 Add an assertion that `docs/cluster-identities.md` contains an auth-plane table whose
  `runai` row requires both planes, and whose `argo`/`kubectl` rows require SSO in neither.
  - Validate: run before writing the section — **must FAIL**.
- [ ] 3.4 Write the `Two auth planes` section in `docs/cluster-identities.md`, using `no` (not
  `n/a`) as the single negative token, and titling the kubeconfig column so it does not claim
  `kubectl` can only ever use the shared `argo-user` file.
  - Validate: 3.3 PASSes.

## 4. Provenance (Requirement 1, Scenario 3)

- [ ] 4.1 Add an assertion that the auth-planes section names a confirming party and an ISO date.
  - Validate: run before adding the line — **must FAIL**.
- [ ] 4.2 Add `Confirmed with the repo owner, 2026-09-15.` to that section.
  - Validate: 4.1 PASSes.

## 5. Inventory matches the manifests (Requirement 2)

- [ ] 5.1 Add an assertion that every stage count stated in `docs/cluster-identities.md` equals the
  number of `sleap-roots-*-template.yaml` files the launcher registers (now five, after #60 added
  `sleap-roots-exit-gate-template.yaml`).
  - Validate: run before fixing — **must FAIL**, because the doc says "three CPU stages".
- [ ] 5.2 Add an assertion that each `priorityClassName` named in the docs matches the manifest.
  - Validate: run before fixing — record whether it passes; the predictor is `high` and the others
    `interactive-preemptible`.
- [ ] 5.3 Correct the stage counts in `docs/cluster-identities.md`.
  - Validate: 5.1 and 5.2 PASS.

## 6. No standing cluster-parity claim (Requirement 2, Scenario 3)

- [ ] 6.1 Add an assertion that `docs/cluster-identities.md` contains no present-tense parity claim
  ("No drift", "matches this repo's file exactly") and does reference
  `scripts/check_cluster_drift.sh`.
  - Validate: run before fixing — **must FAIL** on the "No drift." sentence.
- [ ] 6.2 Replace that paragraph with a dated observation plus a pointer to
  `scripts/check_cluster_drift.sh` and issue #58.
  - Validate: 6.1 PASSes.

## 7. Remaining corrections found by review

- [ ] 7.1 Fix the intro's "sitting behind them", which asserts the SSO plane sits behind the three
  Kubernetes identities — a containment this change explicitly denies. Qualify the count as "three
  Kubernetes identities".
  - Validate: assertion that the doc contains "three Kubernetes identities" and not the bare
    "Three different identities".
- [ ] 7.2 Correct "before they can sign in" → membership gates seeing `busch-lab`, not SSO itself.
- [ ] 7.3 State that creating Generic secrets is self-service once you have console access.
- [ ] 7.4 Add the quota nuance accurately: `deserved` quota 2, preemptible work may exceed it, but
  the predictor is non-preemptible `high` so it waits rather than bursts. Keep #60's correction of
  the unset-priority-class claim untouched.
  - Validate: assertion that the doc does not claim the pipeline's GPU stage bursts above quota.
- [ ] 7.5 Note that a missing secret produces the same `Pending`/hang failure as a missing
  `hostPath` directory, and that the credential the prod dispatcher mounts is the staging one (#17).
- [ ] 7.6 Replace the `Up 6 days` uptime with a dated "verified running" statement.

## 8. Superseded plan bullets

- [ ] 8.1 Annotate `docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md`
  lines 599, 600 and 605 — all three are false or contradicted, not only the one that caused this
  work. Match line 352's existing blockquote format exactly, or state in `design.md` why not.
  - Validate: assertion that every false bullet in that list carries a superseded marker.

## 9. Close out

- [ ] 9.1 Run the full suite: `python scripts/check_manifests.py && python scripts/check_docs.py`.
  - Validate: both exit `0`; the 53 pre-existing manifest assertions still pass.
- [ ] 9.2 `openspec validate add-access-model-doc-assertions --strict`.
- [ ] 9.3 Rewrite the stale design doc and plan from PR #74, whose premises this change corrects.
