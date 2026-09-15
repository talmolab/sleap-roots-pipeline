# Wire the producers' partial-success exit code into the DAG

## Why

All three producer stages implement a distinct partial-success exit code (`3`) — "the batch ran to
completion; some scans isolated-failed" — in builds newer than the image pins this repo currently
carries. None of the three `WorkflowTemplate`s react to it. `retryPolicy: Always` retries on any
non-zero exit, so a single genuinely-failing scan exhausts its stage's retry budget and then kills
the whole DAG, discarding the scans that succeeded.

Demonstrated live on 2026-09-01: workflow `sleap-roots-pipeline-jqsf9` ended `Failed` at **0/3**
progress. Two scans were confirmed fully staged on the NFS mount with real data; neither ever
reached the predictor. This is [#56](https://github.com/talmolab/sleap-roots-pipeline/issues/56),
the last remaining blocker for the A4 batch-oracle poison-scan target.

## What Changes

- Add `continueOn: {failed: true}` to the `images-downloader`, `predictor` and `trait-extractor`
  DAG tasks, so a partial stage no longer terminates the DAG. `failed` only, never `error` — a
  stage that never ran should stop the DAG rather than let it proceed on data that was never
  produced.
- Add a fifth DAG task, `exit-gate`, as the DAG's only leaf, backed by a new
  `sleap-roots-exit-gate-template.yaml`. It receives each producer's real exit code as three
  separately-named parameters and fails unless every one is in `{0, 3}`.
  This is **not** belt-and-braces. `continueOn` keys only on node *phase*, so without the gate an
  exhausted-retry crash would be indistinguishable from a partial success and would report the
  Workflow `Succeeded` — strictly worse than today, where a crash at least fails the run. See
  `design.md`.
- Register the new template in `runai_run_pipeline.sh`.
- Bump three stale image pins, without which the wiring is inert: both `bloomctl` templates to the
  build carrying bloom#830's exit code **and** bloom#774's per-scan status marking (#774 changed
  the write-back stage's own code, so that template needs it too), and the predictor to the build
  carrying predict#42's manifest forward-copy. The trait-extractor's pin is already current.
- Correct documentation this change falsifies: README's stage list, folder structure, template
  registration commands and — most substantively — its "DAG Behavior and Step Failures" section,
  which states that an exhausted retry fails the entire workflow; `openspec/project.md`'s four
  "four-stage" references; and the stale "empty input exits 0" claim in the trait-extractor
  template and two live design docs (closed by sleap-roots#266 / predict#36).

**No `retryStrategy.expression` is added, and existing retry limits are unchanged.** Argo's
whole-step retry is currently the only per-scan retry that exists anywhere in the producers
(`MAX_SCAN_ATTEMPTS` is unimplemented in every repo), so suppressing it would permanently isolate
scans that a second attempt would have handled. See `design.md` Decision 2.

**BREAKING** (consumer-side, outside this repo): the DAG gains a fifth task, so `salk-bloom`'s
`services/workflows/tests/test_k8s_client.py::test_build_workflow_body_dag_references_all_four_templates_in_order`
fails, and `k8s_client.py::build_workflow_body`'s docstring ("the four already-registered
WorkflowTemplates") goes stale. Both must be updated in the companion vendoring PR — note the
existing `check_vendored_workflow_drift.py` compares bytes and will pass green while that test is
red. `build_workflow_body` itself needs no change; it passes the DAG through unmodified.

**BREAKING** (knowingly deferred): `local_run_pipeline_first_time.sh` submits the *cluster*
manifest and carries its own four-template list, so it will hard-fail on the unregistered
`templateRef`. The local dry-run path is out of scope for this change and remains tracked by
[#21](https://github.com/talmolab/sleap-roots-pipeline/issues/21).

## Impact

- **Affected specs:** `per-batch-pipeline`
- **Affected manifests/scripts:** `sleap-roots-pipeline.yaml`; `sleap-roots-exit-gate-template.yaml`
  (new); the images-downloader, predictor, trait-extractor and write-back templates;
  `runai_run_pipeline.sh`
- **Affected docs:** `README.md`, `openspec/project.md`, `docs/bloom-integration/roadmap.md`,
  `docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`,
  `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`
- **Affected cross-repo files:** `salk-bloom`'s `services/workflows/vendored/sleap-roots-pipeline.yaml`,
  `services/workflows/vendored/SLEAP_ROOTS_PIPELINE_REF`, `services/workflows/k8s_client.py`
  (docstring), `services/workflows/tests/test_k8s_client.py`
- **Hard deployment ordering.** The `exit-gate` WorkflowTemplate must be registered in
  `runai-busch-lab` **before** any vendored five-task DAG is deployed. If the vendored copy ships
  first, every batch dispatch fails at submit time on an unresolvable `templateRef` — and since
  prod and staging share that namespace, that is a simultaneous prod and staging dispatch outage,
  not silent drift. Merging the bloom PR to `staging` *is* the deploy. Rollback rule: reverting
  this repo is safe; deleting the gate template is not, while any deployed vendored copy
  references it.
- **This reaches production.** prod and staging deliberately share `runai-busch-lab`, and prod's
  workers are running. Every `argo template update` affects both environments' future dispatches,
  and there is no drift-check for these templates
  ([#58](https://github.com/talmolab/sleap-roots-pipeline/issues/58)) — the gate adds a fifth
  unchecked object.
- **Known limitation, deliberately not fixed here:** a run will read `complete` with
  `failed_count > 0`, not `partial`. The status poller's rollup decides from Argo workflow phases
  alone, and every Argo continue-past-failure mechanism yields `Succeeded`, so `partial` is
  unreachable from this repo at any batch size. Tracked as
  [bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857). **Do not read
  a green Workflow, or a `complete` run, as "no scans failed."** The gate mounts no volumes, so it
  attests that every producer completed acceptably — not that any scan was processed or any output
  landed. The outcome for a zero-scan or zero-staged batch is **input-directory-state-dependent and
  not yet characterised** (see `design.md`); it must be measured, not assumed.
- **`Workflow: Failed` no longer implies "nothing was written".** `continueOn` lets write-back run
  on crash paths, where `reconcile_unresolved_scans` closes out every scan dispatched under this
  `ARGO_WORKFLOW_NAME` as `failed`. Previously the DAG stopped at the failing producer and nothing
  reached Bloom. Compounding this, the stage directories are shared across runs **and
  environments** — prod dispatches the vendored copy with the same `hostPath`s — and
  `run_manifest.json` accumulates `scan_keys`, so a crash path can be scoped by another run's
  manifest. This change adds `ARGO_WORKFLOW_NAME` to the predictor and trait-extractor (inert
  today) as the prerequisite for producer-side run-scope validation.
- **Other deferred follow-ups, both filed:**
  [bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859) (a partial
  `predict`/`trait_extractor` still fails the Workflow at write-back, because a manifest
  `scan_key` with no result is marked *retriable*) and
  [sleap-roots-predict#44](https://github.com/talmolab/sleap-roots-predict/issues/44) (forwarded
  manifest must narrow to `ok ∪ skipped`, or a partial predict misattributes failures to traits).
