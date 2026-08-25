# Design: single-source-of-truth for the dispatched Argo Workflow body

**Date:** 2026-08-25
**Status:** proposed
**Trigger:** a live production bug found during a baseline E2E validation of the A4 pipeline
(2026-08-24/25) — `salk-bloom`'s dispatch worker (`services/workflows/k8s_client.py::
build_workflow_body`) hand-reconstructs the Argo `Workflow` CRD body in Python instead of
reusing this repo's canonical `sleap-roots-pipeline.yaml`, and silently omits `spec.volumes`
entirely. Every real batch dispatch fails: `images-downloader` errors with `volume
'images-input-dir' not found in workflow spec`, cascading to skip every downstream stage.

## Why this happened

`sleap-roots-pipeline.yaml` (this repo) is the only place this Workflow's shape has ever been
correctly and completely defined, and the only path that has ever actually run it successfully
end-to-end (PR #33, 2026-07-30 — via `argo submit sleap-roots-pipeline.yaml --parameter
scan-ids=...`). `salk-bloom`'s dispatch worker (bloom #677, Phase 2, merged 2026-08-18) needed to
submit the same shape programmatically — parameterized per-batch, with tracking labels — so it
was rebuilt from scratch in Python rather than loaded from the file. That reimplementation
correctly copied the DAG's task/`templateRef` structure but dropped `spec.volumes` entirely, and
nothing caught it: Phase 2's own validation deliberately used a minimal `busybox` test workflow
with "no `hostPath`/GPU/real-data dependencies" (see `salk-bloom/openspec/changes/archive/
2026-08-17-add-cyl-pipeline-dispatch/design.md`), so the real 4-stage DAG was never exercised
against a real submission until this session's E2E validation — which itself was blocked by an
unrelated CA-cert bug until just before this bug surfaced.

Two independent representations of the same Workflow shape, one hand-copied from the other with
no mechanism to detect drift, is the root problem — not just the missing volumes specifically.
This design fixes the class of bug, not just the instance.

## Decisions made (conversationally, before this doc)

1. **The canonical source is the whole `sleap-roots-pipeline.yaml` Workflow** — not a hand-picked
   subset of fields. A slice needs someone to remember to widen it every time the manual file
   grows (a new stage, a new volume) — exactly the class of omission this fix addresses. The
   whole-file approach captures future changes automatically and keeps the manually-tested path
   and the automated-dispatch path as close to identical as possible.
2. **The dispatch worker layers a small, explicit set of overrides on top of the loaded file** —
   it cannot submit it byte-for-byte:
   - `spec.arguments.parameters[0].value` — the manual file's `""` placeholder is always replaced
     with the batch's real, comma-joined `scan-ids`.
   - `metadata.labels` — `submitted-by`, `pipeline-run-id`, `batch-index`, `environment` don't
     exist in the manual file at all; added by dispatch.
   - `spec.ttlStrategy` — **stays dispatch-only, deliberately not folded into the shared file.**
     The `bloom-pipeline` ServiceAccount that submits dispatched workflows has no `delete` RBAC on
     `workflows.argoproj.io` — without a TTL, dispatched Workflow objects would accumulate in the
     shared cluster forever with no mechanism to ever remove them (not just "until someone
     remembers to clean up" — a human running the manual file by hand has `kubectl delete` as a
     real fallback; the dispatch worker fundamentally does not).
3. **Distribution mechanism: vendor + CI drift-check, not a published package, not a live fetch.**
   - A published-package approach (matching `sleap-roots-contracts`'s PyPI pattern) was
     considered and rejected as disproportionate — that pattern exists for a growing, multi-file
     schema library consumed by 4+ services; here there is exactly one file to share.
   - A live fetch at build- or run-time was considered and rejected — no precedent anywhere in
     this program (confirmed by searching `salk-bloom` for any `git+https`/`raw.githubusercontent`/
     cross-repo build-time fetch pattern: zero hits), and it would make every real pipeline
     dispatch depend on GitHub being reachable at that exact moment.
   - Vendoring a copy with an automated drift-check gets the same real goal — one canonical
     source, loud automatic failure the moment it drifts — without standing up packaging/
     publishing infrastructure sized for a single file.

## Scope

This fix covers `sleap-roots-pipeline.yaml` only — the top-level `Workflow` (volumes, entrypoint,
serviceAccountName, DAG task/`templateRef` structure). It does **not** cover the four
`*-template.yaml` `WorkflowTemplate` files (`images-downloader`, `predictor`, `trait-extractor`,
`write-back`) — `build_workflow_body`'s DAG only ever references those by name
(`templateRef: {name, template}`), never their bodies, so there's nothing to vendor there. Those
four files have their own, differently-shaped risk (is the cluster's *registered* `WorkflowTemplate`
object in sync with the repo's copy of it?) — a real, similarly-motivated question, but a
different mechanism (this is about a template being *applied* to the cluster, not consumed
programmatically) and explicitly out of scope here.

## Mechanism

**In `sleap-roots-pipeline` (this repo):**
- Add a guardrail comment at the top of `sleap-roots-pipeline.yaml` stating plainly: this file is
  vendored by `salk-bloom` (path + pinned-ref file named explicitly) for programmatic dispatch;
  changing this file's `volumes`, `entrypoint`, `serviceAccountName`, or DAG structure requires
  updating the vendored copy and bumping the pinned commit SHA in that repo, or CI there will fail.
  This is the cheap, high-value half of preventing this class of bug from recurring — a future
  editor of this file sees the warning before making a change that would otherwise silently
  drift.

**In `salk-bloom` (companion change, tracked separately in that repo):**
- Vendor a copy at `services/workflows/vendored/sleap-roots-pipeline.yaml`, plus a sibling
  `services/workflows/vendored/SLEAP_ROOTS_PIPELINE_REF` file containing the exact
  `sleap-roots-pipeline` commit SHA the vendored copy was pulled from.
- A new CI check (added to `pr-checks.yml`): on every PR, fetch
  `https://raw.githubusercontent.com/talmolab/sleap-roots-pipeline/<pinned-SHA>/sleap-roots-pipeline.yaml`
  and diff it byte-for-byte against the vendored copy. Fail loudly on any mismatch — this is the
  one network fetch in the whole design, and it happens in CI (which already talks to GitHub
  constantly and is already trusted), never in the running service or its container build.
