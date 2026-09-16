## MODIFIED Requirements

### Requirement: Launcher registers all four templates

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, and `write-back` templates. Its target namespace SHALL equal
`sleap-roots-pipeline.yaml`'s own `metadata.namespace` (`runai-busch-lab`), so that the namespace it
registers templates into is the namespace the Workflow it submits actually runs in.

That value SHALL NOT be overridable by an environment variable. `argo submit -n <ns>` does not
redirect a submission — the manifest's `metadata.namespace` wins — so an override could only move
the template registrations away from the namespace the Workflow still lands in. Targeting another
project requires editing the manifest as well, and registering that project's templates and secrets
first.

#### Scenario: Launcher's TEMPLATES list contains all four stage templates

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all four template files: the images-downloader,
  predictor, trait-extractor, and write-back templates
- **AND** it references no models-downloader template

#### Scenario: Launcher targets the busch-lab namespace

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its `NAMESPACE` value is `runai-busch-lab`
- **AND** that value equals `sleap-roots-pipeline.yaml`'s `metadata.namespace`
- **AND** it is a literal, not an environment-variable expansion
