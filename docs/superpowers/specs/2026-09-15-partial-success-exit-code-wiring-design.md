# Design: wiring the producers' partial-success exit code into the Argo DAG

Resolves [sleap-roots-pipeline#56](https://github.com/talmolab/sleap-roots-pipeline/issues/56).

All three producer stages already emit a distinct partial-success exit code (`3`); none of the
three `WorkflowTemplate`s react to it. `retryPolicy: Always` retries on any non-zero exit, so one
genuinely-failing scan exhausts the step's retries and kills the whole DAG — including for scans
that were already correctly staged. Demonstrated live on 2026-09-01: workflow
`sleap-roots-pipeline-jqsf9` ended `Failed` at **0/3** progress with 2 confirmed-good scans never
reaching the predictor.

**Scope: deliberately minimal.** This change fixes the Argo wiring and the image pins, and nothing
else. Three related defects found while designing it are filed and explicitly deferred — see
"Deferred, with issues" below. Each is real; none blocks the batch-oracle poison-scan target.

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
worse than today.** Today a crash at least fails the run correctly. The `exit-gate` below exists
solely to undo that.

This also holds for the `depends` variant: `depends: "X.Succeeded || X.Failed"` reports the
workflow `Succeeded` too
([argo-workflows#12530](https://github.com/argoproj/argo-workflows/issues/12530), open since
2024-01; a maintainer describes a proper fix as breaking and unlikely to happen).

## Decisions

1. **`continueOn` + a terminal exit-code gate.** Restore correct final status with an explicit
   gate task rather than relying on Argo to preserve it, since Argo demonstrably will not.
2. **No `retryStrategy.expression` anywhere.** See "Retry policy" — adding it would delete the
   only per-scan retry that currently exists.
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

**`failed: true` only — deliberately not `error: true`.** Argo distinguishes `Failed` (the
container ran and exited non-zero) from `Error` (the stage never produced a verdict). A producer's
exit `3` is always `Failed`, as is a graceful `SIGTERM`-to-`143`.

**Eviction is not one answer, and an earlier draft of this document got it wrong.** Verified at
v3.6.7, both routes exist: `case apiv1.PodFailed` → `inferFailedReason` → `NodeFailed` when
`pod.Status.Message` is set (the kubelet-eviction shape), *but* a pod **deleted** out from under
Argo goes to `markNodeError("pod deleted")` → `NodeError`. This repo's own recorded observation —
`sleap-roots-images-downloader-template.yaml`'s note that RunAI eviction under CPU-pool contention
"typically surfaces as an Error-phase node" — is empirical for this cluster and outranks the
theoretical reading, so assume preemption usually yields `Error` here.

That is fine, and is why `error: true` is still omitted: an `Error` means the stage never expressed
an opinion, so the DAG should stop rather than continue on data that was never produced. Both
routes end red — `Failed` flows through `continueOn` to the gate, which rejects `143`; `Error`
stops the DAG, the gate is `Omitted` and inherits `Failed`. What differs is only whether write-back
runs first. Omitting `error: true` is the choice, not an oversight.

`dependencies:` is retained throughout — **not** converted to `depends:`. Conversion is
all-or-nothing per DAG template and would forbid `continueOn` on every task in it
(`workflow/validate/validate.go:1326/1327` at v3.6.7), and buys nothing since `depends` swallows final
status the same way (#12530).

### The `exit-gate` task

A new terminal task — the DAG's only leaf — which reads each producer's real exit code and fails
unless every one is in `{0, 3}`. Illustrative shape only; the full task carries a `templateRef`
and the referenced template declares the matching `inputs.parameters`:

```yaml
# illustrative — see the manifests for the complete task + template
- name: exit-gate
  dependencies: [write-back]
  templateRef:
    name: sleap-roots-exit-gate-template
    template: exit-gate
  arguments:
    parameters:
      - name: images-downloader-code
        value: "{{tasks.images-downloader.exitCode}}"
      - name: predictor-code
        value: "{{tasks.predictor.exitCode}}"
      - name: trait-extractor-code
        value: "{{tasks.trait-extractor.exitCode}}"
```

The gate template itself carries four things `argo lint` will not check, each of which is a real
hazard if omitted:

- **`command: ["/bin/sh","-c"]`** — mandatory. The reused `bloomctl` image sets
  `ENTRYPOINT ["bloomctl"]` and no `CMD`, so the args-only convention the other four templates
  follow would run `bloomctl <script>` and exit 2, failing **every** workflow including successful
  ones. This is the one place the "containers are not modified" decision is deliberately inverted —
  the gate is ours, not a producer.
- **an explicit `priorityClassName`** — an Argo pod with none lands at very-high (150) on this
  cluster, *above* the GPU predictor's `high` (125), which would make a trivial `sh` pod the
  highest-priority thing in the pipeline.
- **a `retryStrategy` with `retryPolicy: Always`** — the gate is the only leaf, so a single
  image-pull blip or preemption would otherwise report a fully-successful batch as `Failed`.
- **`resources.requests`** — otherwise the pod is BestEffort QoS and is first evicted under node
  pressure, at the one point in the DAG where all the real work is already done.

It deliberately declares **no** `volumeMounts` and no `HOME`: Argo only attaches volumes a mount
names, so neither the NFS `hostPath` volumes nor the credentials Secret reach this pod. The gate
reads no data and makes no Bloom call.

Because the gate is the sole target task — leaves are the default targets and no `dag.targets` is
set — `assessDAGPhase` computes the DAG phase from it alone; intermediate `Failed` nodes are not
consulted. Gate succeeds, workflow `Succeeded`; gate fails, workflow `Failed`.

`{{tasks.<NAME>.exitCode}}` is a documented DAG variable and **resolves correctly through retry
nodes** on any v3.x: `buildLocalScope` calls `possiblyGetRetryChildNode` to read the last real
attempt (`workflow/controller/operator.go`, present since v3.0.0). Confirmed empirically on this
cluster — a real failed run (`sleap-roots-pipeline-p8j6c`) shows `write-back` as a `Retry` node
with `phase: Failed` and `outputs.exitCode: 1` after three attempts.

**Constraint: the gate references tasks it does not directly depend on, which works only because
this DAG is linear.** Task-scope resolution draws on a task's *ancestors*
(`workflow/common/ancestry.go::GetTaskAncestry` recurses through dependencies), and in a linear
chain (`images-downloader` → `predictor` → `trait-extractor` → `write-back` → `exit-gate`) all
three producers are ancestors of the gate.

**What happens if that is ever broken is the opposite of what an earlier draft of this document
claimed.** It said an unresolvable `{{tasks...}}` reference "requeues the task indefinitely",
hanging the workflow. That is **false at v3.6.7** — the version this cluster actually runs, read
off the `argoexec` wait-container image tag on live Argo pods. In `workflow/controller/dag.go` at
that tag, task arguments are substituted with
`template.Replace(string(taskBytes), woc.globalParams.Merge(scope.getParameters()), true)` — the
trailing `true` is `allowUnresolved` — so the literal string `{{tasks.<name>.exitCode}}` passes
through to the container unchanged. `grep -i requeue` over that file returns nothing. (The claim
came from a read of `main`, post-4.1.3, where the code has since changed.)

**Second correction, from actually running it.** The above is true of *runtime* substitution, but a
non-ancestor reference never gets that far: Argo's `validateDAGTaskArgumentDependency` rejects it at
**both `argo lint` and submission** with `missing dependency '<task>' for parameter '<name>'`.
Verified on this cluster by deliberately breaking the ancestry — both the lint and the submit
refused. So "restructure the DAG and it silently hangs" was wrong in the safe direction; that
mistake cannot reach the cluster.

The allowlist still earns its place, for a case the validator cannot see: a task that **is** a valid
ancestor but produced no `outputs.exitCode`, reachable when a node is `Failed` without its main
container terminating. There the empty or literal value does reach the container at runtime.

Net: three layers, each catching something the others do not — the static ancestry assertion in
`scripts/check_manifests.py` (no cluster needed), Argo's validator at lint and submit, and the
allowlist at runtime. Two details of the gate remain load-bearing rather than cosmetic:

- **The comparison is an allowlist, never a denylist.** There is no runtime error to rely on, so
  the only thing that makes a broken reference visible is the gate rejecting anything that is not
  exactly `0` or `3`. A denylist of `{1, 2, 143}` would silently pass a literal placeholder, an
  empty string, and any future exit code.
- **The codes arrive as three separately-named parameters, not one joined string.** Shell
  word-splitting collapses an empty field, so a joined `"0,,0"` would iterate twice over `0` and
  pass — defeating the very case the test vectors exist to catch.

The comparison lives in the gate container rather than in `when:` because `when:` is evaluated by
**govaluate**, not expr, so `asInt`/`in`/`matches` are unavailable and a mixed string/number
comparison is a parse error; hyphenated task names are additionally hostile to it. (An unresolved
reference in `when:` does fail rather than hang — `shouldExecute` errors and the node is marked
`Error` — but the govaluate limitations stand on their own.)

A related reachable state: a node can be `Failed` with **no** `outputs.exitCode` at all.
`inferFailedReason` returns `Failed` as soon as `pod.Status.Message` is set — the kubelet-eviction
path — while `exitCode` is only recorded when the main container actually terminated. The gate
receives an unsubstituted placeholder in that case, and the allowlist rejects it.

### Write-back is untouched — and why that is safe *here*

`bloomctl cyl batch-ingest-result` has no partial-success code: both its exits are `ctx.exit(1)`,
gated on `batch_result.needs_retry`. It keeps its existing `retryStrategy` and gets no
`continueOn`. If it fails, the gate is `Omitted`, inherits `Failed`, and the workflow fails —
correct without extra wiring.

This is safe for the scenario #56 targets, but for a narrower reason than an earlier draft claimed.
`write_run_manifest` builds `this_run_scan_keys` from
`{s.scan_key for s in result.scans if s.status in ("ok", "skipped")}`
(`download_for_predict.py:472`) — it **excludes failed scans** — but the next lines merge that with
whatever is already on disk (`merged = existing_scan_keys | this_run_scan_keys`) in a directory
shared across runs *and environments*. So the real safety condition is not "failed scans are
excluded" but **"this scan_key was never successfully staged into this shared directory by any
prior run"**. That holds for scenario 3's never-uploadable poison scan, which is why the target
case is safe — but it does not generalise: a scan that staged fine last week and fails transiently
today re-enters the manifest from the earlier run. So after a partial
`images-downloader`, the failed scan never enters the manifest, write-back never looks for its
result, `missing_scan_keys` stays empty, and write-back exits `0`. The scan is still marked
`failed` at the run level, via `fail_cyl_pipeline_run_scans_without_result` keyed on
`ARGO_WORKFLOW_NAME`, which does not consult the manifest.

**A partial `predict` or `trait_extractor` is a different story**, and is a real deferred gap —
see [bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859) under
"Deferred, with issues".

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
works, because skip-if-done means already-done scans return `skipped` rather than being redone.
Scenario 2 (2026-09-01) verified tail-only resume by file timestamp, not merely by workflow
status.

Adding `expression: 'lastRetry.exitCode != "3"'` would remove it: a scan that failed on a
transient network blip and would have staged fine on attempt 2 gets permanently isolated on
attempt 1.

Leaving retries in place makes the retry budget the de-facto `MAX_SCAN_ATTEMPTS`, which is
literally what §8 asks for: retry the batch N times (transient per-scan failures get real
re-attempts, already-done scans skip), then on a persistent exit `3`, isolate that scan and
continue.

**Cost, stated honestly.** A permanently-poison scan burns its stage's full retry budget before
the DAG proceeds. Per-attempt compute is cheap (a skip-everything predictor run was measured at
11s), but the predictor's `backoff: {duration: 2m, factor: 2}` with `limit: 3` dominates: roughly
2 + 4 + 8 ≈ **14 minutes of wall-clock** before the DAG moves on. images-downloader and
trait-extractor have no backoff, so theirs is negligible. Accepted: real per-scan recovery is
worth more than that delay, and the alternative removes recovery entirely.

### Is retrying on exit `3` safe per stage?

A persistent exit `3` re-runs the stage, so each stage's skip-if-done has to be trustworthy or a
retry could redo or corrupt already-good work.

- **images-downloader** — safe. `scan_is_already_staged` validates the sidecar, not just the
  directory's existence, and holds a per-scan lock across the skip-check-through-sidecar-write
  window (bloom#533).
- **trait-extractor** — safe. Skip-if-done compares
  `(provenance.idempotency_key, provenance.contract_version)` against the existing
  `{scan_key}.result.json` (`trait_extractor/extractor.py:105`) — content-derived, not mere file
  existence.
- **predictor** — the weakest of the three, knowingly. Its skip is **existence-only**, and the
  template's own comment already warns that a mid-write eviction can leave a truncated
  `.predictions.json` that a retry trusts as done, concluding that more retries widen that window
  and the limit should be gated on atomic-write plus checksum-verified skip. This design does not
  widen it — the limit is unchanged and no new retries are added — but it does not close it
  either. It remains predict's to fix (predict#43 covers the atomic-write half).

### Image pins

| Template | From | To | Carries |
|---|---|---|---|
| images-downloader, write-back | `bloomctl:sha-3659705` | `sha-0614889` (`sha256:e39b4746…`) | bloom#830's exit `3` **and** bloom#774's per-scan status marking |
| predictor | `sleap-roots-predict:sha-f974632…` | `sha-e025e309…` (`sha256:4d4064c6…`) | predict#42's `run_manifest.json` forward-copy |
| trait-extractor | `sleap-roots-trait-extractor:sha-689cffb` | **no change** | already current |

trait-extractor's pin is the only one that is **not** stale. The complete `689cffb..origin/main`
diff in `sleap-roots` is OpenSpec documentation only — no code, no `Dockerfile`, no dependency
changes — so the built image is unchanged.

Tag conventions differ per repo and must not be inferred: `bloomctl` tags are **7-char**
(`sha-623414f` resolves, `sha-623414f7` 404s), `sleap-roots-predict` uses the **full 40-char** sha.
Both were verified by querying GHCR directly rather than derived from `git rev-parse --short`,
which abbreviates differently than the CI runner does.

## Error handling

Producer exit codes, and what each yields. "DAG proceeds" means downstream tasks run; for every
non-zero code that happens via `continueOn`, and the final phase is then decided by the gate.

| Exit | Meaning | Retried? | DAG proceeds? | Workflow phase |
|---|---|---|---|---|
| `0` | all scans succeeded | no | yes (ordinary `dependencies`) | `Succeeded` |
| `3` | batch completed, some scans isolated-failed | yes, to limit | yes, via `continueOn` | `Succeeded` — gate allows `3` |
| `1` | crash / abort | yes, to limit | yes, via `continueOn` | **`Failed`** — gate rejects |
| `2` | CLI usage error | yes, to limit | yes, via `continueOn` | **`Failed`** — gate rejects |
| `143` | `SIGTERM` (preemption) | yes, to limit | yes, via `continueOn` | **`Failed`** — gate rejects |

A pod-level `Error` — a pod **deleted** out from under Argo (`markNodeError("pod deleted")`), which
is how scheduler-driven preemption typically surfaces on this cluster — is **not** covered by
`continueOn: {failed: true}`, so the DAG stops there and the gate is `Omitted`, inheriting `Failed`.
Intended.

**Correction to an earlier draft:** it listed image-pull failure and wait-container death as `Error`
cases. At v3.6.7 `assessNodeStatus` maps `PodPending` unconditionally to `NodePending`, and there is
no `ImagePullBackOff`/`FailedMount` handling anywhere in `operator.go`. A pod that never gets
*scheduled* therefore sits **`Pending` indefinitely** — never `Failed`, never `Error` — so neither
`retryStrategy` nor `continueOn` applies and nothing times it out (this repo sets no
`activeDeadlineSeconds`). Two consequences: `hostPath type: Directory` does **not** "fail loudly" as
`sleap-roots-pipeline.yaml` claims — it hangs; and because the gate is the only leaf, it is now the
single point at which that hang can strand a Workflow whose real work is already complete.

**Empty stage-in — CORRECTED.** An earlier draft of this document claimed: *"If every scan fails to
stage, bloomctl still exits 3, `continueOn` proceeds, and predict hits an empty input directory and
exits 1 — which the gate rejects, failing the workflow."* **That reasoning only holds for a fresh
input directory, and this pipeline never has one.**

The three stage directories are fixed, shared `hostPath`s, deliberately so (cluster-side dedup
depends on the sharing). Worse, they are shared *across environments*: production dispatches the
vendored copy of this Workflow, which is byte-identical on the `hostPath` block, so prod, staging
and every manual test read and write
`/hpi/hpi_dev/users/eberrigan/pipeline_orchestration_tests/a4_poc/{input,predictions,traits}`.

And `run_manifest.json` is cumulative: `write_run_manifest` computes
`merged = existing_scan_keys | this_run_scan_keys` and writes whenever the merge is non-empty. So:

- **Every scan fails to stage** → `this_run_scan_keys` is empty, but the merge is not, so a
  manifest is written containing *prior runs'* `scan_keys` stamped with *this* run's
  `pipeline_run_id`. predict scopes to those, finds them already on disk, skips them all, and exits
  **`0`** (`BatchResult.ok` is `all(s.status != "failed")`, and skipped is not failed). Traits `0`,
  write-back `0`, gate sees `(3,0,0)` → **Workflow `Succeeded` for a batch that staged nothing.**
- **A crash-class exit** (e.g. a malformed `--scan-ids` raising `ClickException`) happens *before*
  `write_run_manifest` runs at all, so the previous run's manifest is consumed verbatim.

Consequences to hold onto:

1. **The outcome is input-directory-state-dependent**, not fixed. On a fresh directory predict
   raises and the gate correctly fails the run; on the shared one it does not. Neither outcome
   should be asserted as fact until measured — see the open question below.
2. **`Workflow: Failed` no longer implies "nothing was written".** `continueOn` lets write-back run
   on crash paths, where `reconcile_unresolved_scans` closes out every scan dispatched under this
   `ARGO_WORKFLOW_NAME` as `failed`. Before this change the DAG stopped at the failing producer and
   nothing reached Bloom. The Known-Gaps section documents the converse (a green Workflow does not
   mean every scan succeeded); this is the more dangerous direction and is now documented too.
3. **Run-scoping via `run_manifest.json` is not sufficient** to keep a stage acting on its own run,
   because no consumer validates `pipeline_run_id` — and predict/traits were not even given their
   workflow identity. This change adds `ARGO_WORKFLOW_NAME` to both (inert today) as the
   prerequisite for that check; the check itself is producer-side work.

The stages disagree on empty input, which is why the gate reads producers' codes rather than
assuming uniformity: bloomctl exits `0` on zero requested scans, predict exits `1`, and traits
exits `1` with no manifest or `3` with one. The trait-extractor template's existing comment
claiming an empty `/in` exits 0 (a silent-green node) is stale — sleap-roots#266 closed that — and
is corrected as part of this change.

## Testing

`argo lint` on every changed manifest. Note it does **not** validate `retryStrategy.expression`
syntax (`validate.go:687` checks only `retryPolicy`) — not a concern here, since this design adds
no expression, but relevant if one is ever added.

Live verification on staging, experiment `A4-PIPELINE-E2E-TEST`:

1. **Poison scan** — re-run 2026-09-01's scenario 3: one scan whose `cyl_images` row points at
   object-storage content that was never uploaded, alongside two genuinely good scans. Expect: DAG
   reaches `write-back`; both good scans' results land on the NFS mount and in
   `cyl_trait_sources`; the poison scan marked `failed`; `done_count=2`, `failed_count=1`;
   workflow `Succeeded`.
2. **Crash injection — the more important test.** Confirm the gate still fails the workflow on a
   crash-class exit, since converting real crashes into green workflows is precisely this
   approach's failure mode. Concrete method: submit with a deliberately malformed `scan-ids`
   parameter, which `bloomctl` surfaces as a `ClickException` (exit `1`) or `UsageError` (exit
   `2`) rather than a partial-success `3`. Expect the gate to reject it and the workflow to end
   `Failed`.

Pass signals verified by artifact, not by workflow status alone — per the 2026-09-01 precedent of
checking file mtimes rather than trusting the phase.

## Deferred, with issues

Real defects found while designing this, each deliberately out of scope:

- **Run status will read `complete`, not `partial`**
  ([bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857)). The status
  poller's `rollup()` decides from Argo workflow phases only, and every Argo continue-past-failure
  mechanism yields `Succeeded`, so `partial` is unreachable from this repo at any batch size.
  `done_count`/`failed_count` are correct; only the status string is not. **Do not read a green
  workflow, or a `complete` run, as "no scans failed."**
- **A partial `predict`/`trait_extractor` will still fail the workflow**
  ([bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859)). Those
  scans *are* in the manifest, so write-back reports `missing_scan_keys`, marks them
  **retriable**, exits `1`, and retries to exhaustion. bloom already fixed this exact cascade for
  `status_update_matched` mismatches in `/review-pr` round 5; the missing-result case was never
  covered because the DAG could not previously reach write-back partially. Does not affect the
  poison-scan target (see "Write-back is untouched").
- **predict's forwarded manifest must narrow to `ok ∪ skipped`**
  ([sleap-roots-predict#44](https://github.com/talmolab/sleap-roots-predict/issues/44)). Once the
  DAG can reach traits after a partial predict, every predict-failed scan becomes a misattributed
  *trait-extraction* failure (`trait_extractor/extractor.py:271-280`). predict recorded this as an
  expiring decision keyed on #56 landing.
- **`MAX_SCAN_ATTEMPTS`** remains unimplemented. The retry budget stands in for it.

## Risks

- **This deploys to production.** prod and staging deliberately share the `runai-busch-lab`
  namespace, disambiguated only by `WORKFLOWS_K8S_ENV_LABEL`, and prod's workers are genuinely
  running. Every `argo template update` affects both environments' future dispatches.
- **No drift-check exists for these templates**
  ([#58](https://github.com/talmolab/sleap-roots-pipeline/issues/58)), so the cluster's registered
  copy can silently diverge from this repo — the mechanism behind #51/#52/#54/#55 each having to
  be caught by hand. The new `exit-gate` template adds a fifth unchecked object.
- **Cross-repo lockstep.** `sleap-roots-pipeline.yaml` is vendored by `salk-bloom` at
  `services/workflows/vendored/` with a pinned `SLEAP_ROOTS_PIPELINE_REF` (currently `9df1e52`,
  presently byte-identical). A DAG edit requires bumping both there. The drift check only fires
  when a *bloom* PR touches those paths, so it will not flag upstream drift on its own.
- **The gate adds a pod per workflow**, and on a crash path the downstream stages run wastefully
  before the gate concludes.
- **Upstream behaviour change risk.** If argo-workflows#13501 ever merges, `continueOn` semantics
  shift. This design depends only on the well-tested `continueOn`-on-the-failing-task shape
  (`TestContinueOnFailDag`), not on the buggy downstream-task variant.

## Resolved: which image the gate runs

The already-pinned `bloomctl` image, reused purely for its shell (`python:3.11-slim` base, so
`/bin/sh` exists), not to run `bloomctl`. Reusing an image this repo already pins avoids adding a
fifth un-drift-checked object on top of #58. The costs, both recorded in the template: `command`
must be overridden (above), and this pin now has to move in lockstep with the two other bloomctl
templates — a 2-file bump becomes a 3-file bump, in a repo whose recurring failure mode
(#51/#52/#54/#55) is precisely stale pins. The gate uses `imagePullPolicy: IfNotPresent` rather
than the `Always` the other bloomctl templates use: those pull every run to catch a silently
overwritten `sha-` tag, which matters for code that actually executes, whereas the gate uses only
`/bin/sh` and is the terminal single point of failure — a registry round-trip there is pure added
failure surface.
