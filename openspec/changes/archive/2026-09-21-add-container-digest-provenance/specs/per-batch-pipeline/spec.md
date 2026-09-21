## ADDED Requirements

### Requirement: Each provenance-emitting stage records the container image that produced its results

The two provenance-emitting stages — `predictor` and `trait-extractor` — SHALL each inject the
container-digest environment variable its own image reads, so the resulting record identifies not
only which code ran (`predict_code_sha` / `traits_code_sha`, baked into the images) but which image
ran. The `predictor` template SHALL set `SRP_PREDICT_CONTAINER_DIGEST` and the `trait-extractor`
template SHALL set `SRT_TRAITS_CONTAINER_DIGEST`.

The `images-downloader`, `write-back` and `exit-gate` stages are outside this requirement: all
three run `bloomctl`, which emits no provenance envelope and reads no such variable. Note that
"producer" elsewhere in this capability (`continueOn`, the exit-gate) means the three stages
`images-downloader`, `predictor` and `trait-extractor`; this requirement is deliberately narrower,
which is why it is not phrased in terms of producers. The `local-WSL2-*` template variants are also
outside it: they are a local dry-run path, are not registered to any cluster, and are not part of
the manifest set `scripts/check_manifests.py` validates.

Each value SHALL be the `sha256:`-prefixed manifest digest of the image that same template pins,
and each template's `image:` reference SHALL carry that digest, so the pinned image is the single
in-file source of truth for the value and the two cannot be updated independently. Because a
digest that disagrees with the image that actually ran is a false provenance record rather than a
missing one — and therefore worse than the empty string both fields default to — a template SHALL
NOT declare either variable without its `image:` being digest-pinned to the same value.

Each reference SHALL also retain a `sha-<sha>` tag before the `@`. Where a reference carries both,
**the digest is authoritative and the tag is human-facing only**: the tag's agreement with the
digest is verified by hand against the registry at pin time and is NOT re-checked by
`scripts/check_manifests.py`, which performs no network resolution. No consumer SHALL derive image
identity from the tag.

Only the stage's own digest is injected. `predict_container_digest` reaches the trait-extractor's
envelope threaded through predict's `{scan}.predictions.json` manifest, not from the
trait-extractor pod's environment, so the `trait-extractor` template SHALL NOT set
`SRP_PREDICT_CONTAINER_DIGEST`.

*Informative (a property of `sleap-roots-contracts`, not a constraint this capability can
enforce):* these variables are recorded in provenance only. As of `identity.py`,
`compute_idempotency_key` hashes `scan_key`, `images_checksum`, `models`, `param_hash`,
`predict_code_sha`, `traits_code_sha` and, when non-empty, `predict_output_params` — no container
digest. Setting these variables therefore invalidates no accumulated key and triggers no
recomputation.

#### Scenario: The predictor injects its own digest, consistent with its pinned image

- **WHEN** `sleap-roots-predictor-template.yaml` is inspected
- **THEN** its `image:` reference matches `@sha256:[0-9a-f]{64}`
- **AND** its `image:` reference also carries a `sha-<sha>` tag before the `@`
- **AND** its container `env` contains exactly one `SRP_PREDICT_CONTAINER_DIGEST` entry
- **AND** that entry's `value` matches `^sha256:[0-9a-f]{64}$`
- **AND** that entry's `value` equals the digest parsed from its own `image:` reference

#### Scenario: The trait-extractor injects its own digest, consistent with its pinned image

- **WHEN** `sleap-roots-trait-extractor-template.yaml` is inspected
- **THEN** its `image:` reference matches `@sha256:[0-9a-f]{64}`
- **AND** its `image:` reference also carries a `sha-<sha>` tag before the `@`
- **AND** its container `env` contains exactly one `SRT_TRAITS_CONTAINER_DIGEST` entry
- **AND** that entry's `value` matches `^sha256:[0-9a-f]{64}$`
- **AND** that entry's `value` equals the digest parsed from its own `image:` reference

#### Scenario: A pin bump that updates only one side fails the manifest check

- **WHEN** a template's `image:` digest is bumped without updating its digest env var, or the env
  var is changed without updating `image:`
- **THEN** `scripts/check_manifests.py` exits non-zero, naming the stage whose digest disagrees
- **AND** the expected value is derived by parsing the template's own `image:` line, so no literal
  digest appears in the checker

#### Scenario: An absent or malformed digest cannot satisfy the consistency check

- **WHEN** a template declares a digest env var whose value is empty or not a well-formed
  `sha256:<64 hex>` string
- **THEN** `scripts/check_manifests.py` exits non-zero
- **AND** when a template's `image:` reference carries no parseable `@sha256:<64 hex>` digest while
  its digest env var is present, the equality assertion itself reports failure rather than
  comparing two absent values and passing vacuously

#### Scenario: A newly-computed scan records the digest of the image that ran

- **WHEN** a workflow completes against templates registered from these manifests
- **AND** a scan is newly predicted and newly trait-extracted by that run, rather than skipped by
  either stage's idempotency-key check
- **THEN** that scan's `{scan_key}.result.json` has non-empty
  `provenance.predict_container_digest` and `provenance.traits_container_digest`
- **AND** each equals the digest pinned by the corresponding deployed `WorkflowTemplate`

