# Design: wiring the producers' partial-success exit code into the Argo DAG

Resolves [sleap-roots-pipeline#56](https://github.com/talmolab/sleap-roots-pipeline/issues/56).

All three producer stages already emit a distinct partial-success exit code (`3`); none of the
three `WorkflowTemplate`s react to it. `retryPolicy: Always` retries on any non-zero exit, so one
genuinely-failing scan exhausts the step's retries and kills the whole DAG — including for scans
that were already correctly staged. Demonstrated live on 2026-09-01: workflow
`sleap-roots-pipeline-jqsf9` ended `Failed` at **0/3** progress with 2 confirmed-good scans never
reaching the predictor.

## Why the obvious fix does not work

#56's own proposal — use `retryStrategy.expression` or a `continueOn`-based restructure — cannot
be implemented as stated. Argo offers two levers and neither does what is needed alone:

- **`retryStrategy.expression`** (v3.2+) can stop the retry loop, but a node whose expression
  evaluates false is still `Failed`. An expression cannot turn a failure into a success.
- **`continueOn`** can let the DAG proceed, but it keys only on node *phase* — it is two booleans
  (`error`, `failed`) with no exit-code field. Exit-code support was requested upstream
  ([argo-workflows#6396](https://github.com/argoproj/argo-workflows/issues/6396)) and its
  implementation PR ([#6702](https://github.com/argoproj/argo-workflows/pull/6702)) was closed
  unmerged.

So no combination distinguishes exit `3` from exit `1`-after-exhausted-retries. Worse, a
maintainer ran **exactly** this shape (`retryStrategy` + `continueOn` + `dependencies`) in
[argo-workflows#2798](https://github.com/argoproj/argo-workflows/issues/2798) and got workflow
`Succeeded` with a "No more retries left" node inside.

**A naive `continueOn` would therefore convert genuine crashes into green workflows — strictly
worse than today.** Today a crash at least fails the run correctly.

This also holds for the `depends` variant: `depends: "X.Succeeded || X.Failed"` reports the
workflow `Succeeded` too
([argo-workflows#12530](https://github.com/argoproj/argo-workflows/issues/12530), open since
2024-01; a maintainer describes a proper fix as breaking and unlikely to happen).

## Decisions made (conversationally, before this doc)

1. **`continueOn` + a terminal exit-code gate.** Restore correct final status with an explicit
   gate task rather than relying on Argo to preserve it, since Argo demonstrably will not.
2. **No `retryStrategy.expression` anywhere.** See "Retry policy" below — adding it would delete
   the only per-scan retry that currently exists.
3. **Containers are not modified.** A `command: ["/bin/sh","-c"]` wrapper mapping `3` to `0` would
   be simpler Argo-side, but it replaces each image's `ENTRYPOINT` outright (Kubernetes Pod v1:
   "The docker image's ENTRYPOINT is used if this is not provided") and POSIX `sh -c` does not
   forward `SIGTERM` to its child. predict and traits both ship deliberate `SIGTERM`-to-`143`
   handlers for graceful preemption, and clean tail-only resume under preemption is the one
   batch-oracle scenario that already passes (2026-09-01, scenario 2). Rejected to avoid
   regressing it.
4. **Image pin bumps are in scope**, because #56's wiring is inert without them.
5. **The `local-WSL2-*` variants are out of scope.** They are pre-A4 — no images-downloader or
   write-back stage exists in them at all, and they still reference `models-downloader` and GitLab
   `:latest` images. Bringing them to A4 is
   [#21](https://github.com/talmolab/sleap-roots-pipeline/issues/21).

## Mechanism

### `continueOn` on the three producers

`continueOn: {failed: true}` on the `images-downloader`, `predictor` and `trait-extractor` DAG
tasks. Placement matters: `continueOn` goes on the task **that fails**, and affects that task's
dependents (`workflow/common/ancestry.go::expandDependency` appends `|| <dep>.Failed` to each
dependent's compiled `depends`). Putting it on a downstream task instead does nothing useful and
trips a known upstream bug
([argo-workflows#13498](https://github.com/argoproj/argo-workflows/issues/13498), open; fix PR
#13501 unmerged for over a year).

`dependencies:` is retained throughout — **not** converted to `depends:`. Conversion is
all-or-nothing per DAG template and would forbid `continueOn` on every task in it
(`workflow/validate/validate.go:1472/1476`), and buys nothing since `depends` swallows final
status the same way (#12530).

### The `exit-gate` task

A new terminal task, the DAG's only leaf, which reads each producer's real exit code and fails
unless every one is in `{0, 3}`:

```yaml
- name: exit-gate
  dependencies: [write-back]
  arguments:
    parameters:
      - name: codes
        value: "{{tasks.images-downloader.exitCode}},{{tasks.predictor.exitCode}},{{tasks.trait-extractor.exitCode}}"
```

Because the gate is the sole target task, `assessDAGPhase` computes the DAG phase from it alone —
intermediate `Failed` nodes are not consulted. Gate succeeds, workflow `Succeeded`; gate fails,
workflow `Failed`.

`{{tasks.<NAME>.exitCode}}` is a documented DAG variable and **resolves correctly through retry
nodes** on any v3.x: `buildLocalScope` calls `possiblyGetRetryChildNode` to read the last real
attempt (`workflow/controller/operator.go`, present since v3.0.0). Confirmed empirically on this
cluster — a real failed run (`sleap-roots-pipeline-p8j6c`) shows `write-back` as a `Retry` node
with `phase: Failed` and `outputs.exitCode: 1` after three attempts.

The codes are passed as an **argument**, and the comparison is done in the gate container, rather
than via `when:`. `when:` is evaluated by **govaluate**, not expr, so `asInt`/`in`/`matches` are
unavailable there and mixed string/number comparison is a parse error; and an unresolvable
`{{tasks...}}` reference in `when:` **requeues the task indefinitely** rather than failing
(`dag.go::resolveDependencyReferences`). Keeping the logic in the container avoids both.

### Write-back is deliberately untouched

`bloomctl cyl batch-ingest-result` has no partial-success code — both its exits are
`ctx.exit(1)`, gated on `batch_result.needs_retry`. It keeps its existing `retryStrategy` and gets
no `continueOn`: if it fails, the gate is `Omitted`, inherits `Failed`, and the workflow fails.
Correct without any additional wiring.

### Retry policy: retries, *then* isolate

`retryPolicy: Always` and the existing per-stage limits are **unchanged**, and no `expression` is
added. This is a deliberate reversal of #56's suggested approach.

The reason: there is no per-scan retry anywhere in the producers. `stage_one_scan` has no retry
loop (first error produces `ScanResult(..., "failed")`), `bloomcli` has no transport-level retry,
and `MAX_SCAN_ATTEMPTS` — the per-scan attempt cap A4 §8's retry-then-isolate is written against —
is unimplemented in every repo. `download_frames_for_predict` is stricter still: a `stop` Event
means one frame's write failure marks every not-yet-started frame of that scan failed without
attempting it.

So Argo's whole-step retry is currently the *only* mechanism providing scan-level retry — and it
works, because skip-if-done makes re-runs cheap: already-staged scans return `skipped`, and a
skip-everything predictor run was measured at 11s. Scenario 2 (2026-09-01) verified tail-only
resume by file timestamp, not merely by workflow status.

Adding `expression: 'lastRetry.exitCode != "3"'` would remove it: a scan that failed on a
transient network blip and would have staged fine on attempt 2 gets permanently isolated on
attempt 1.

Leaving retries in place makes the retry budget the de-facto `MAX_SCAN_ATTEMPTS`, which is
literally what §8 asks for: retry the batch N times (transient per-scan failures get real
re-attempts, already-done scans skip), then on a persistent exit `3`, isolate that scan and
continue.

Cost: a permanently-poison scan burns its stage's full retry budget before the DAG proceeds.
Accepted, because those retries are cheap and the alternative loses real recovery.

### Image pins

| Template | From | To | Carries |
|---|---|---|---|
| images-downloader, write-back | `bloomctl:sha-3659705` | `sha-0614889` (`sha256:e39b4746…`) | bloom#830's exit `3` **and** bloom#774's per-scan status marking |
| predictor | `sleap-roots-predict:sha-f974632…` | `sha-e025e309…` (`sha256:4d4064c6…`) | predict#42's `run_manifest.json` forward-copy |
| trait-extractor | `sleap-roots-trait-extractor:sha-689cffb` | **no change** | already current — see below |

trait-extractor's pin is **not** stale, unlike the other three. `689cffb` is 2026-08-21 16:50;
`sleap-roots` `main` has advanced only to `094992d` (an OpenSpec archive commit ten minutes
later), and no commit has touched `trait_extractor/` since the pin.

Tag conventions differ per repo and must not be inferred: `bloomctl` tags are **7-char**
(`sha-623414f` resolves, `sha-623414f7` 404s), `sleap-roots-predict` uses the **full 40-char** sha.
Both were verified by querying GHCR directly rather than derived from `git rev-parse --short`,
which abbreviates differently than the CI runner does.

## Error handling

| Exit | Meaning | Retried? | DAG proceeds? | Workflow phase |
|---|---|---|---|---|
| `0` | all scans succeeded | no | yes | `Succeeded` |
| `3` | batch completed, some scans isolated-failed | yes, to limit | yes, via `continueOn` | `Succeeded` (gate allows `3`) |
| `1` | crash / abort | yes, to limit | yes, via `continueOn` | **`Failed`** (gate rejects) |
| `2` | CLI usage error | yes, to limit | yes | **`Failed`** (gate rejects) |
| `143` | `SIGTERM` (preemption) | yes, to limit | yes | **`Failed`** (gate rejects) |

**Empty stage-in needs no special guard.** If *every* scan fails to stage, bloomctl still exits
`3`, `continueOn` proceeds, and predict hits an empty input directory and exits `1` — which the
gate rejects, failing the workflow. A batch that staged nothing should fail, so this is the right
outcome. The cost is some wasted downstream retries before the gate concludes.

Note the stages disagree on empty input, which is why the gate reads producers' codes rather than
assuming uniformity: bloomctl exits `0` on zero requested scans, predict exits `1`, and traits
exits `1` with no manifest or `3` with one. The trait-extractor template's existing comment
claiming an empty `/in` exits 0 (a silent-green node) is stale — sleap-roots#266 closed that — and
is corrected as part of this change.

## Testing

`argo lint` on every changed manifest. Note it does **not** validate `retryStrategy.expression`
syntax (`validate.go:687` checks only `retryPolicy`) — not a concern here, since this design adds
no expression, but relevant if one is ever added.

Live verification on staging, experiment `A4-PIPELINE-E2E-TEST`, re-running 2026-09-01's
scenario 3 (one scan pointing at never-uploaded object storage content, alongside two genuinely
good scans):

1. **Poison scan.** DAG reaches `write-back`; both good scans' results land on the NFS mount and
   in `cyl_trait_sources`; the poison scan is marked `failed`; `done_count=2`, `failed_count=1`;
   workflow `Succeeded`.
2. **Crash injection — the more important test.** Force a crash-class exit and confirm the gate
   still fails the workflow. Without this, the change cannot be claimed safe, because converting
   real crashes into green workflows is precisely this approach's failure mode.

Pass signals verified by artifact, not by workflow status alone — per the 2026-09-01 precedent of
checking file mtimes rather than trusting the phase.

## Known remaining gaps (explicitly not fixed here)

- **Run status will read `complete`, not `partial`.** The status poller's `rollup()` decides from
  Argo workflow phases only, and every Argo continue-past-failure mechanism yields `Succeeded`, so
  `partial` is unreachable from this repo at any batch size. Filed as
  [bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857). Until it
  lands, expect `complete` with `failed_count > 0`. **Do not read a green workflow as "no scans
  failed."**
- **predict's forwarded manifest must narrow to `ok ∪ skipped`.** Once the DAG can reach traits
  after a partial predict, every predict-failed scan becomes a misattributed *trait-extraction*
  failure (`trait_extractor/extractor.py:271-280`). predict recorded this as an expiring decision
  keyed on #56 landing; filed as
  [sleap-roots-predict#44](https://github.com/talmolab/sleap-roots-predict/issues/44).
- **`MAX_SCAN_ATTEMPTS`** remains unimplemented. The retry budget stands in for it.

## Risks

- **This deploys to production.** prod and staging deliberately share the `runai-busch-lab`
  namespace, disambiguated only by `WORKFLOWS_K8S_ENV_LABEL`, and prod's workers are genuinely
  running. Every `argo template update` affects both environments' future dispatches.
- **No drift-check exists for these templates**
  ([#58](https://github.com/talmolab/sleap-roots-pipeline/issues/58)), so the cluster's registered
  copy can silently diverge from this repo — the mechanism behind #51/#52/#54/#55 each having to
  be caught by hand.
- **Cross-repo lockstep.** `sleap-roots-pipeline.yaml` is vendored by `salk-bloom` at
  `services/workflows/vendored/` with a pinned `SLEAP_ROOTS_PIPELINE_REF` (currently `9df1e52`,
  presently byte-identical). A DAG edit requires bumping both there. Note the drift check only
  fires when a *bloom* PR touches those paths, so it will not flag upstream drift on its own.
- **The gate adds a pod per workflow**, and on a crash path the downstream stages run wastefully
  before the gate concludes.
- **Upstream behaviour change risk.** If argo-workflows#13501 ever merges, `continueOn` semantics
  shift. This design depends only on the well-tested `continueOn`-on-the-failing-task shape
  (`TestContinueOnFailDag`), not on the buggy downstream-task variant.

## Is retrying on exit `3` safe per stage?

Leaving retries on means a persistent exit `3` re-runs the stage, so each stage's skip-if-done has
to be trustworthy or a retry could redo or corrupt already-good work.

- **images-downloader** — safe. `scan_is_already_staged` validates the sidecar, not just the
  directory's existence, and holds a per-scan lock across the skip-check-through-sidecar-write
  window (bloom#533).
- **trait-extractor** — safe. Skip-if-done compares
  `(provenance.idempotency_key, provenance.contract_version)` against the existing
  `{scan_key}.result.json` (`trait_extractor/extractor.py:105`) — content-derived, not mere file
  existence.
- **predictor** — the weakest of the three, and knowingly so. Its skip is **existence-only**, and
  the template's own comment already warns that a mid-write eviction can leave a truncated
  `.predictions.json` that a retry trusts as done, concluding that more retries widen that window
  and the limit should be gated on atomic-write plus checksum-verified skip. This design does not
  widen it — the limit stays at its current value and no new retries are added — but it does not
  close it either. It remains predict's to fix (predict#43 covers the atomic-write half).

## Open questions

- Which image does the `exit-gate` run? Reusing an already-pinned image avoids adding a supply
  chain dependency; a small public base is simpler but new. To settle at implementation time.
