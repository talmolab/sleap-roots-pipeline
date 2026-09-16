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
  actually resolved and pulled; the tag becomes human-facing decoration. This delivers the
  "tighten to `@sha256:<digest>`" intent the templates have carried in comments since the first
  GHCR publish.
- **Add the two digest env vars**, each valued with the same digest its own `image:` line pins.
- **Assert the two agree** in `scripts/check_manifests.py`, deriving the expected value by parsing
  the `image:` line rather than hardcoding a literal digest. See `design.md` for why the `image:`
  line has to carry the digest for this assertion to be meaningful at all.
- **Correct a false claim** in the A4 design doc, which lists a pinned container digest under
  *required for correctness* of the idempotency key. No container digest is an input to
  `compute_idempotency_key`. The claim's conclusion is right for a different reason (pinning
  stabilises the **code SHAs baked into the image**, which *are* key inputs), so this is a
  wrong-mechanism correction rather than a deletion.

**Explicitly out of scope: `ARGO_WORKFLOW_UID` / `ARGO_NODE_ID`.** An earlier comment on #70
proposed batching them here so one `argo template update` would cover the whole template side.
That was retracted on the issue and is not done here: both have **zero occurrences** in either
producer, so setting them from a template would have no effect. `provenance.argo_workflow_uid` and
`argo_node_id` are equally empty, but they need a producer-side change first and belong with
[talmolab/sleap-roots#268](https://github.com/talmolab/sleap-roots/issues/268), alongside
`Provenance.pipeline_run_id`.

**This change triggers no recompute.** `compute_idempotency_key(scan_key, images_checksum, models,
param_hash, predict_code_sha, traits_code_sha, predict_output_params)` takes no container digest,
so populating these env vars invalidates no accumulated idempotency key and forces no
re-prediction. Sequencing matters: sleap-roots#268's fix is a *code* change that bumps
`traits_code_sha`, which **is** a key input, so it invalidates every key and forces a full
recompute. Landing #70 first means one recompute cycle, not two.

## Impact

- Affected specs: `per-batch-pipeline` (1 ADDED requirement, 2 MODIFIED)
- Affected manifests: `sleap-roots-predictor-template.yaml`,
  `sleap-roots-trait-extractor-template.yaml`
- Affected tooling: `scripts/check_manifests.py` (58 assertions today)
- Affected docs: `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`
- Deployment: both templates need `argo template update` in `runai-busch-lab` after merge. That
  namespace is shared by Bloom staging **and** production, so the apply is production-visible.
