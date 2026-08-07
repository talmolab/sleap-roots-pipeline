# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit. Both changes here are cluster-admin-directed (`bloom-workflow` created and confirmed in
both namespaces 2026-08-06; hostPath hardening explicitly requested "before anything runs
unattended").

## 1. Workflow edit

- [x] 1.1 Edited `sleap-roots-pipeline.yaml`: added `serviceAccountName: bloom-workflow` under
  `spec` (sibling to `entrypoint`). Changed all three volumes' `hostPath.type` from
  `DirectoryOrCreate` to `Directory`. Rewrote the volumes-block comment to drop the
  now-obsolete "images-input-dir specifically needs DirectoryOrCreate for a cold start" framing
  (that path has existed continuously since this program's PoC and isn't going away) and explain
  the fail-loudly rationale instead.
- [x] 1.2 Confirmed via inspection: `serviceAccountName: bloom-workflow` present at the `spec`
  level, no template overrides it (none of the four templates set their own
  `serviceAccountName` — unchanged from before this edit), all three `hostPath.type` values are
  `Directory`, no `DirectoryOrCreate` string remains anywhere in the file.

## 2. Static validation

- [x] 2.1 `argo lint --offline sleap-roots-pipeline.yaml` → exactly the expected, pre-existing
  limitation: `couldn't find workflow template "sleap-roots-images-downloader-template" in
  namespace "runai-talmo-lab"` (offline lint can't cross-resolve `templateRef` against
  unregistered templates — the same limitation this file's prior changes have documented). No
  other lint errors.

## 3. Live validation (real cluster)

- [x] 3.1 `kubectl get serviceaccount` is forbidden for `argo-user` (confirmed: "cannot get
  resource serviceaccounts" — matches the earlier RBAC investigation's finding that this
  identity can't read SA objects directly). Verified indirectly instead via 3.2/3.3 — if
  `bloom-workflow` didn't exist, pod admission would have failed outright, which it didn't.
- [x] 3.2 Submitted `sleap-roots-pipeline-6ndlb` (`scan-ids=289,577,1009`) against
  `runai-talmo-lab`. `kubectl get pod sleap-roots-pipeline-6ndlb-predictor-1061253075 -o
  jsonpath='{.spec.serviceAccountName}'` → `bloom-workflow`, confirmed on the real pod (not just
  the Workflow object).
- [x] 3.3 Run succeeded end-to-end: all four stages `Completed` (`images-downloader`,
  `predictor`, `trait-extractor`, `write-back`, 0 restarts). No
  `workflowtaskresults.argoproj.io is forbidden` error anywhere — `bloom-workflow`'s RBAC works.
  `write-back`'s log shows `Ingested 0/4 envelopes (4 skipped)` — expected (these scans were
  already ingested in earlier sessions), not a failure.
- [x] 3.4 Confirmed the `hostPath.type: Directory` change is a no-op in the success case — same
  run reused the pre-existing `a4_poc` paths without any `FailedMount` issue. Explicitly not
  re-testing the down-mount failure path (would require actually taking the NFS mount down on a
  live node, out of scope/too disruptive for this change — the fix is "fail loudly instead of
  silently corrupting," not something to re-derive here).

## 4. Validate + close out

- [x] 4.1 `openspec validate wire-bloom-workflow-sa --strict` → valid.
- [x] 4.2 `/pr-description`; PR opened. Noted in the PR body that this change is independent of
  and unrelated to PR #41 (`enable-predictor-gpu-fractions`) despite overlapping in time —
  different files, different concern (RBAC + storage vs. GPU scheduling). Also noted: busch-lab
  template registration (issue #40) is blocked on a separate RBAC gap discovered while doing
  this work (`argo-user` lacks `workflowtemplates` create rights in `runai-busch-lab`, confirmed
  via `kubectl auth can-i`) — tracked on #40, not blocking this PR since this PR only touches
  `sleap-roots-pipeline.yaml`, submitted into `runai-talmo-lab`.
