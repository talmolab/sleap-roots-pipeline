# Wire the producers' partial-success exit code into the DAG

## Why

All three producer stages already emit a distinct partial-success exit code (`3`) — meaning "the
batch ran to completion; some scans isolated-failed". None of the three `WorkflowTemplate`s react
to it. `retryPolicy: Always` retries on any non-zero exit, so a single genuinely-failing scan
exhausts its stage's retry budget and then kills the whole DAG, discarding the scans that
succeeded.

Demonstrated live on 2026-09-01: workflow `sleap-roots-pipeline-jqsf9` ended `Failed` at **0/3**
progress. Two scans were confirmed fully staged on the NFS mount with real data; neither ever
reached the predictor. This is [#56](https://github.com/talmolab/sleap-roots-pipeline/issues/56),
and it is the last remaining blocker for the A4 batch-oracle poison-scan target — both driver-side
halves have now shipped (bloom#830 for `bloomctl`, predict#36 and sleap-roots#266 earlier).

## What Changes

- Add `continueOn: {failed: true}` to the `images-downloader`, `predictor` and `trait-extractor`
  DAG tasks, so a partial stage no longer terminates the DAG.
- Add a fifth DAG task, `exit-gate`, as the DAG's only leaf. It reads each producer's real exit
  code and fails unless every one is in `{0, 3}`. This is **not** belt-and-braces: `continueOn`
  keys only on node *phase*, so without the gate an exhausted-retry crash would also be swallowed
  and report the workflow `Succeeded` — strictly worse than today's behaviour.
- Add `sleap-roots-exit-gate-template.yaml` and register it in `runai_run_pipeline.sh`.
- Bump three stale image pins, without which the wiring is inert: both `bloomctl` templates to the
  build carrying bloom#830's exit code *and* bloom#774's per-scan status marking, and the
  predictor to the build carrying predict#42's manifest forward-copy.
- Correct a stale comment in the trait-extractor template claiming an empty input directory exits
  `0` (sleap-roots#266 closed that).

**No `retryStrategy.expression` is added, and existing retry limits are unchanged.** Argo's
whole-step retry is currently the only per-scan retry that exists anywhere in the producers
(`MAX_SCAN_ATTEMPTS` is unimplemented in every repo), so suppressing it would permanently isolate
scans that a second attempt would have handled. See `design.md`.

## Impact

- Affected specs: `per-batch-pipeline`
- Affected manifests: `sleap-roots-pipeline.yaml`, the three producer templates, the new
  `sleap-roots-exit-gate-template.yaml`, `runai_run_pipeline.sh`
- **Cross-repo lockstep required.** `sleap-roots-pipeline.yaml` is vendored by `salk-bloom` at
  `services/workflows/vendored/` against a pinned `SLEAP_ROOTS_PIPELINE_REF`. A DAG edit requires
  a companion PR there bumping both. The drift check only fires when a *bloom* PR touches those
  paths, so it will not flag this on its own.
- **This reaches production.** prod and staging deliberately share the `runai-busch-lab`
  namespace, and prod's workers are running. Every `argo template update` affects both.
- **Known limitation, deliberately not fixed here:** a run will read `complete` with
  `failed_count > 0`, not `partial`. The status poller's rollup decides from Argo workflow phases
  alone, and every Argo continue-past-failure mechanism yields `Succeeded`, so `partial` is
  unreachable from this repo at any batch size. Tracked as
  [bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857). Do not read
  a green workflow, or a `complete` run, as "no scans failed".
- Other deferred follow-ups, both filed:
  [bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859) (a partial
  `predict`/`trait_extractor` still fails the workflow at write-back) and
  [sleap-roots-predict#44](https://github.com/talmolab/sleap-roots-predict/issues/44) (forwarded
  manifest must narrow to `ok ∪ skipped`).
- Out of scope: the `local-WSL2-*` variants, which are pre-A4 and contain neither an
  images-downloader nor a write-back stage
  ([#21](https://github.com/talmolab/sleap-roots-pipeline/issues/21)).
