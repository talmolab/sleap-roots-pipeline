# Design notes

The full design — the upstream Argo research this rests on, the rejected alternatives, and the
per-stage retry-safety analysis — is
`docs/superpowers/specs/2026-09-15-partial-success-exit-code-wiring-design.md`. This file covers
only the three decisions a reviewer needs in order to judge the spec deltas.

All Argo behaviour below is stated for **v3.6.7**, the version this cluster actually runs (read off
the `argoexec` wait-container image tag on live Argo pods). Earlier drafts of this design cited
v3.5.11 and `main`; where they disagree, v3.6.7 governs.

## Decision 1: why the gate exists

Argo cannot express "continue on exit 3 but not on exit 1", and this is not a matter of finding the
right field:

- `retryStrategy.expression` can stop the retry loop, but a node whose expression evaluates false
  is still `Failed`. It cannot turn a failure into a success.
- `continueOn` is two booleans on node *phase* (`error`, `failed`) with no exit-code field.
  Exit-code support was requested upstream (argo-workflows#6396); its implementation PR (#6702) was
  closed unmerged.

A maintainer ran exactly this shape — `retryStrategy` + `continueOn` + `dependencies` — in
argo-workflows#2798 and got workflow `Succeeded` with a "No more retries left" node inside. The
`depends` variant behaves the same (argo-workflows#12530, open since 2024-01).

So a `continueOn`-only change would report genuine crashes as green. The `exit-gate` re-derives the
final phase from the real exit codes, which is the only way to get it back.

## Decision 2: no `expression`, retries left intact

There is no per-scan retry anywhere in the producers. `stage_one_scan` has no retry loop, `bloomcli`
has no transport-level retry, and `MAX_SCAN_ATTEMPTS` — the per-scan attempt cap A4 §8's
retry-then-isolate is written against — is unimplemented in every repo.

Argo's whole-step retry is therefore the only scan-level retry that exists, and it works because
skip-if-done returns `skipped` for already-done scans rather than redoing them. Scenario 2
(2026-09-01) verified tail-only resume by file timestamp.

Adding `expression: 'lastRetry.exitCode != "3"'` would delete it: a scan that failed on a transient
blip and would have succeeded on attempt 2 gets permanently isolated on attempt 1. Leaving retries
in place makes the retry budget the de-facto `MAX_SCAN_ATTEMPTS`.

Cost, stated plainly: a permanently-poison scan burns its stage's retry budget first, and the
predictor's `backoff: {duration: 2m, factor: 2}` at `limit: 3` dominates — roughly 14 minutes of
wall-clock before the DAG proceeds. Accepted.

## Decision 3: the gate's strictness is the safety mechanism, not a DAG-shape plea

`{{tasks.<NAME>.exitCode}}` resolves through retry nodes (`buildLocalScope` calls
`possiblyGetRetryChildNode`), confirmed empirically on this cluster against a real failed run.
Ancestor scope is transitive (`workflow/common/ancestry.go::GetTaskAncestry` recurses), so the gate
can reference producers it does not directly depend on — which is what makes a terminal gate
possible at all in a linear DAG.

**Correction to an earlier draft of this design.** It claimed an unresolvable `{{tasks...}}`
reference "requeues the task indefinitely and hangs the workflow". That is **false at v3.6.7**:
`workflow/controller/dag.go` substitutes task arguments with
`template.Replace(..., allowUnresolved=true)`, so the literal string `{{tasks.<name>.exitCode}}`
passes through to the container unchanged, and `grep -i requeue` over that file returns nothing.
(For `when:`, an unresolved reference makes `shouldExecute` error and the node is marked `Error` —
also a deterministic failure, not a hang.) The claim came from a read of `main`, post-4.1.3, where
the code has since changed.

**Second correction, from actually running it.** The above is true of *runtime* substitution, but a
**non-ancestor** reference never reaches runtime: Argo's `validateDAGTaskArgumentDependency`
(`workflow/validate/validate.go` at v3.6.7) matches on the prefix `{{tasks.` — any suffix, so
`.exitCode` is covered — and rejects it at **both `argo lint` and submission** with
`missing dependency '<task>' for parameter '<name>'`. Verified by deliberately breaking the DAG
against this cluster. So restructuring the DAG so a producer stops being an ancestor cannot reach
the cluster silently, and an earlier draft of this document was wrong to say it could.

This correction matters because it changes what protects us, and in which direction. A broken
*ancestry* is caught loudly and early, by three independent layers: the static ancestry assertion
in `scripts/check_manifests.py`, Argo's own validator at lint and submit, and the gate. What has no
runtime error to rely on is the narrower case the validator cannot see — a task that **is** a valid
ancestor but produced no `outputs.exitCode`, reachable when a node is `Failed` without its main
container terminating. There the gate receives an empty or literal value, and rejecting anything
outside `{0, 3}` is the only thing that converts it into a visible failure. Hence two spec
requirements that would otherwise look like style:

- the gate compares against an explicit **allowlist**, never a denylist — a denylist of
  `{1, 2, 143}` would pass a literal placeholder, an empty string, and any future exit code;
- the codes arrive as **three separately-named parameters**, not one delimiter-joined value —
  shell word-splitting silently collapses an empty field, so a joined `"0,,0"` would iterate twice
  over `0` and pass.

The comparison lives in the gate container rather than in `when:` because `when:` is evaluated by
govaluate, not expr, so integer-coercion helpers are unavailable and mixed string/number comparison
is a parse error. Hyphenated task names are additionally hostile to govaluate.

A related reachable state the spec now covers: a node can be `Failed` with **no** `outputs.exitCode`
at all — `inferFailedReason` returns `Failed` as soon as `pod.Status.Message` is set (the kubelet
eviction path), while `exitCode` is only recorded when the main container actually terminated. The
gate sees an unsubstituted placeholder in that case, and rejects it.

## Decision 4: `failed: true` only, never `error: true`

`Failed` means the container ran and exited non-zero — exit `3`, or a graceful `SIGTERM`-to-`143`.
`Error` means the stage never produced a verdict, chiefly a pod **deleted** out from under Argo
(`markNodeError("pod deleted")`), which is how scheduler-driven preemption typically surfaces here
per this repo's own recorded observation. (Both eviction routes exist at v3.6.7 — a kubelet
eviction sets `pod.Status.Message` and yields `Failed` — so do not assume one; an earlier draft
asserted `Failed` unconditionally and was wrong.) A stage that never expressed an opinion should
stop the DAG rather than let it proceed on data that was never produced, so `error: true` stays
off. Both routes end red; they differ only in whether write-back runs first. The `Omitted` path is
clean — Argo creates a real `NodeOmitted` node and propagates the upstream failure.

Neither covers a pod that is never **scheduled**: at v3.6.7 `assessNodeStatus` maps `PodPending`
unconditionally to `NodePending` and there is no `ImagePullBackOff`/`FailedMount` handling, so such
a pod hangs rather than failing. Since the gate is the only leaf, it is the new single point where
that can strand a Workflow whose work is already done.

## Decision 5: write-back keeps its existing wiring

`bloomctl cyl batch-ingest-result` has no partial-success code — both exits are `ctx.exit(1)`, gated
on `needs_retry`. It gets no `continueOn`: if it fails, the gate is `Omitted`, inherits `Failed`, and
the Workflow fails.

This is safe for the targeted scenario for a non-obvious reason. `write_run_manifest` builds from
`{s.scan_key for s in result.scans if s.status in ("ok", "skipped")}` — it excludes failed scans. So
after a partial `images-downloader` the failed scan never enters the manifest, write-back never
looks for its result, and it exits `0`. The scan is still marked `failed` at the run level via
`fail_cyl_pipeline_run_scans_without_result`, which is keyed on `ARGO_WORKFLOW_NAME` and does not
consult the manifest.

A partial `predict`/`trait_extractor` does *not* have this property — those scans are in the
manifest, so write-back reports them missing, marks them **retriable**, and exits `1`. Out of scope
here and it does not affect the poison-scan target; tracked as bloom#859.

**Narrower than it first looks.** `write_run_manifest` merges with whatever is already on disk
(`merged = existing | this_run`) in a directory shared across runs *and environments*. So the
safety condition is not "failed scans are excluded" but "this scan_key was never successfully
staged into this shared directory by any prior run". True for scenario 3's never-uploadable poison
scan; not true in general. Two consequences now recorded in the full design doc: a zero-staged
batch can report `Succeeded`, and a crash path can run write-back scoped by another run's manifest.
`ARGO_WORKFLOW_NAME` is added to predictor and trait-extractor here (inert) so a producer-side
run-scope check becomes possible.

The gate sits *after* write-back rather than before it. That means a crash-class run still performs
its write-back before being declared `Failed`. Deliberate: write-back is idempotent, and on a
`143` or a manifest-write failure the downstream results are genuine — discarding their ingestion
would throw away good work in exactly the case where retries were exhausted, which contradicts the
principle motivating #56.

## Resolved: which image the gate runs

The already-pinned `bloomctl` image, reused purely for its shell (`python:3.11-slim` base). Avoids
adding a further un-drift-checked object (#58). Two consequences the template records: its
`ENTRYPOINT` is `["bloomctl"]` with no `CMD`, so `command` **must** be overridden or every Workflow
fails; and this pin must move in lockstep with the two other bloomctl templates.
