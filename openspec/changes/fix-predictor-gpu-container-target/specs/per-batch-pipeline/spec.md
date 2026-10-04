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
a fractional GPU via a pod-level `gpu-memory` annotation (an absolute amount, which RunAI applies
in MB of 10^6 bytes; not a whole-GPU `resources.limits.nvidia.com/gpu` and not a relative
`gpu-fraction`). It SHALL make `main` the pod's first container, via a template-level
`podSpecPatch` whose `$setElementOrder/containers` places `main` before `wait`, because Run:ai
before 2.24 gives the fractional GPU to the first container. It SHALL also declare a pod-level
`gpu-fraction-container-name: "main"` annotation, which selects `main` by name from Run:ai 2.24.
It SHALL explicitly set
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
  numeric string value (MB of 10^6 bytes)
- **AND** it declares `gpu-fraction-container-name` with the value `"main"`
- **AND** `spec.templates[predictor].podSpecPatch` parses as JSON equal to
  `{"$setElementOrder/containers": [{"name": "main"}, {"name": "wait"}]}`
- **AND** it does NOT declare a `gpu-fraction` annotation
- **AND** the container's `resources.limits` does NOT include `nvidia.com/gpu`
- **AND** `spec.templates[predictor].schedulerName` is explicitly `runai-scheduler`
- **AND** the container's `securityContext` does NOT set `privileged: true`
- **AND** the container's `securityContext` does NOT set `runAsUser: 0`

#### Scenario: The predict container, not the Argo sidecar, receives the GPU

- **WHEN** a predictor pod created from the template runs a batch containing at least one scan
  that is not already done
- **THEN** the created pod's `spec.containers[0]` is `main`
- **AND** the `main` container can allocate CUDA memory
- **AND** usable CUDA memory in `main` is capped below the pod's `gpu-memory` value, and allocations
  past the cap fail with a CUDA out-of-memory error
- **AND** predict resolves its inference device to CUDA for every model it loads

#### Scenario: Multiple predictor pods co-schedule on one physical GPU

- **WHEN** two predictor pods, each requesting the template's `gpu-memory` value, are scheduled
  concurrently onto the same physical GPU
- **THEN** both pods complete successfully
- **AND** neither pod is OOM-killed
- **AND** neither pod's predict log reports a CUDA out-of-memory error

#### Scenario: Predictor retries correctly under the fractional GPU shape

- **WHEN** a predictor pod fails, or is preempted or evicted, mid-run
- **THEN** `retryStrategy` retries the step with a new pod built from the same template
- **AND** the retried pod schedules successfully under the same `gpu-memory` annotation
- **AND** the retried pod's `spec.containers[0]` is `main`, and `main` can allocate CUDA memory

#### Scenario: Predictor writes as non-root into a pre-existing, previously root-owned directory

- **WHEN** the predictor processes a scan whose output directory already exists on the shared
  `predictions-output-dir` path from a prior run under the old `runAsUser: 0` configuration
- **AND** that scan's existing output files are absent or stale, so skip-if-done does not
  short-circuit
- **THEN** the predictor (running without `privileged`/`runAsUser: 0`) successfully writes fresh
  output files into that pre-existing directory
- **AND** no permission-denied error occurs
