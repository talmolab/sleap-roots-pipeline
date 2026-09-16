# Record the container image that produced each result

## Why

Both producers already read a container-digest environment variable and fall back to `""` when it
is unset:

| env var | read by | at |
|---|---|---|
| `SRP_PREDICT_CONTAINER_DIGEST` | `sleap-roots-predict` | `sleap_roots_predict/output_contract.py:226` |
| `SRT_TRAITS_CONTAINER_DIGEST` | `sleap-roots` (traits) | `trait_extractor/envelope.py:73` |

No template sets either one. The mismatch is one-directional — the consuming code shipped, the
producing side never did — so every result envelope records *which code* produced it
(`predict_code_sha`, `traits_code_sha`, both baked into the images) but not *which image*.

Confirmed live on 2026-09-16: `provenance.predict_container_digest` and
`provenance.traits_container_digest` are empty in **all 12** `*.result.json` files under
`/hpi/hpi_dev/users/eberrigan/pipeline_orchestration_tests/a4_poc/traits/`. This is
[#70](https://github.com/talmolab/sleap-roots-pipeline/issues/70).

Because both fields default to `""` rather than erroring, nothing surfaced the gap for months; it
took reading the live NFS output to notice.

## What Changes

- **Pin both producer images by digest**, retaining the existing `sha-<sha>` tag for readability:
  `ghcr.io/…:sha-<sha>@sha256:<digest>`. When a reference carries both, the digest is what is
  actually resolved and pulled; the tag becomes human-facing decoration.

  This extends to the producers the rule `sleap-roots-images-downloader-template.yaml:4-7` already
  states for the `bloomctl` image, **for the reason recorded there**: a `sha-<gitsha>` tag is
  immutable in *name* only — re-running the build workflow against the same commit would silently
  overwrite it in GHCR unless immutable tags are enabled on that package (noted there as unverified
  from this repo). That is the residual risk a digest closes and a commit-sha tag does not. The two
  producer templates themselves have never carried that note; this change is what makes it real for
  them.
- **Add the two digest env vars**, each valued with the same digest its own `image:` line pins.
- **Assert the two agree** in `scripts/check_manifests.py`, deriving the expected value by parsing
  the `image:` line rather than hardcoding a literal digest. See `design.md` for why the `image:`
  line has to carry the digest for this assertion to be meaningful, and for the precise limits of
  what that assertion can and cannot prove.
- **Correct a falsified claim** about the idempotency key, at all five sites where it appears — not
  only the two in the file where it was first noticed. No container digest is an input to
  `compute_idempotency_key`. The claim's conclusion survives, but by a different mechanism (see
  `design.md`), so this is a wrong-mechanism correction rather than a deletion.

**Not marked BREAKING, deliberately.** The two MODIFIED requirements tighten "pinned by digest *or*
`sha-<sha>`" to "digest required", which makes both currently-shipping manifests non-conformant
until this change's own edits land, and introduces a new runtime failure mode
(`ImagePullBackOff` on a malformed reference) in a namespace shared with Bloom production. The
failure is immediate, total, cannot half-apply, cannot corrupt data, and reverts in one line, and
the task plan proves the reference pulls locally *before* the cluster is touched. Recorded here so
the judgement is visible rather than merely absent.

**Explicitly out of scope: `ARGO_WORKFLOW_UID` / `ARGO_NODE_ID`.** An earlier comment on #70
proposed batching them here so one `argo template update` would cover the whole template side.
That was retracted on the issue and is not done here: both have **zero occurrences** in either
producer, so setting them from a template would have no effect. They need a producer-side change
first and belong with [talmolab/sleap-roots#268](https://github.com/talmolab/sleap-roots/issues/268).

Six `Provenance` fields are empty in the live envelopes, not four. This change fixes two
(`predict_container_digest`, `traits_container_digest`). The remaining four are `pipeline_run_id`,
`argo_workflow_uid` and `argo_node_id` (all sleap-roots#268) and `worker_request_id`, which is
dispatch-side and belongs to Bloom. `produced_at` is `None` by design and is not counted.

**This change triggers no recompute** — and, as a direct consequence, **will not retroactively
populate existing envelopes**. `compute_idempotency_key(scan_key, images_checksum, models,
param_hash, predict_code_sha, traits_code_sha, predict_output_params)` takes no container digest,
so the key is unchanged, so both stages skip already-completed scans and leave their existing
manifests and envelopes untouched. Re-running over `a4_poc` would therefore leave all 12 envelopes
empty and still be behaving correctly; only newly-computed scans record a digest. This is the
operationally surprising consequence of the change and is captured as its own spec scenario.

Sequencing matters: sleap-roots#268's fix is a *code* change that bumps `traits_code_sha`, which
**is** a key input, so it invalidates every key and forces a full recompute. Landing #70 first means
one recompute cycle, not two.

## Impact

- Affected specs: `per-batch-pipeline` (1 ADDED requirement, 2 MODIFIED)
- Affected manifests: `sleap-roots-predictor-template.yaml`,
  `sleap-roots-trait-extractor-template.yaml`. The `local-WSL2-*` producer variants are
  deliberately out of scope (see the ADDED requirement's scope clause).
- Affected tooling: `scripts/check_manifests.py` (58 assertions today)
- Affected docs: `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`,
  `docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md`,
  `docs/bloom-integration/roadmap.md` (the claim sweep, and the post-run status-log entry)
- **No cross-repo vendoring step is needed.** `salk-bloom` vendors only `sleap-roots-pipeline.yaml`
  (per that file's own header), not the templates this change edits — so unlike #56's §8, there is
  no lockstep companion PR.
- Deployment: both templates need `argo template update` in `runai-busch-lab` after merge. That
  namespace is shared by Bloom staging **and** production, so the apply is production-visible.
