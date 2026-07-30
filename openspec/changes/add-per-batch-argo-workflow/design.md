## Context

Full architecture, rationale, and deferred items live in
`docs/superpowers/specs/2026-07-28-a4-batch-stage-write-back-design.md` (approved 2026-07-28), which
itself grounds in `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`. This
change implements only the four-task DAG wiring in this declarative repo; everything else in the
design (semaphore, Bloom trigger route, producer Argo-readiness, notification) is a later,
separately-tracked change.

## Key decisions (scoped to this change)

- **`predictor`/`trait-extractor` are unchanged.** Both are already batch-capable
  (`run_batch`/`extract_batch`); the gap was purely the two `bloomctl`-based stages.
- **Image pin: `sha-61959bd`, not `0.1.0a2`/`sha-1bb03f6`.** The latter (referenced elsewhere in
  the roadmap) predates bloom #532 and lacks the batch commands. No versioned `bloomcli` release
  has been cut yet, so the commit-sha tag is the only correct reference for now — expect to bump
  it again once a real version tag exists.
- **Credential mount is a reference, not a live dependency.** `bloomctl`'s auth
  (`bloomcli/src/bloomctl/credentials.py`) reads a dotenv file at `~/.bloom/credentials.txt`
  directly — no interactive login needs to have run in-process, so a Secret volume mount works with
  zero `bloomctl` code changes. The actual credential (sleap-roots-pipeline#17) is being provisioned
  in a parallel session; this change wires the reference and does not block on it.
- **`HOME=/home/bloom` set explicitly** in both new containers — `bloomcli`'s Dockerfile creates its
  runtime user via `adduser --system` with no explicit home directory, so `Path.home()` (which
  `load_credentials()` uses) is ambiguous without it.
- **Batch input is a Workflow parameter (`scan-ids`), not a per-run isolated path.** Volumes stay
  the existing fixed `a4_poc` hostPath paths — safe because nothing can submit concurrent batches
  yet (no trigger route exists to do so). Revisit alongside the Bloom-side dispatch worker.
- **Capability rename: `per-scan-pipeline` → `per-batch-pipeline`.** Single-scan support isn't
  removed — it's a batch of size 1 — but keeping the old id would mislead readers into thinking a
  separate scan-only pathway still exists. The `predictor`/`trait-extractor` requirements carry
  forward unchanged in substance under the new capability id.

## Out of scope (later changes)

The Argo semaphore for concurrent-batch concurrency (design §9 of the 2026-07-06 doc), per-run path
isolation, moving off the interim image tag, the dev-personal hostPath convention, the Bloom-side
trigger route + `cyl_pipeline_runs`/`cyl_pipeline_run_scans` tables + dispatch worker
(bloom #11/#404), producer Argo-readiness reconciliation (predict #26 / sleap-roots #259),
notification (sleap-roots-pipeline#18), and local-WSL2 dev testing for this DAG shape
(sleap-roots-pipeline#21, updated with this change's specifics but not implemented here).

## Testing strategy — real cluster submit, not a local WSL2 dry-run

Checked live: this machine's Docker Desktop Kubernetes node (`desktop-control-plane`) reports no
`nvidia.com/gpu` in its `allocatable`/`capacity` at all — `predictor` cannot schedule locally
regardless of anything this change does. The `local-WSL2-*` variants are also already known-stale
relative to the cluster's GHCR contract (issue #21, filed before this change existed — updated with
these specifics, not touched here). So this change's acceptance gate is a real submit against the
RunAI cluster (`tasks.md` §5), not a local dry-run. Local dev testing for this DAG shape stays
tracked in #21.

## Risks

- **Credential provisioning status.** The `genericsecret-bloom-staging-pipeline-credentials`
  Secret has since been created via the RunAI console (Credentials → Generic secret, Project
  scope `talmo-lab`), populated from a `bloomctl login --profile pipeline-staging` against
  `staging.bloom.salk.edu` — sleap-roots-pipeline#17 is effectively resolved for the staging
  environment. **Confirmed live**: the multi-line value survived intact — `images-downloader`
  authenticated and staged real frames on the first real cluster submit.
- **Skip-if-done can serve stale copied-through data after an upstream data fix, not just after
  a code fix.** Found during this change's own cluster testing (bloom #555/#556): when
  `images-downloader` re-staged scans with a corrected sidecar, `predictor` still skipped
  re-running (its own prediction outputs were already valid), so it never re-copied the corrected
  sidecar forward into its output directory — `trait-extractor` kept reading the stale copy until
  `predictor`'s outputs were manually cleared to force a real re-run. This is a variant of the
  already-known "existence-only skip" resumability gap (design doc §8 of the 2026-07-06 doc) that
  specifically affects sidecar *content* changes, not just prediction validity — worth folding into
  whatever eventually hardens skip-if-done (checksum-verified skip, not just existence), rather than
  fixed here.
- **`--scan-ids ""` (the parameter's empty default) behavior.** The source implies a clean exit 0
  (`parse_scan_ids_flag("")` → `[]`, "nothing to stage") rather than a CLI parse error, but this is
  confirmed on the real cluster submit (`tasks.md` 5.4), not assumed here.
- **Write-back can also go silently green on an empty batch.** Like `trait-extractor`'s known gap
  (sleap-roots#259), `batch-ingest-result` also exits 0 on an empty envelopes directory — so all
  four DAG nodes can succeed with zero real work done. This is the same class of issue as the
  already-deferred "producer Argo-readiness reconciliation" item above; not solved by this change,
  called out here so it isn't mistaken for new behavior introduced later.
