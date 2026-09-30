## ADDED Requirements

### Requirement: GPU and stage-in concurrency are bounded by namespace semaphores

The pipeline SHALL let at most `pipeline-gpu` predictor tasks, and at most `pipeline-stage-in`
images-downloader tasks, hold a slot at once across every Workflow in `runai-busch-lab` that uses
these templates. A task SHALL hold its slot across all of its retry attempts and the backoff between them, and a task
waiting for a slot SHALL have no pod.

To that end, the `predictor` template SHALL acquire the `pipeline-gpu` key, and the
`images-downloader` template SHALL acquire the `pipeline-stage-in` key, of the ConfigMap
`sleap-roots-pipeline-semaphores`, each through `synchronization.semaphores[].configMapKeyRef` (the
plural list form, with no singular `semaphore` and no mutex). Each template SHALL reference only its
own key.

The ConfigMap SHALL be defined in this repo in `sleap-roots-pipeline-semaphores.yaml`, in namespace
`runai-busch-lab`, and SHALL define exactly the keys the templates acquire. Each value SHALL be a
quoted decimal integer string of at least 1.

`pipeline-gpu` SHALL NOT exceed 10, the number of predictor GPU slices busch-lab's 2-GPU deserved
quota holds at the predictor's `gpu-memory: "8192"` (5 per GPU), and the predictor's `gpu-memory`
annotation SHALL be `"8192"` for as long as that bound stands.

#### Scenario: Both stages acquire their own semaphore key

- **WHEN** `sleap-roots-predictor-template.yaml` and `sleap-roots-images-downloader-template.yaml`
  are inspected
- **THEN** the `predictor` template's `synchronization.semaphores` holds exactly one
  `configMapKeyRef` with name `sleap-roots-pipeline-semaphores` and key `pipeline-gpu`
- **AND** the `images-downloader` template's holds exactly one with the same name and key
  `pipeline-stage-in`
- **AND** neither template's `synchronization` has any other field

#### Scenario: Every referenced key resolves to a valid limit

- **WHEN** `sleap-roots-pipeline-semaphores.yaml` is inspected
- **THEN** it is a `ConfigMap` named `sleap-roots-pipeline-semaphores` in namespace `runai-busch-lab`
- **AND** its `data` keys are exactly `pipeline-gpu` and `pipeline-stage-in`
- **AND** each value is a quoted string matching `^[1-9][0-9]*$`

#### Scenario: The GPU limit fits the quota's slice capacity

- **WHEN** the ConfigMap's `pipeline-gpu` value and the predictor template are read
- **THEN** `pipeline-gpu` is at most 10
- **AND** the predictor template's `gpu-memory` annotation is `"8192"`, the value the bound was
  derived at

#### Scenario: A task waiting for a slot starts no pod (verified live)

- **WHEN** more predictor tasks are ready than `pipeline-gpu` allows
- **THEN** each excess predictor node is `Pending` with a message naming the
  `runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/pipeline-gpu` lock
- **AND** no pod exists for that node until a slot is released
- **AND** the same holds for images-downloader tasks and the `pipeline-stage-in` lock

### Requirement: The drift check covers the semaphore ConfigMap

`scripts/check_cluster_drift.sh` SHALL compare the live `sleap-roots-pipeline-semaphores`
ConfigMap's `data` with `sleap-roots-pipeline-semaphores.yaml`'s. It SHALL report a missing
ConfigMap or any differing, missing or extra key as drift (exit 1). It SHALL report a failed read of
the ConfigMap, or a failed comparison, as CHECK FAILED (exit 2), and SHALL never report sync in that
case. No drift finding SHALL lower an earlier CHECK FAILED result from 2 to 1.

#### Scenario: A live retune is reported

- **WHEN** a live `data` value differs from the repo's
- **THEN** the check prints DRIFT with each differing key's repo and live values
- **AND** exits 1, or 2 if a CHECK FAILED was already recorded

#### Scenario: A missing ConfigMap is reported

- **WHEN** the ConfigMap does not exist in the namespace
- **THEN** the check prints NOT CREATED and exits non-zero

#### Scenario: An unreadable ConfigMap is not mistaken for a missing one

- **WHEN** the `kubectl get` of the ConfigMap itself fails
- **THEN** the check prints CHECK FAILED and exits 2

## MODIFIED Requirements

### Requirement: Launcher registers every workflow template

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, `write-back`, and `exit-gate` templates.

Before registering any template, it SHALL ensure the `sleap-roots-pipeline-semaphores` ConfigMap
exists in the target namespace: it SHALL create it from `sleap-roots-pipeline-semaphores.yaml` if a
`kubectl get --ignore-not-found` returns nothing, and SHALL NOT update or replace one that exists.
If an existing ConfigMap lacks a key the templates acquire, or holds a value that is not a decimal
integer of at least 1, or if `kubectl` is absent or the `kubectl get` itself fails, it SHALL exit
non-zero without registering any template.

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
- **THEN** its only `kubectl create` is of `sleap-roots-pipeline-semaphores.yaml`, on the branch where
  a `kubectl get --ignore-not-found` of the ConfigMap returned nothing
- **AND** that step precedes the template-registration loop
- **AND** the script contains no `kubectl apply`, `replace`, `edit` or `patch`
- **AND** the list of keys it validates equals the ConfigMap's keys

#### Scenario: Launcher stops before any template when it cannot ensure the ConfigMap

- **WHEN** the launcher runs and `kubectl get` fails, or the existing ConfigMap lacks a key
- **THEN** it exits non-zero
- **AND** it has made no `argo` call

#### Scenario: Launcher registers into the namespace the Workflow runs in

- **WHEN** `runai_run_pipeline.sh` and `sleap-roots-pipeline.yaml` are inspected
- **THEN** the launcher's `NAMESPACE` value is `runai-busch-lab`
- **AND** that value equals the Workflow's `metadata.namespace`

#### Scenario: The launcher's namespace is a literal, not an environment-variable expansion

- **WHEN** `runai_run_pipeline.sh`'s `NAMESPACE` assignment is inspected
- **THEN** it is a plain literal value
- **AND** it contains no parameter expansion or default-value syntax that would let an environment
  variable redirect where templates are registered
