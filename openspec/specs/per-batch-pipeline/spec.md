# per-batch-pipeline Specification

## Purpose
TBD - created by archiving change add-per-batch-argo-workflow. Update Purpose after archive.
## Requirements
### Requirement: Four-stage per-batch DAG

The pipeline Workflow SHALL define a four-task DAG: `images-downloader` (root) → `predictor` →
`trait-extractor` → `write-back`, with each stage depending on the one before it. The Workflow
SHALL declare a `scan-ids` argument parameter that `images-downloader` consumes, so the batch a run
processes is a caller-supplied input rather than a hardcoded scan. The Workflow SHALL set
`spec.serviceAccountName: bloom-workflow` so every step's pod can report its results back to Argo.
Its `hostPath` volumes SHALL use `type: Directory`, not `type: DirectoryOrCreate`, so a down NFS
mount fails the pod loudly instead of silently writing output to the node's local disk.

#### Scenario: Workflow runs all four stages in order

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** its DAG has exactly four tasks: `images-downloader`, `predictor`, `trait-extractor`,
  `write-back`
- **AND** `predictor` lists `images-downloader` in its `dependencies`
- **AND** `trait-extractor` lists `predictor` in its `dependencies`
- **AND** `write-back` lists `trait-extractor` in its `dependencies`
- **AND** the Workflow declares a `scan-ids` entry under `arguments.parameters`

#### Scenario: Workflow sets bloom-workflow as its ServiceAccount

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** `spec.serviceAccountName` is `bloom-workflow`
- **AND** none of the four stage templates override `serviceAccountName` at the template level

#### Scenario: hostPath volumes fail loudly on a down NFS mount

- **WHEN** the Workflow's `volumes` are inspected
- **THEN** `images-input-dir`, `predictions-output-dir`, and `traits-output-dir` all declare
  `hostPath.type: Directory`
- **AND** none of the three declares `type: DirectoryOrCreate`

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

### Requirement: Trait-extractor runs the GHCR trait-extractor image

The `trait-extractor` template SHALL run `ghcr.io/talmolab/sleap-roots-trait-extractor`, passing
only the input and output directory paths as `args` (the image's `ENTRYPOINT` is
`["python","-m","trait_extractor"]`). It SHALL read the predictor's output mount as its input and
write its results to a separate output mount.

#### Scenario: Trait-extractor template uses the GHCR image via the module entry

- **WHEN** `sleap-roots-trait-extractor-template.yaml` is inspected
- **THEN** the container image is `ghcr.io/talmolab/sleap-roots-trait-extractor` pinned by digest or `sha-<sha>`
- **AND** its `args` are exactly the input and output mount paths (no `python /workspace/src/main.py` prefix)
- **AND** its input mount is the same volume the predictor writes its predictions to

### Requirement: Images-downloader stages a batch via bloomctl

The `images-downloader` template SHALL run `bloomctl cyl batch-download-for-predict` against the
`images-input-dir` volume, passing the Workflow's `scan-ids` parameter, so `predictor` finds the
batch already staged in the same layout it reads today.

#### Scenario: Images-downloader template stages the requested batch

- **WHEN** `sleap-roots-images-downloader-template.yaml` is inspected
- **THEN** its container `args` invoke `cyl batch-download-for-predict` with the `images-input-dir`
  mount path as the output directory and `--scan-ids {{workflow.parameters.scan-ids}}`
- **AND** it mounts the same `images-input-dir` volume the `predictor` template mounts

### Requirement: Write-back ingests a batch via bloomctl

The `write-back` template SHALL run `bloomctl cyl batch-ingest-result` against the
`traits-output-dir` volume with `--predictions-dir` pointed at `predictions-output-dir`, so every
`ResultEnvelope` `trait-extractor` produces in the batch is written back to Bloom, with blobs
sourced from predict's manifest.

#### Scenario: Write-back template ingests the batch's envelopes and predictions

- **WHEN** `sleap-roots-write-back-template.yaml` is inspected
- **THEN** its container `args` invoke `cyl batch-ingest-result` with the `traits-output-dir` mount
  path as the envelopes directory and `--predictions-dir` set to the `predictions-output-dir` mount
  path
- **AND** it mounts both the `traits-output-dir` and `predictions-output-dir` volumes

### Requirement: bloomctl-based tasks pin their image and mount credentials deterministically

Both the `images-downloader` and `write-back` templates SHALL pin the `bloomctl` container image by
immutable tag or digest (never `:latest`), SHALL set a `HOME` environment variable explicitly, SHALL
set an `ARGO_WORKFLOW_NAME` environment variable sourced from Argo's built-in `{{workflow.name}}`
variable, SHALL mount a Secret at `$HOME/.bloom/credentials.txt` so `bloomctl`'s credential lookup
resolves deterministically regardless of the image's runtime user configuration, and SHALL carry
the same `project: talmo-lab` label the `predictor`/`trait-extractor` templates carry, for
consistency with those templates (note: `sleap-roots-predictor-template.yaml`'s own comment states
this exact label placement — top-level `WorkflowTemplate.metadata.labels` — is "currently INERT"
and is not copied onto the pod by Argo; this requirement follows the existing convention rather
than asserting the label is functionally load-bearing for RunAI quota attribution).

#### Scenario: Both bloomctl templates pin the image and mount credentials at a fixed HOME path

- **WHEN** `sleap-roots-images-downloader-template.yaml` and `sleap-roots-write-back-template.yaml`
  are inspected
- **THEN** both pin the `bloomctl` image by an immutable `sha-<sha>` tag or digest, not `:latest`
- **AND** both set a `HOME` environment variable
- **AND** both mount a Secret volume at `$HOME/.bloom/credentials.txt` (matching the `HOME` value
  they set)
- **AND** both carry a `project: talmo-lab` label

#### Scenario: Both bloomctl templates carry the Argo workflow identity

- **WHEN** `sleap-roots-images-downloader-template.yaml` and `sleap-roots-write-back-template.yaml`
  are inspected
- **THEN** both templates' container `env:` blocks include a `ARGO_WORKFLOW_NAME` entry
- **AND** its `value` is exactly `"{{workflow.name}}"`

#### Scenario: ARGO_WORKFLOW_NAME resolves to the real workflow name on submission

- **WHEN** a Workflow built from `sleap-roots-pipeline.yaml` (or the local-WSL2 counterpart) is
  submitted, referencing the updated `images-downloader` and `write-back` templates
- **THEN** the `ARGO_WORKFLOW_NAME` environment variable inside each stage's container resolves to
  the actual generated workflow name (e.g. `sleap-roots-pipeline-abc12`), not the literal
  unresolved string `{{workflow.name}}`

### Requirement: Launcher registers all four templates

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, and `write-back` templates.

#### Scenario: Launcher's TEMPLATES list contains all four stage templates

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all four template files: the images-downloader,
  predictor, trait-extractor, and write-back templates