- `k8s_client.py::build_workflow_body` is rewritten to load the vendored YAML (via
  `importlib.resources` or a plain file read relative to the module — whichever matches how this
  service already packages non-Python data, to be confirmed during implementation), deep-copy it,
  and apply exactly the three overrides listed above. Add a defensive assertion that
  `spec.arguments.parameters[0].name == "scan-ids"` before overwriting its value — a cheap check
  against the vendored file's structure silently changing shape in a way the CI diff wouldn't
  necessarily catch if someone updates the pin without reading the diff carefully.
- Bumping the pin (updating the vendored copy + `SLEAP_ROOTS_PIPELINE_REF`) becomes the explicit,
  visible, deliberate re-sync event — the same "tracked event" property this program already uses
  for `sleap-roots-contracts` version re-pins.

## Error handling

- If the vendored file is missing or fails to parse at container startup, fail the same way
  missing `WORKFLOWS_K8S_CA_CERT`/`_TOKEN`/`_API_URL` already fail today — a `K8sConfigError`
  raised before any network call, not a runtime surprise on the first real dispatch.
- If the defensive `parameters[0].name == "scan-ids"` assertion fails, same treatment — configuration
  error, not a silent wrong submission.
- The CI drift-check failing is not a runtime error at all — it blocks the PR that introduced the
  drift from merging, which is the entire point.

## Testing

- `salk-bloom`'s `tests/test_k8s_client.py` needs a new test asserting the constructed body's
  `spec.volumes` matches the vendored file's `spec.volumes` exactly — a direct regression test for
  the bug this fixes. Existing tests asserting the DAG/task shape stay, updated only where the
  loaded-and-patched construction changes their expected literal body.
- Manual verification: re-run the same real-cluster trigger this session already used
  (`POST /workflows/pipeline` against the `A4-PIPELINE-E2E-TEST` staging experiment,
  `experiment_id 12880747`) after the fix ships, and confirm the resulting Argo Workflow reaches
  a real terminal state (`Succeeded`/`Failed`/`partial`) instead of `Error`-ing on the missing
  volume.

## Open questions

None outstanding — all real decision points were resolved conversationally before writing this
doc (canonical scope, override list, distribution mechanism, in/out-of-scope boundary for the
four `WorkflowTemplate` files).
