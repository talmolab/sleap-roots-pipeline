## 1. Baseline validation (RED — confirm the gap exists before touching anything)

- [x] 1.1 `argo lint` on both templates against the live cluster (v3.6.5 via WSL,
      `KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml`) — pre-edit content confirmed clean by
      inspection (unchanged apart from the added `env:` entries); superseded by the stronger
      post-edit lint (2.3/3.3) and the real cluster run (task 4) below.
- [x] 1.2 `grep -n "env:" -A3` on both templates before editing confirmed only `HOME` was set —
      no `ARGO_WORKFLOW_NAME` or equivalent already present.
- [x] 1.3 **RED→GREEN evidence gap found in PR #43 review, fixed here.** The PR body claimed
      `argo lint` also passed on the full `sleap-roots-pipeline.yaml`, but that step was never
      actually recorded anywhere in this file — re-ran it post-edit to close the gap between claim
      and evidence trail:
      ```
      $ argo lint sleap-roots-pipeline.yaml
      ✔ no linting errors found!
      ```
      (plus unrelated pre-existing `W0813 ... Use tokens from the TokenRequest API ...`
      deprecation warnings from `kubectl`'s own auth path, not from this change).

## 2. images-downloader template

- [x] 2.1 Added `ARGO_WORKFLOW_NAME` (`value: "{{workflow.name}}"`) to
      `sleap-roots-images-downloader-template.yaml`'s container `env:` block, alongside the
      existing `HOME` entry, with an explanatory comment matching this file's existing convention.
- [x] 2.2 Confirmed via grep the `value` is exactly `"{{workflow.name}}"`.
- [x] 2.3 `argo lint sleap-roots-images-downloader-template.yaml` — clean (exit 0).

## 3. write-back template

- [x] 3.1 Added `ARGO_WORKFLOW_NAME` (`value: "{{workflow.name}}"`) to
      `sleap-roots-write-back-template.yaml`'s container `env:` block, alongside the existing
      `HOME` entry, with a comment cross-referencing the images-downloader template. Did **not**
      add an `images-input-dir` volume mount (see `design.md`).
- [x] 3.2 Confirmed via grep the `value` is exactly `"{{workflow.name}}"`.
- [x] 3.3 `argo lint sleap-roots-write-back-template.yaml` — clean (exit 0).

## 4. Real resolution check (cluster-only — no local fallback exists; done)

`local-WSL2-sleap-roots-pipeline.yaml`'s DAG only wires `models-downloader` → `predictor` →
`trait-extractor` (no local counterpart for either changed template) — real cluster access was
used instead, per user direction (2026-08-12) not to rely on the out-of-date local WSL2 DAG.

- [x] 4.1 Registered both updated templates on the live cluster (`argo template update`, namespace
      `runai-talmo-lab`) and submitted a real Workflow: `argo submit sleap-roots-pipeline.yaml
      --parameter scan-ids=289,577,1009` (the same 3-scan reference set as
      [sleap-roots-pipeline#33](https://github.com/talmolab/sleap-roots-pipeline/pull/33)'s prior
      real run) → `sleap-roots-pipeline-mqbhq`.
- [x] 4.2 Inspected both changed templates' pods via `kubectl get pod ... -o jsonpath=
      '{.spec.containers[?(@.name=="main")].env}'` (Argo substitutes `{{workflow.name}}` into the
      pod spec at creation time, so this is equivalent to and more reliable than an in-container
      `env` check for a short-lived pod). **Confirmed for both**: `ARGO_WORKFLOW_NAME` =
      `sleap-roots-pipeline-mqbhq` — the real resolved workflow name, not the literal
      `{{workflow.name}}` string. `images-downloader` succeeded (12s); `write-back` ran (its pod
      spec shows the same correctly-resolved env var) but its command itself failed 3/3 retries —
      see below, unrelated to this change. **Re-run after resolving that unrelated issue**
      (`sleap-roots-pipeline-tgmb8`, same `scan-ids=289,577,1009`): full 4/4 success, `write-back`
      green on the first attempt, `ARGO_WORKFLOW_NAME` again confirmed correctly resolved
      (`sleap-roots-pipeline-tgmb8`) in its pod spec.

      **Pasted evidence (PR #43 review flagged this claim as narrated-only, not shown —
      fixed here with the actual captured output):**
      ```
      $ kubectl get pod sleap-roots-pipeline-mqbhq-images-downloader-1518998170 -n runai-talmo-lab \
          -o jsonpath='{.spec.containers[?(@.name=="main")].env}'
      [{"name":"HOME","value":"/home/bloom"},{"name":"ARGO_WORKFLOW_NAME","value":"sleap-roots-pipeline-mqbhq"}, ...]

      $ kubectl get pod sleap-roots-pipeline-mqbhq-write-back-1999280327 -n runai-talmo-lab \
          -o jsonpath='{.spec.containers[?(@.name=="main")].env}'
      [{"name":"HOME","value":"/home/bloom"},{"name":"ARGO_WORKFLOW_NAME","value":"sleap-roots-pipeline-mqbhq"}, ...]

      $ kubectl get pod sleap-roots-pipeline-tgmb8-write-back-3193021068 -n runai-talmo-lab \
          -o jsonpath='{.spec.containers[?(@.name=="main")].env}'
      [{"name":"HOME","value":"/home/bloom"},{"name":"ARGO_WORKFLOW_NAME","value":"sleap-roots-pipeline-tgmb8"}, ...]
      ```
      All three show the real resolved workflow name, never the literal `{{workflow.name}}` string.
- [x] 4.3 N/A — live cluster access was available and used; no fallback needed.

**Unrelated finding, root-caused and resolved during this session (not a code regression):**
`write-back`'s first real run failed all 3 attempts with the identical error bloom issue #646
described (`blob upload failed ... "alg" (Algorithm) Header Parameter value not allowed`), despite
#646's fix (bloom PR #647) being merged to `staging` ~1 hour earlier. Root cause: the `staging`
GitHub Environment has a required-reviewer approval gate; an unrelated prior deploy (from a
2026-08-11 merge, verified during PR #43 review to touch only comment-string path updates in
`deploy.yml`/`docker-build-bloomcli.yml`/several `bloommcp/*.py` files after an OpenSpec archive
rename — zero executable/behavioral change, "docs-only" in effect) had sat unapproved for ~24h,
and because both deploy jobs share a
`cancel-in-progress: false` concurrency group, it blocked PR #647's deploy from ever running —
`status: pending`, zero steps executed. The fix itself was never wrong or reverted; it just hadn't
reached the running containers. User approved the pending deployment; re-running the same
Workflow (`sleap-roots-pipeline-tgmb8`) succeeded with `write-back` green (idempotent no-op on
these particular scans, but confirmed to have genuinely exercised the fixed Storage/JWT auth path
— `upload_blob` in `bloomcli/src/bloomctl/cyl/ingest.py` always calls `bucket.download()` first
even on a skip, and re-raises anything other than a `404`, so a still-broken auth path would have
failed identically to the first run). No GitHub issue/comment needed for this — already resolved,
recorded here and in the roadmap status log for the record.

## 5. Docs and cross-repo bookkeeping

- [x] 5.1 Update `docs/bloom-integration/roadmap.md`'s "Cross-repo correctness" subsection in all
      three places that go stale once this lands, linking to `design.md` rather than
      re-deriving the copy-forward reasoning: (a) this repo's table row — flip from "not yet
      started" to shipped; (b) the `bloomctl` row's "**#38's planned env var name**" wording,
      now shipped rather than planned; (c) the prose paragraph currently ending "...leaves the
      actual decision to whoever implements it. Not yet started — next in this repo's queue" —
      replace with the copy-forward decision and current status. Add a status-log entry noting
      the real-cluster validation and the unrelated, now-resolved staging-deploy-gate finding.
      Drafted, approved, committed.
- [x] 5.2 Commented on issue #38 with what shipped ([comment](https://github.com/talmolab/sleap-roots-pipeline/issues/38#issuecomment-5286220514)); closed #38. Commented on tracker
      issue #37 ([comment](https://github.com/talmolab/sleap-roots-pipeline/issues/37#issuecomment-5286221811)) noting completion, the still-open write-back
      unscoped-glob gap, and the manifest-visibility decision.
- [x] 5.3 Re-checked `salk-bloom` PR #655 (bloom #653): still `OPEN`, unmerged, `mergedAt: null` —
      unchanged in shape since this handoff was written. Nothing to reconcile.
- [x] 5.4 N/A — the #646-adjacent finding was root-caused and resolved within this session (stuck
      staging deploy-approval gate, not a code regression); no GitHub post needed.

## 6. Follow-up items found during PR #43 review (not yet due, tracked here)

- [ ] 6.1 **Image-tag/consumer coordination.** Both templates still pin
      `ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-c21d11b`, a build that predates
      `salk-bloom` PR #655 (bloom #653) — the actual, still-unmerged consumer of
      `ARGO_WORKFLOW_NAME`. This change proves the env var resolves correctly at the pod-spec
      level; it does **not** prove the currently-pinned `bloomctl` binary reads it (it can't —
      that code doesn't exist in this image yet). **When the pinned tag is next bumped** to a
      build that includes #655's merged work, re-confirm `ARGO_WORKFLOW_NAME`'s name and semantics
      still match what that `bloomctl` release actually expects (re-read its source, don't assume
      this proposal's snapshot is still accurate) before/as part of that image-bump PR.
- [ ] 6.2 **`templateRef` live-resolution timing, documented not fixed.** `sleap-roots-pipeline.yaml`'s
      DAG tasks use per-step `templateRef:` (not the whole-workflow `spec.workflowTemplateRef`,
      which alone gets snapshotted into `status.storedWorkflowTemplate` at submission). Argo's
      behavior here has a documented public ambiguity
      (argoproj/argo-workflows#1525) about whether step-level `templateRef` resolves against a
      snapshot or the live registered `WorkflowTemplate` object at each node's start — meaning
      `argo template update` while a workflow is in-flight has a theoretical ordering risk. Checked
      for this session's own real submits: `argo list -n runai-talmo-lab --running` showed no
      in-flight workflows in the namespace at the time either `argo template update` call was made,
      so no actual exposure occurred here. The general risk remains real and undocumented for
      future concurrent-batch operation (this repo's own roadmap A4 target) — flagging here rather
      than fixing, since resolving Argo's actual behavior needs upstream confirmation or a live
      test this change doesn't need to block on. Whoever builds concurrent-batch support (A4) should
      confirm Argo's actual behavior before assuming `argo template update` is safe mid-flight.

## 7. Merge conflict resolution + busch-lab re-validation (2026-08-13)

A concurrent session (`fix(pipeline): target runai-busch-lab as the pipeline's namespace`,
`d1ab43e`) landed on `main` while this branch was in progress, switching the pipeline's
`namespace`/`project` label from `runai-talmo-lab` to `runai-busch-lab` across all four templates
and the top-level Workflow. Separately, two more concurrent commits independently resolved the
same manifest-visibility question this change addresses and corrected mis-dated status-log
entries in `docs/bloom-integration/roadmap.md`.

- [x] 7.1 Merged `main` into this branch. The two changed templates and `sleap-roots-pipeline.yaml`
      auto-merged cleanly (non-overlapping lines: this branch's `ARGO_WORKFLOW_NAME` env-var
      addition vs. main's namespace/label switch). `docs/bloom-integration/roadmap.md` had two real
      conflicts — resolved by combining both sides' content (kept this branch's "shipped,
      real-cluster-validated" status plus main's date-corrected status-log entries and
      architectural framing), not by discarding either side.
- [x] 7.2 `openspec validate add-argo-workflow-name-env-var --strict` — clean after the merge.
- [x] 7.3 **Re-validated for real in `runai-busch-lab`** (the pipeline's now-actual target,
      post-merge), not just re-using the earlier `runai-talmo-lab` result: registered both updated
      templates (`argo template update`, `runai-busch-lab-argo-user` identity, matching this
      program's established convention of using `argo-user` for template management and
      `bloom-pipeline`'s real identity for submission) and submitted
      `sleap-roots-pipeline.yaml --parameter scan-ids=289,577,1009` under the `bloom-pipeline`
      identity → `sleap-roots-pipeline-l2247`. Full 4/4 success. Confirmed via
      `kubectl get pod ... -o jsonpath` on both changed templates' pods: `ARGO_WORKFLOW_NAME` =
      `sleap-roots-pipeline-l2247` (the real resolved name) in both. `write-back` logged
      `Ingested 0/4 envelopes -> /workspace/input (4 skipped)` — the same idempotent no-op as the
      `runai-talmo-lab` run (scans 289/577/1009 already ingested from prior real tests), consistent
      with `upload_blob`'s checksum-match-skip behavior, not a failure.
