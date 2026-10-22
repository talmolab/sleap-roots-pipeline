# Design: production runbook

## Context

#132 asks for one page. Most of its content already exists, in sources that have owners and are
kept current by their own process. Two `/review-openspec` rounds shaped this design. Round 1
(2026-10-04) and round 2 (2026-10-16) were both BLOCKED, then revised. They found five problems:

- "Predict first" is not a general rollback rule.
- Two standing procedures disagree with the page: `/tdd` step 3 has no idle check, and the
  semaphore header owns stuck-Pending recovery.
- Several linked texts are stale (pre-a9 or pre-#137) or limited to one environment.
- Some planned checks could never go red.
- One planned README rewrite was itself false. A crashed stage-in does not always leave no
  manifest.

The owner chose to fix every linked claim in this PR (option (a), 2026-10-16).

## Decisions

### The runbook owns the guard procedure, and links everything else

**Where the guard is restated today.** The idle guard appears in at least five places, and none of
them is complete:

- the roadmap's hard constraint, which says "Running or Pending", not "or no phase", and has no
  rollback copy;
- `/tdd` step 3, which has no idle check;
- `openspec/project.md`'s Live acceptance bullet, which has no idle check;
- a completed frontier item (item 6);
- the dated status-log entries. These hold the lessons: re-guard in the same command, read back the
  digest env, and the `No workflows found` false positive.

**What changes.** The page becomes the canonical statement. The hard constraint keeps the reach
fact and links the page. `/tdd` step 3 and project.md link the page. The completed item and the
status log stay as history; the page cites the 2026-10-02 (deploy) entry as evidence for the
`.status.phase` lesson.

**What stays out of the guard.** `check_cluster_drift.sh`'s header, `test.md` and `pre-merge.md`
mention the drift check but don't restate the idle condition, so they are left alone. The
semaphore retune (`kubectl patch`) belongs to its header.

**Identity.** The guard runs under `argo-user`, which can `get`, `list` and `watch` Workflows
(`kubectl auth can-i`, 2026-10-16).

**Owners the page links instead of copying:**

| #132 section | Owner the page links |
|---|---|
| Reach of a change | `cluster-identities.md` "Namespace facts that bite" |
| Not a pause | `cluster-identities.md` "Namespace facts that bite" |
| Rollback | the trait-extractor `Rollback` comment (entry point); predictor; images-downloader for bloomctl |
| Directory and Secret preconditions | `cluster-identities.md` storage and Secrets paragraphs |
| Shared semaphore slot | `sleap-roots-pipeline-semaphores.yaml` header; #106 |
| Failure mechanics | `ci-debug.md` §A |
| Failure outcome | exit-gate template header; bloom#859, bloom#857 |
| GPU reorder | predictor template comment; #127 |
| Git Bash | `openspec/project.md` Testing Strategy; #128 |

### Rollback: enter from the trait-extractor comment

**How the layers work.** Undoing the latest traits deploy means unlink, then re-pin traits alone.
Predict goes first only when going further back, to undo bloom#971 phase 1.

**What the page says.** The trait-extractor comment states those layers in order, so the page sends
the operator there and does not copy the layers. A future deploy adds a layer at its source, not on
the page.

**The unlink side effect.** `unlink()` also drops `candidate` and `latest` (training#72's
correction, roadmap 2026-10-05 entry). That fact goes into the comment, since the comment owns the
procedure.

**Below the a9 floor.** That is not offered as a rollback. It reverses row 6, and its pre-a9 writer
would start a new cumulative legacy manifest in `bloom_cyl_pipeline/prod`, which never had one, so
there is nothing to restore.

### Failure evidence: the TTL window

Verified read-only:

- **Bloom `main`.** `k8s_client.build_workflow_body`, which is called only from the cyl dispatch
  worker, sets `ttlStrategy.secondsAfterCompletion` from `WORKFLOWS_K8S_TTL_SECONDS`. The default
  is 3600 in both `.env.*.defaults`. Bloom keeps no cyl pod logs; `get_pod_log` has no non-test caller. No line numbers are cited, because they drift (#137's `:347` is already `:352`).
- **Live, 2026-10-16.** Four `environment: prod` Workflows carry `secondsAfterCompletion: 3600`.
  Hand-submitted Workflows carry none.
- **Unreadable.** The controller's podGC default can't be read, so pods may go sooner.

The page therefore says "at most", names the variable, links #137, and copies no number.

### Spec placement

**cluster-access-docs (ADDED).** Both ADDED requirements extend it. That spec owns this repo's
operator-doc claims and already has the no-parity / point-at-the-drift-check rule the page depends
on.

**per-batch-pipeline (MODIFIED).** Its "Every producer carries the Argo workflow identity"
requirement explains itself with the pre-a9 accumulation, in the present tense. The MODIFIED delta
rewords only that paragraph, so the scenario and the behavior are unchanged. It is the one
claim-wide correction that lives in a spec rather than a doc, so it can't be asserted by
`check_docs.py` before archive; the delta is its record.

### Mechanical checks, and their limits

- **Section-scoped checks** slice to the next heading of any kind, so a reordered page fails only
  the order check.
- **Claim-wide checks** run over ordered file lists that include the runbook.
- **The no-pin check** covers tags, digests and bare commit SHAs.
- **Relative links** must resolve.
- **The no-pin check's limits:** its bare-SHA pattern skips a hex string after `/` or `-` (for
  example, inside a commit URL). That is acceptable, because the page links issues, not commits.
- **Dated plans and specs are exempt** from the claim-wide corrections, like status-log entries.
  `2026-09-15-cluster-identities-and-namespace-drift.md`'s "only by an env label" is one example.
- **Anchors** inside linked documents aren't checked; a broken one is a dead link, not a false
  claim.
- **Paraphrase drift** can't be checked and is left to review.

## Non-goals

- The status dashboard, while #136 is open on it. Post-merge.
- runai SKILL §8. Its "Mount error" row is about `runai workspace --host-path`, whose volume type
  isn't verified here. Its pod-log row is about a running pod, inside any TTL.
- Any cluster, Bloom or registry write. The two template edits are comments, and the parsed YAML is
  unchanged.

## Risks

- **The listed issue links go stale as issues close.** Removing one fails the assertion, so its
  remover must update the assertion in the same change.
- **`tdd.md` and `ci-debug.md` are rendered from vault templates.** A re-render could drop these
  edits. That is tracked as a post-merge task.
