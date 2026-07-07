# per-scan-pipeline Specification

## Purpose
TBD - created by archiving change add-per-scan-argo-workflow. Update Purpose after archive.
## Requirements
### Requirement: Two-stage warm-predict → traits DAG

The pipeline Workflow SHALL define a two-task DAG in which `predictor` is the root task and
`trait-extractor` depends on `predictor`. It SHALL NOT include a `models-downloader` task, and it
SHALL NOT declare model-staging volumes (`models-input-dir` / `models-output-dir`). Data SHALL
pass between the two stages via shared volume mounts (the predictor's output mount is the
trait-extractor's input mount), not via Argo parameters or artifacts.

#### Scenario: Workflow runs predict then traits with no model-download stage

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** its DAG has exactly two tasks, `predictor` and `trait-extractor`
- **AND** `trait-extractor` lists `predictor` in its `dependencies`
- **AND** there is no `models-downloader` task and no `models-input-dir`/`models-output-dir` volume

### Requirement: Predictor runs the warm GHCR predict container

The `predictor` template SHALL run the rebuilt warm-batch predict container (the
`sleap-roots-predict` GHCR image), invoked as `<image> <input_dir> <output_dir>` with a
`WANDB_API_KEY` environment variable sourced from a Kubernetes secret. The template SHALL NOT
mount a model-input directory (models load in-process from the wandb registry). It SHALL request
a GPU (`nvidia.com/gpu`) and retain a `retryStrategy`.

#### Scenario: Predictor template uses the GHCR predict image with WANDB key and no models mount

- **WHEN** `sleap-roots-predictor-template.yaml` is inspected
- **THEN** the container image is the `sleap-roots-predict` GHCR image pinned by digest or `sha-<sha>` (not `:latest`)
- **AND** its `args` are the input and output directory mount paths only (no models-input argument)
- **AND** it sets `WANDB_API_KEY` from a `secretKeyRef`
- **AND** it declares no models-input `volumeMount`
- **AND** it requests `nvidia.com/gpu`

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

### Requirement: Producer images are pinned, and the launcher registers only the two templates

Both producer images SHALL be pinned by digest or immutable `sha-<sha>` tag, never `:latest`. The
cluster launcher (`runai_run_pipeline.sh`) SHALL register only the `predictor` and
`trait-extractor` templates and SHALL NOT register a `models-downloader` template.

#### Scenario: Launcher no longer registers models-downloader

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains the predictor and trait-extractor template files
- **AND** it does not contain `models-downloader-template.yaml`

