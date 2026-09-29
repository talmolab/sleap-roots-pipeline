# per-batch-pipeline Specification

## Purpose
TBD - created by archiving change add-per-batch-argo-workflow. Update Purpose after archive.
## Requirements
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
the same `project: busch-lab` label the `predictor`/`trait-extractor` templates carry, for
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
- **AND** both carry a `project: busch-lab` label

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

### Requirement: Per-batch DAG with a terminal exit-code gate

The pipeline Workflow SHALL define a five-task DAG: four processing stages — `images-downloader`
(root) → `predictor` → `trait-extractor` → `write-back` — followed by a terminal `exit-gate` task
depending on `write-back`. Each task SHALL depend on the one before it, and `exit-gate` SHALL be
the only task that no other task depends on, so the Workflow's final phase is determined by the
gate rather than by any stage's own node phase. The Workflow SHALL declare a `scan-ids` argument
parameter that `images-downloader` consumes, so the batch a run processes is a caller-supplied
input rather than a hardcoded scan. The Workflow SHALL set `spec.serviceAccountName:
bloom-workflow` so every step's pod can report its results back to Argo. Its `hostPath` volumes
SHALL use `type: Directory`, not `type: DirectoryOrCreate`, so a down NFS mount cannot silently
write output to the node's local disk. Note the resulting failure mode is a **hang, not a loud
failure**: a pod that cannot mount its `hostPath` sits `Pending`, not `Failed` or `Error`, so
neither `retryStrategy` nor `continueOn` applies. The DAG SHALL use
`dependencies:`, never `depends:`, since the latter is all-or-nothing per DAG template and would
forbid `continueOn` on every task in it. Because this file is the only canonical,
correctly-complete definition of this Workflow's shape — and is independently reconstructed
programmatically elsewhere (`salk-bloom`'s dispatch worker) with no built-in mechanism to detect
drift between the two — the file SHALL carry a header comment stating plainly that it is vendored
(pinned to a commit SHA, CI-checked for drift) by `salk-bloom` for programmatic dispatch, so an
editor of its `volumes`/`entrypoint`/`serviceAccountName`/DAG structure is warned at the point of
editing rather than discovering the drift only when a real batch dispatch fails.

#### Scenario: Workflow runs the four processing stages in order, then the gate

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** its DAG has exactly five tasks: `images-downloader`, `predictor`, `trait-extractor`,
  `write-back`, `exit-gate`
- **AND** `predictor` lists `images-downloader` in its `dependencies`
- **AND** `trait-extractor` lists `predictor` in its `dependencies`
- **AND** `write-back` lists `trait-extractor` in its `dependencies`
- **AND** `exit-gate` lists `write-back` in its `dependencies`
- **AND** `exit-gate` is the only task that no other task lists in its `dependencies`
- **AND** the Workflow declares a `scan-ids` entry under `arguments.parameters`

#### Scenario: DAG uses dependencies, not depends

- **WHEN** the Workflow's DAG tasks are inspected
- **THEN** no task declares a `depends` field
- **AND** every task with a predecessor declares `dependencies`

#### Scenario: Workflow sets bloom-workflow as its ServiceAccount

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** `spec.serviceAccountName` is `bloom-workflow`
- **AND** none of the five workflow templates override `serviceAccountName` at the template level

#### Scenario: hostPath volumes require their path to pre-exist

- **WHEN** the Workflow's `volumes` are inspected
- **THEN** `images-input-dir`, `predictions-output-dir`, and `traits-output-dir` all declare
  `hostPath.type: Directory`
- **AND** none of the three declares `type: DirectoryOrCreate`
- **AND** the consequence is documented as a `Pending` hang rather than a pod failure, since
  `assessNodeStatus` maps `PodPending` unconditionally to `NodePending` at v3.6.7

#### Scenario: File carries a cross-repo vendoring guardrail

- **WHEN** `sleap-roots-pipeline.yaml` is inspected
- **THEN** its header comments name `salk-bloom` as vendoring a pinned copy of this file for
  programmatic dispatch
- **AND** the comment names the drift-check mechanism (a CI check comparing the vendored copy
  against this file at the pinned commit)
- **AND** the comment states that changing this file's `volumes`, `entrypoint`,
  `serviceAccountName`, or DAG structure requires updating the vendored copy and its pinned
  reference in `salk-bloom`

### Requirement: Launcher registers every workflow template

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, `write-back`, and `exit-gate` templates.

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

#### Scenario: Launcher registers into the namespace the Workflow runs in

- **WHEN** `runai_run_pipeline.sh` and `sleap-roots-pipeline.yaml` are inspected
- **THEN** the launcher's `NAMESPACE` value is `runai-busch-lab`
- **AND** that value equals the Workflow's `metadata.namespace`

#### Scenario: The launcher's namespace is a literal, not an environment-variable expansion

- **WHEN** `runai_run_pipeline.sh`'s `NAMESPACE` assignment is inspected
- **THEN** it is a plain literal value
- **AND** it contains no parameter expansion or default-value syntax that would let an environment
  variable redirect where templates are registered

### Requirement: A partial-success exit does not terminate the batch

Each of the three producer tasks — `images-downloader`, `predictor`, `trait-extractor` — SHALL
declare `continueOn: {failed: true}` on the task itself in the DAG, so that a stage which completes
its batch while isolating one or more per-scan failures does not prevent the remaining stages from
running on the scans that succeeded.

`continueOn` SHALL declare `failed` only, and SHALL NOT declare `error`. A `Failed` node means the
container ran and exited non-zero, which covers both the partial-success exit code and RunAI
eviction; an `Error` node means the stage never ran at all (image pull failure, wait-container
death, pod deleted), and the DAG must stop rather than continue on data that was never produced.

`continueOn` SHALL be declared on the failing task itself, never on a downstream task, since Argo
applies it to that task's dependents and placing it downstream both fails to have the intended
effect and triggers a known upstream defect.

`write-back` SHALL NOT declare `continueOn`, since `bloomctl cyl batch-ingest-result` has no
partial-success exit code and there is nothing to let through.

The producer templates' `retryStrategy` blocks SHALL retain `retryPolicy: Always` with their
existing limits, and SHALL NOT declare a `retryStrategy.expression`. Argo's whole-step retry is
currently the only scan-level retry mechanism that exists in any producer, so suppressing retries
on the partial-success code would permanently isolate a scan that a further attempt would have
completed.

#### Scenario: Producer tasks tolerate a failed node

- **WHEN** the Workflow's DAG tasks are inspected
- **THEN** `images-downloader`, `predictor` and `trait-extractor` each declare
  `continueOn.failed: true`
- **AND** none of them declares `continueOn.error`
- **AND** `write-back` declares no `continueOn` at all

#### Scenario: Producer retry strategies are unchanged and expression-free

- **WHEN** the three producer templates are inspected
- **THEN** each retains `retryPolicy: Always`
- **AND** none declares a `retryStrategy.expression`

#### Scenario: A partially-failing stage lets the remaining scans through

- **WHEN** a batch is submitted in which one scan fails permanently and the others succeed, and a
  producer stage therefore exits with the partial-success code after exhausting its retries
- **THEN** the downstream stages run
- **AND** the scans that succeeded reach `write-back` and are ingested
- **AND** the failed scan is recorded as `failed` at the run level

#### Scenario: A stage that never ran stops the DAG

- **WHEN** a producer's pod fails to start at all, producing an `Error` rather than a `Failed` node
- **THEN** the DAG does not proceed past that stage
- **AND** `exit-gate` is `Omitted` and inherits the failure
- **AND** the Workflow's final phase is `Failed`

### Requirement: An exit-code gate determines the Workflow's final phase

The DAG SHALL include a terminal `exit-gate` task, backed by
`sleap-roots-exit-gate-template.yaml`, which receives each producer's real exit code and exits
non-zero unless every one of them is either `0` (all scans succeeded) or the partial-success code
`3`. Because `continueOn` keys only on a node's phase and cannot read exit codes, without this gate
an exhausted-retry crash would be indistinguishable from a partial success and would report the
Workflow `Succeeded`.

The gate SHALL receive the exit codes as **three separately-named** input parameters, one per
producer, and SHALL NOT receive them as a single delimiter-joined value — splitting a joined value
in a shell silently collapses an empty field, so a missing code would pass undetected.

The gate SHALL perform the comparison inside its container against an explicit allowlist of the
accepted values, and SHALL NOT use a `when:` expression, because `when:` is evaluated by govaluate
rather than expr, so integer-coercion helpers are unavailable and a mixed string/number comparison
is a parse error.

The gate SHALL reject any value that is not exactly one of the accepted codes — including an empty
value and an unsubstituted `{{tasks.<name>.exitCode}}` placeholder.

Every producer the gate references SHALL remain an ancestor of the gate, since task-scope references
resolve only through a task's ancestry. That constraint is enforced at three independent layers, each
catching something the others do not: a static ancestry assertion over the manifests; Argo's own
`validateDAGTaskArgumentDependency`, which rejects a non-ancestor reference at **both** lint and
submission time (verified — it reports `missing dependency '<task>' for parameter '<name>'`, so a
broken ancestry cannot reach the cluster silently); and the gate's allowlist.

The allowlist remains necessary because it covers a case the validator cannot: a task that *is* a
valid ancestor but produced no `outputs.exitCode` — reachable when a node is `Failed` without its
main container having terminated. There the gate receives an empty or unsubstituted value at
runtime, and rejecting anything outside the accepted set is what converts it into a visible
failure.

#### Scenario: Gate accepts success and partial success

- **WHEN** every producer exits either `0` or `3`
- **AND** `write-back` exits `0`
- **THEN** the `exit-gate` task exits `0`
- **AND** the Workflow's final phase is `Succeeded`

#### Scenario: Gate rejects a crash-class exit

- **WHEN** any producer exits with a code other than `0` or `3` after exhausting its retries — for
  example `1` (crash), `2` (usage error) or `143` (`SIGTERM`, once retries are spent)
- **THEN** the `exit-gate` task exits non-zero
- **AND** the Workflow's final phase is `Failed`

#### Scenario: Gate rejects an empty or unresolved exit code

- **WHEN** the value the gate receives for any producer is empty, absent, a literal
  `{{tasks.<name>.exitCode}}` placeholder, or anything else outside the accepted set
- **THEN** the `exit-gate` task exits non-zero
- **AND** the Workflow's final phase is `Failed`

#### Scenario: Gate reads the last attempt's code through a retry node

- **WHEN** a producer task carries a `retryStrategy` and its final attempt exits with a given code
- **THEN** the value the gate receives for that producer is that final attempt's exit code, not an
  empty string

#### Scenario: Gate receives three named parameters, not a joined value or a when expression

- **WHEN** the `exit-gate` DAG task is inspected
- **THEN** it passes three separately-named `arguments.parameters`, one per producer, each carrying
  that producer's `exitCode`
- **AND** it declares no `when` field

#### Scenario: Every producer the gate references is an ancestor of it

- **WHEN** the Workflow's DAG is inspected
- **THEN** every task named in a `{{tasks.<name>.exitCode}}` reference in the `exit-gate` task's
  `arguments.parameters` is reachable from `exit-gate` by transitively following `dependencies`

#### Scenario: A failing write-back fails the Workflow through the gate

- **WHEN** `write-back` fails after exhausting its retries
- **THEN** `exit-gate` is `Omitted` and inherits the failure
- **AND** the Workflow's final phase is `Failed`

#### Scenario: The gate attests machinery completion, not data completeness

- **WHEN** the `exit-gate` task and its template are inspected
- **THEN** the template declares no `volumeMounts`, so the gate cannot observe whether any output
  was written
- **AND** the gate's decision is derived solely from the producers' exit codes
- **AND** a passing gate therefore attests that every producer stage completed acceptably, and does
  **not** attest that any scan was processed or that any output landed

### Requirement: The exit-gate template runs without data or credential access

`sleap-roots-exit-gate-template.yaml` SHALL pin its container image by immutable tag or digest
(never `:latest`), and SHALL override `command`, because the reused image's `ENTRYPOINT` is the
`bloomctl` CLI with no `CMD` — an args-only template would run `bloomctl <script>` and fail every
Workflow, including successful ones.

The template SHALL declare no `volumeMounts`, so Argo attaches neither the `hostPath` data volumes
nor the credentials Secret to its pod, and SHALL NOT set `HOME`: the gate reads no data and makes
no Bloom API call.

The template SHALL declare an explicit `priorityClassName`, since the priority an Argo pod receives
with none declared cannot be verified from this repo's credentials (the cluster-scoped
`priorityclasses` API is Forbidden to the `argo-user` identities) and pods observed with none
resolved to priority `0` — the lowest tier, below `train`. It SHALL declare a
`retryStrategy` with `retryPolicy: Always` **and a `backoff`**, since it is the DAG's only leaf: a
transient gate-pod failure would otherwise report a fully-successful batch as `Failed`, and
retrying immediately against a still-contended cluster spends the whole budget in seconds. It SHALL
declare `resources` requests, so the pod is not BestEffort QoS. It SHALL carry the same `project`
label the other stage templates carry — for consistency only; object-level metadata is not copied
onto the pod and is inert for quota attribution, which RunAI derives from the namespace.

