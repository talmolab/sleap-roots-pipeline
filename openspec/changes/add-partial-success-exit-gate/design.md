# Design notes

The full design — including the upstream Argo research this rests on, the rejected alternatives,
and the per-stage retry-safety analysis — lives at
`docs/superpowers/specs/2026-09-15-partial-success-exit-code-wiring-design.md`. This file records
only the decisions a reviewer needs in order to judge the spec deltas, and does not restate it.

## Decision 1: why `continueOn` alone is not the fix

Argo cannot express "continue on exit 3 but not on exit 1", and this is not a matter of finding
the right field:

- `retryStrategy.expression` (v3.2+) can stop the retry loop, but a node whose expression
  evaluates false is still `Failed`. It cannot turn a failure into a success.
- `continueOn` is two booleans on node *phase* (`error`, `failed`) with no exit-code field.
  Exit-code support was requested upstream (argo-workflows#6396); its implementation PR (#6702)
  was closed unmerged.

A maintainer ran exactly this shape — `retryStrategy` + `continueOn` + `dependencies` — in
argo-workflows#2798 and got workflow `Succeeded` with a "No more retries left" node inside. The
`depends` variant behaves the same way (argo-workflows#12530, open since 2024-01).

So a `continueOn`-only change would convert genuine crashes into green workflows. The `exit-gate`
exists to undo precisely that, by re-deriving the final phase from the real exit codes.

## Decision 2: no `expression`, retries left intact

There is no per-scan retry anywhere in the producers. `stage_one_scan` has no retry loop,
`bloomcli` has no transport-level retry, and `MAX_SCAN_ATTEMPTS` — the per-scan attempt cap A4 §8's
retry-then-isolate is written against — is unimplemented in every repo.

Argo's whole-step retry is therefore the only scan-level retry that exists, and it works because
skip-if-done returns `skipped` for already-done scans rather than redoing them. Scenario 2
(2026-09-01) verified tail-only resume by file timestamp.

Adding `expression: 'lastRetry.exitCode != "3"'` would delete it: a scan that failed on a transient
blip and would have succeeded on attempt 2 gets permanently isolated on attempt 1. Leaving retries
in place makes the retry budget the de-facto `MAX_SCAN_ATTEMPTS`.

Cost, stated plainly: a permanently-poison scan burns its stage's retry budget first. The
predictor's `backoff: {duration: 2m, factor: 2}` at `limit: 3` dominates — roughly 14 minutes of
wall-clock before the DAG proceeds. Accepted.

## Decision 3: the gate reads exit codes, and this constrains the DAG's shape

`{{tasks.<NAME>.exitCode}}` resolves through retry nodes on any v3.x (`buildLocalScope` calls
`possiblyGetRetryChildNode`), confirmed empirically on this cluster against a real failed run.

The gate references producers it does not directly depend on, which resolves only because the DAG
is linear and they are all its *ancestors*. **If the DAG is ever parallelized so a referenced
producer is no longer an ancestor of the gate, the workflow hangs rather than fails** — an
unresolvable `{{tasks...}}` reference causes the controller to requeue indefinitely. The spec
delta pins this as a requirement so it is checked rather than remembered.

The comparison lives in the gate container, not in `when:`. `when:` is evaluated by govaluate, not
expr, so `asInt`/`in`/`matches` are unavailable and mixed string/number comparison is a parse
error; and the same requeue-on-unresolvable behaviour applies there too.

## Decision 4: `failed: true` only, never `error: true`

`Failed` means the container ran and exited non-zero — which covers exit `3` and also RunAI
eviction (`inferFailedReason` returns `Failed`, not `Error`, when `pod.Status.Message` is set).
`Error` means the stage never ran at all: image pull failure, wait-container death. A stage that
never expressed an opinion should stop the DAG, not be continued past on data that was never
produced.

## Decision 5: write-back keeps its existing wiring

`bloomctl cyl batch-ingest-result` has no partial-success code — both exits are `ctx.exit(1)`,
gated on `needs_retry`. It gets no `continueOn`: if it fails, the gate is `Omitted`, inherits
`Failed`, and the workflow fails. Correct without extra wiring.

This is safe for the targeted scenario for a non-obvious reason. `write_run_manifest` builds from
`{s.scan_key for s in result.scans if s.status in ("ok", "skipped")}` — it excludes failed scans.
After a partial `images-downloader` the failed scan never enters the manifest, so write-back never
looks for its result and exits `0`. The scan is still marked `failed` at the run level via
`fail_cyl_pipeline_run_scans_without_result`, which is keyed on `ARGO_WORKFLOW_NAME` and does not
consult the manifest.

A partial `predict`/`trait_extractor` does *not* have this property — those scans are in the
manifest — and will fail the workflow at write-back until bloom#859 lands. Out of scope here, and
it does not affect the poison-scan target.

## Open question

Which image the `exit-gate` runs. Reusing an already-pinned image avoids adding a supply-chain
dependency and a further drift-prone object (#58); a minimal public base is simpler but new.
Settled at implementation time in favour of reusing the already-pinned `bloomctl` image.