#### Scenario: Injecting the digest does not retroactively populate skipped scans

- **WHEN** a workflow runs over a tree whose predictions and results were produced by an earlier,
  non-digest-injecting image, and both stages skip on an unchanged idempotency key
- **THEN** those scans' existing manifests and envelopes are left unchanged, with both digest
  fields still empty
- **AND** this is expected rather than a defect: the container digest is not an idempotency-key
  input, so populating it invalidates no accumulated work and forces no recomputation

#### Scenario: The trait-extractor does not fabricate the predict digest

- **WHEN** `sleap-roots-trait-extractor-template.yaml` is inspected
- **THEN** its container `env` contains no `SRP_PREDICT_CONTAINER_DIGEST` entry

## MODIFIED Requirements

### Requirement: Predictor runs the warm GHCR predict container

The `predictor` template SHALL run the rebuilt warm-batch predict container (the
`sleap-roots-predict` GHCR image), invoked as `<image> <input_dir> <output_dir>` with a
`WANDB_API_KEY` environment variable sourced from a Kubernetes secret. Its image reference SHALL
be pinned by `@sha256:` digest, retaining the `sha-<sha>` tag alongside it for readability; a
tag-only reference is no longer sufficient, because a `sha-<gitsha>` tag is immutable in name only
(a rebuild of the same commit can overwrite it in GHCR) and because the digest env var this
template injects is validated against the digest in this line. The template SHALL NOT
mount a model-input directory (models load in-process from the wandb registry). It SHALL request
a fractional GPU via a pod-level `gpu-memory` annotation (an absolute MiB value, not a whole-GPU
`resources.limits.nvidia.com/gpu` and not a relative `gpu-fraction`), SHALL explicitly set
`schedulerName: runai-scheduler` (defense-in-depth, since the annotation-only GPU request has no
`nvidia.com/gpu` fallback if scheduler wiring ever changes), SHALL NOT set `privileged: true` or
`runAsUser: 0` on its `securityContext`, and SHALL retain a `retryStrategy`.

#### Scenario: Predictor template uses the GHCR predict image with WANDB key and no models mount

- **WHEN** `sleap-roots-predictor-template.yaml` is inspected
- **THEN** the container image is the `sleap-roots-predict` GHCR image pinned by `@sha256:` digest
  (not `:latest`, and not a bare `sha-<sha>` tag)
- **AND** its `args` are the input and output directory mount paths only (no models-input argument)
- **AND** it sets `WANDB_API_KEY` from a `secretKeyRef`
- **AND** it declares no models-input `volumeMount`

#### Scenario: Predictor requests a fractional GPU at the pod level

- **WHEN** `sleap-roots-predictor-template.yaml` is inspected
- **THEN** `spec.templates[predictor].metadata.annotations` declares `gpu-memory` with a positive
  numeric string value (MiB)
- **AND** it does NOT declare a `gpu-fraction` annotation
- **AND** the container's `resources.limits` does NOT include `nvidia.com/gpu`
- **AND** `spec.templates[predictor].schedulerName` is explicitly `runai-scheduler`
- **AND** the container's `securityContext` does NOT set `privileged: true`
- **AND** the container's `securityContext` does NOT set `runAsUser: 0`

#### Scenario: Multiple predictor pods co-schedule on one physical GPU

- **WHEN** two predictor pods, each requesting the template's `gpu-memory` value, are scheduled
  concurrently onto the same physical GPU
- **THEN** both pods complete successfully
- **AND** neither pod is OOM-killed

#### Scenario: Predictor retries correctly under the fractional GPU shape

- **WHEN** a predictor pod is preempted or evicted mid-run
- **THEN** `retryStrategy` retries the step
- **AND** the retried pod schedules successfully under the same `gpu-memory` annotation

#### Scenario: Predictor writes as non-root into a pre-existing, previously root-owned directory

- **WHEN** the predictor processes a scan whose output directory already exists on the shared
  `predictions-output-dir` path from a prior run under the old `runAsUser: 0` configuration
- **AND** that scan's existing output files are absent or stale, so skip-if-done does not
  short-circuit
- **THEN** the predictor (running without `privileged`/`runAsUser: 0`) successfully writes fresh
  output files into that pre-existing directory
- **AND** no permission-denied error occurs

### Requirement: Trait-extractor runs the GHCR trait-extractor image

The `trait-extractor` template SHALL run `ghcr.io/talmolab/sleap-roots-trait-extractor`, passing
only the input and output directory paths as `args` (the image's `ENTRYPOINT` is
`["python","-m","trait_extractor"]`). Its image reference SHALL be pinned by `@sha256:` digest,
retaining the `sha-<sha>` tag alongside it for readability; a tag-only reference is no longer
sufficient, for the same two reasons given for the predictor. It SHALL read the predictor's output
mount as its input and write its results to a separate output mount.

#### Scenario: Trait-extractor template uses the GHCR image via the module entry

- **WHEN** `sleap-roots-trait-extractor-template.yaml` is inspected
- **THEN** the container image is `ghcr.io/talmolab/sleap-roots-trait-extractor` pinned by
  `@sha256:` digest (not a bare `sha-<sha>` tag)
- **AND** its `args` are exactly the input and output mount paths (no `python /workspace/src/main.py` prefix)
- **AND** its input mount is the same volume the predictor writes its predictions to
