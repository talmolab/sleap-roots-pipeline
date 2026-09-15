## MODIFIED Requirements

### Requirement: Launcher registers all four templates

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, and `write-back` templates. It SHALL default its target namespace to
`runai-busch-lab` — the same value as `sleap-roots-pipeline.yaml`'s own `metadata.namespace` — so
that the namespace it registers templates into is the namespace it submits the Workflow against,
and neither can drift from the manifest without the other. That default SHALL be overridable via a
`NAMESPACE` environment variable, so a one-off submit into another project does not require editing
the script.

#### Scenario: Launcher's TEMPLATES list contains all four stage templates

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all four template files: the images-downloader,
  predictor, trait-extractor, and write-back templates
- **AND** it references no models-downloader template

#### Scenario: Launcher defaults to the busch-lab namespace

- **WHEN** `runai_run_pipeline.sh` is inspected with no `NAMESPACE` set in the environment
- **THEN** its effective namespace is `runai-busch-lab`
- **AND** that value equals `sleap-roots-pipeline.yaml`'s `metadata.namespace`

#### Scenario: Launcher namespace is overridable

- **WHEN** `runai_run_pipeline.sh` is run with `NAMESPACE=runai-talmo-lab` set in the environment
- **THEN** its effective namespace is `runai-talmo-lab`