#### Scenario: Gate template overrides the image entrypoint and pins its image

- **WHEN** `sleap-roots-exit-gate-template.yaml` is inspected
- **THEN** its container declares a `command`
- **AND** its image is pinned by an immutable `sha-<sha>` tag or digest, not `:latest`

#### Scenario: Gate template reaches no data and no credentials

- **WHEN** `sleap-roots-exit-gate-template.yaml` is inspected
- **THEN** its container declares no `volumeMounts`
- **AND** it sets no `HOME` environment variable
- **AND** it declares no `serviceAccountName` at the template level

#### Scenario: Gate template declares its scheduling and resilience fields

- **WHEN** `sleap-roots-exit-gate-template.yaml` is inspected
- **THEN** it declares an explicit `priorityClassName`
- **AND** it declares a `retryStrategy` whose `retryPolicy` is `Always`
- **AND** that `retryStrategy` declares a `backoff.duration`
- **AND** it declares `resources.requests`
- **AND** it carries a `project` label matching the other stage templates

### Requirement: Every producer carries the Argo workflow identity

Every batch-processing stage template SHALL set an `ARGO_WORKFLOW_NAME` environment variable
sourced from Argo's built-in `{{workflow.name}}` — `images-downloader`, `predictor`,
`trait-extractor` and `write-back` alike.

The two `bloomctl` stages already consume it. The `predictor` consumes it since its predict#47 pin
(2026-09-25): predict resolves `run_manifest.<ARGO_WORKFLOW_NAME>.json` ahead of the legacy file.
The `trait-extractor` does not consume it yet (its pinned image predates sleap-roots#269), and it
is inert there today. It is required because the stage directories are
fixed, shared `hostPath`s and `run_manifest.json` accumulates `scan_keys` across every run that
writes into them. Once a producer stage can be reached after an upstream failure, the manifest a
stage is scoped by may belong to a different run, and a stage has no way to detect that without
knowing its own workflow identity. Carrying it is the prerequisite for any run-scope validation.

#### Scenario: All four batch-processing templates carry ARGO_WORKFLOW_NAME

- **WHEN** the images-downloader, predictor, trait-extractor and write-back templates are inspected
- **THEN** each declares an `ARGO_WORKFLOW_NAME` entry in its container `env:`
- **AND** each such entry's `value` is exactly `"{{workflow.name}}"`

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

