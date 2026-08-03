# Redesigning "per-run path isolation" — manifest-scoped processing, not per-run paths

## Context

The A4 tier row and the 2026-07-30 status log entry both flagged "per-run path isolation" as a
known, twice-confirmed-real gap: `sleap-roots-pipeline.yaml`'s `images-input-dir`/
`predictions-output-dir`/`traits-output-dir` are fixed hostPaths (`a4_poc/{input,predictions,traits}`)
shared across every run. Two real contamination incidents happened during PR #33's testing:
1. A leftover scan directory from one run got reprocessed by predictor's directory-wide scan on a
   later run, even though it wasn't in that run's requested scan-ids.
2. A stale prediction output from a previous run blocked a corrected sidecar from propagating on a
   subsequent run (predictor's skip-if-done only checks prediction validity, not whether the input
   sidecar changed).

The assumed fix, per the original A4 design doc and this repo's own accepted-risk language, was a
future per-`pipeline_run_id`/`batch_index` path scheme. This doc replaces that assumption.

## The constraint that changes everything

The cluster-side "dedup"/GPU-avoidance mechanism this whole program relies on — including Bloom's
own trigger-route architecture — is `sleap-roots-predict`'s `batch.py` skip-if-done check: a plain
`Path.exists()`, not an idempotency-key comparison. It only works *because* every run currently
shares the same fixed path: if a scan was already processed in Run A's shared directory, Run B's
predict step finds it and skips it.

This isn't incidental. Bloom PR #570's `pipeline.py` module docstring states explicitly that its
dedup preview is informational-only "because the real GPU-avoidance decision is made cluster-side
by the predict loop's own skip-if-done check." The roadmap's own A4 validation target (design §14,
"batch oracle") requires: re-run an already-done batch/experiment → **0 GPU pods scheduled, all
scans reused**. Naive per-run path isolation (keying every run's directories on
`{{workflow.name}}` or a future `pipeline_run_id`) would make every run start from an empty
directory — defeating that reuse guarantee entirely and breaking the batch oracle test.

## The reframe

"Per-run path isolation" was conflating two different needs:

1. **Contamination prevention** — a run should only ever touch the exact scan_ids it was given,
   not whatever else happens to be sitting in the shared directory. This is what actually caused
   incident (1) above — and it's fixed by **manifest-scoped processing**, not by separate
   directory trees.
2. **Reuse preservation** — the durable output store needs to stay **shared and scan_id-keyed**
   (not run-keyed) so legitimate cross-run reuse keeps working, exactly as the batch oracle
   requires.

Incident (2) (stale sidecar served by an existence-only check) is a separate, already-tracked
problem — skip-if-done should compare the real `idempotency_key` (already defined in
`sleap-roots-contracts`: scan_key + images_checksum + model versions/weights + param_hash +
predict_code_sha + traits_code_sha), not just check whether a file exists. That upgrade closes
both incident (2) and the general class of "existence check silently serves stale data" bugs.

## Where the actual work lives — and why almost none of it is in this repo

Tracing the dependency chain surfaced that this repo has very little left to build:

1. **`sleap-roots-contracts`** defines the run-manifest shape (a `run_id`/`workflow_name` + the
   list of `scan_id`s a given run is scoped to) — following this program's own established
   pattern for every other cross-repo shape (`ResultEnvelope`, `Provenance`, `ModelCard`,
   `ResolvedParams`, `PredictionManifest`), since it must be read identically by
   `sleap-roots-predict` and `sleap-roots`/traits, and written by `bloomctl`.
2. **`bloomctl`** (in `salk-bloom`) writes the manifest during `images-downloader` — it already
   writes per-scan sidecars into the same shared directory, so this is a natural addition there,
   not here.
3. **`sleap-roots-predict`** reads the manifest and scopes `run_batch` to exactly those scan_ids
   instead of directory-wide-scanning everything present; separately upgrades skip-if-done to a
   real idempotency-key comparison.
4. **`sleap-roots`/traits** reads the manifest too, and adds a skip-if-done check it currently
   lacks entirely (confirmed earlier this session: traits always recomputes, no exceptions).

**Critically: if the manifest is a file sitting in the already-shared, already-mounted input
directory (not a CLI argument), this repo's Argo templates don't need to change at all.**
Confirmed directly: both `sleap-roots-predict`'s and `sleap-roots`/traits' container entrypoints
use `argparse` with exactly two required positional args (`input_dir`, `output_dir`) — adding a
third argument today would hard-fail with "unrecognized arguments," not silently no-op. A file the
readers simply don't look for yet, versus don't yet exist to parse, is the forward-compatible
path; a new CLI arg is not.

## What this repo's PR actually is

Not a feature — a correction + a guardrail, to stop this program from re-discovering the same
near-mistake later. **All five items below are done:**

1. ✅ **Corrected the stale comment** in `sleap-roots-pipeline.yaml` (previously line 35, now an
   expanded ~10-line block starting at line 35) that said "a real per-scan trigger parameterizes
   them (#10)" — this implied the fix was per-run-parameterized paths, which is now known to be
   wrong.
2. ✅ **Added an explicit architectural guardrail** stating the shared-path requirement outright,
   so a future contributor doesn't "fix" the contamination gap by isolating paths again, unaware
   it would silently break cluster-side dedup.
3. ✅ **Filed a cross-repo tracking issue** — **[#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37)**
   (matching the existing EPIC-tracking convention — A3 EPIC #9, A4 EPIC #10 both live here) — for
   the manifest-scoped-processing + idempotency-key-verified-skip initiative, to be decomposed
   into per-repo sub-issues starting with `sleap-roots-contracts`.
4. ✅ **Updated the roadmap** — new "Cross-repo correctness" subsection + a 2026-08-03 status-log
   entry, both linking #37 and this doc.
5. ✅ **Drafted the handoff to `sleap-roots-contracts`** as the first repo to actually build
   something — delivered as a copy-paste prompt; timing to actually start that session is
   Elizabeth's call (recommended after her in-progress `sleap-roots-predict` parity-gate work
   wraps up).

## Out of scope for this repo's PR

- Actually defining the manifest's Pydantic shape (that's `sleap-roots-contracts`'s job).
- Any `bloomctl`/`sleap-roots-predict`/`sleap-roots` code changes.
- The idempotency-key-verified skip-if-done upgrade itself (tracked, lives in predict/traits).

## Risks / open questions

- This redesign assumes the manifest will be a discoverable file, not a CLI arg — if
  `sleap-roots-contracts`'s design ends up preferring a CLI-arg interface instead (e.g. for
  explicitness/validation-at-parse-time reasons), predict's and traits' `argparse` signatures
  *would* need to change, and this repo's templates would need a coordinated follow-up PR passing
  `{{workflow.parameters.scan-ids}}` through. That decision belongs to whoever designs the
  contracts shape, not this doc — flag it explicitly in the handoff so it's a deliberate choice.
- No timeline pressure is assumed here; this is correctness/robustness work for an already-shipped
  pipeline, not blocking any in-flight A4 milestone.
