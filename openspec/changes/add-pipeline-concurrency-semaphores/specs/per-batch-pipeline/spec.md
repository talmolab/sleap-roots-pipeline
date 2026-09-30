## ADDED Requirements

### Requirement: GPU and stage-in concurrency are bounded by namespace semaphores

The `predictor` template SHALL acquire the `pipeline-gpu` key, and the `images-downloader` template
SHALL acquire the `pipeline-stage-in` key, of the ConfigMap `sleap-roots-pipeline-semaphores`, each
through `synchronization.semaphores[].configMapKeyRef`. Each template SHALL reference only its own
key.

The ConfigMap SHALL be defined in this repo in `sleap-roots-pipeline-semaphores.yaml`, in namespace
`runai-busch-lab`, and SHALL define both keys. Each value SHALL be a decimal integer of at least 1.

`pipeline-gpu` SHALL NOT exceed 10, the number of predictor GPU slices busch-lab's 2-GPU deserved
quota holds at `gpu-memory: "8192"` (5 per GPU).

The local-WSL2 templates SHALL NOT declare `synchronization`.

#### Scenario: Both stages acquire their own semaphore key

- **WHEN** `sleap-roots-predictor-template.yaml` and `sleap-roots-images-downloader-template.yaml`
  are inspected
- **THEN** the `predictor` template's `synchronization.semaphores` holds exactly one
  `configMapKeyRef` with name `sleap-roots-pipeline-semaphores` and key `pipeline-gpu`
- **AND** the `images-downloader` template's holds exactly one with the same name and key
  `pipeline-stage-in`

#### Scenario: Every referenced key resolves to a valid limit

- **WHEN** `sleap-roots-pipeline-semaphores.yaml` is inspected
- **THEN** it is a `ConfigMap` named `sleap-roots-pipeline-semaphores` in namespace `runai-busch-lab`
- **AND** its `data` defines every key a template references
- **AND** each such value parses as an integer of at least 1

#### Scenario: The GPU limit fits the quota's slice capacity

- **WHEN** the ConfigMap's `pipeline-gpu` value is read
- **THEN** it is at most 10

#### Scenario: A task waiting for a slot starts no pod

- **WHEN** more predictor tasks are ready than `pipeline-gpu` allows
- **THEN** each excess predictor node is `Pending` with a message naming the
  `runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/pipeline-gpu` lock
- **AND** no pod exists for that node until a slot is released

#### Scenario: Local templates are exempt

- **WHEN** the `local-WSL2-*-template.yaml` files are inspected
- **THEN** none of their templates declares `synchronization`

## MODIFIED Requirements

### Requirement: Launcher registers every workflow template

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, `write-back`, and `exit-gate` templates.

Before registering any template, it SHALL create the `sleap-roots-pipeline-semaphores` ConfigMap from
`sleap-roots-pipeline-semaphores.yaml` if that ConfigMap does not exist in the target namespace, and
SHALL NOT update or replace one that does.

Its target namespace SHALL equal `sleap-roots-pipeline.yaml`'s own `metadata.namespace`
(`runai-busch-lab`), so that the namespace it registers templates into is the namespace the Workflow
it submits actually runs in.

That value SHALL NOT be overridable by an environment variable. `argo submit -n <ns>` does not
redirect a submission — the manifest's `metadata.namespace` wins — so an override could only move
the template registrations away from the namespace the Workflow still lands in. Targeting another
project requires editing the manifest as well, and registering that project's templates and secrets
first.

#### Scenario: Launcher's TEMPLATES list contains every workflow template

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all five template files: the images-downloader,
  predictor, trait-extractor, write-back, and exit-gate templates
- **AND** it references no models-downloader template

#### Scenario: Launcher creates the semaphore ConfigMap only when absent, before templates

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** it creates `sleap-roots-pipeline-semaphores.yaml` only on the branch where getting the
  `sleap-roots-pipeline-semaphores` ConfigMap fails
- **AND** that step precedes the template-registration loop
- **AND** the script contains no `kubectl apply`, `replace` or `edit` of that ConfigMap

#### Scenario: Launcher registers into the namespace the Workflow runs in

- **WHEN** `runai_run_pipeline.sh` and `sleap-roots-pipeline.yaml` are inspected
- **THEN** the launcher's `NAMESPACE` value is `runai-busch-lab`
- **AND** that value equals the Workflow's `metadata.namespace`

#### Scenario: The launcher's namespace is a literal, not an environment-variable expansion

- **WHEN** `runai_run_pipeline.sh`'s `NAMESPACE` assignment is inspected
- **THEN** it is a plain literal value
- **AND** it contains no parameter expansion or default-value syntax that would let an environment
  variable redirect where templates are registered
