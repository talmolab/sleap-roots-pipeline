## MODIFIED Requirements

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
