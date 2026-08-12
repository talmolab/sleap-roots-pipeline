## MODIFIED Requirements

### Requirement: Predictor runs the warm GHCR predict container

The `predictor` template SHALL run the rebuilt warm-batch predict container (the
`sleap-roots-predict` GHCR image), invoked as `<image> <input_dir> <output_dir>` with a
`WANDB_API_KEY` environment variable sourced from a Kubernetes secret. The template SHALL NOT
mount a model-input directory (models load in-process from the wandb registry). It SHALL request
a fractional GPU via a pod-level `gpu-memory` annotation (an absolute MiB value, not a whole-GPU
`resources.limits.nvidia.com/gpu` and not a relative `gpu-fraction`), SHALL explicitly set
`schedulerName: runai-scheduler` (defense-in-depth, since the annotation-only GPU request has no
`nvidia.com/gpu` fallback if scheduler wiring ever changes), SHALL NOT set `privileged: true` or
`runAsUser: 0` on its `securityContext`, and SHALL retain a `retryStrategy`.

#### Scenario: Predictor template uses the GHCR predict image with WANDB key and no models mount

- **WHEN** `sleap-roots-predictor-template.yaml` is inspected
- **THEN** the container image is the `sleap-roots-predict` GHCR image pinned by digest or `sha-<sha>` (not `:latest`)
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
