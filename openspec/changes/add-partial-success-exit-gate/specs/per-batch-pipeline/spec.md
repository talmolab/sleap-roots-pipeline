## RENAMED Requirements

- FROM: `### Requirement: Four-stage per-batch DAG`
- TO: `### Requirement: Per-batch DAG with a terminal exit-code gate`

- FROM: `### Requirement: Launcher registers all four templates`
- TO: `### Requirement: Launcher registers every workflow template`

## MODIFIED Requirements

### Requirement: Per-batch DAG with a terminal exit-code gate

The pipeline Workflow SHALL define a five-task DAG: four processing stages — `images-downloader`
(root) → `predictor` → `trait-extractor` → `write-back` — followed by a terminal `exit-gate` task
depending on `write-back`. Each task SHALL depend on the one before it, and `exit-gate` SHALL be
the only task that no other task depends on, so the Workflow's final phase is determined by the
gate rather than by any stage's own node phase. The Workflow SHALL declare a `scan-ids` argument
parameter that `images-downloader` consumes, so the batch a run processes is a caller-supplied
input rather than a hardcoded scan. The Workflow SHALL set `spec.serviceAccountName:
bloom-workflow` so every step's pod can report its results back to Argo. Its `hostPath` volumes
SHALL use `type: Directory`, not `type: DirectoryOrCreate`, so a down NFS mount fails the pod
loudly instead of silently writing output to the node's local disk. The DAG SHALL use
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

#### Scenario: hostPath volumes fail loudly on a down NFS mount

- **WHEN** the Workflow's `volumes` are inspected
- **THEN** `images-input-dir`, `predictions-output-dir`, and `traits-output-dir` all declare
  `hostPath.type: Directory`
- **AND** none of the three declares `type: DirectoryOrCreate`

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

#### Scenario: Launcher's TEMPLATES list contains every workflow template

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all five template files: the images-downloader,
  predictor, trait-extractor, write-back, and exit-gate templates

## ADDED Requirements

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

The template SHALL declare an explicit `priorityClassName`, since an Argo pod with none lands at
very-high priority on this cluster — above the predictor's own class. It SHALL declare a
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

The two `bloomctl` stages already consume it. The `predictor` and `trait-extractor` stages do not
consume it yet, and it is inert for them today; it is required because the stage directories are
fixed, shared `hostPath`s and `run_manifest.json` accumulates `scan_keys` across every run that
writes into them. Once a producer stage can be reached after an upstream failure, the manifest a
stage is scoped by may belong to a different run, and a stage has no way to detect that without
knowing its own workflow identity. Carrying it is the prerequisite for any run-scope validation.

#### Scenario: All four batch-processing templates carry ARGO_WORKFLOW_NAME

- **WHEN** the images-downloader, predictor, trait-extractor and write-back templates are inspected
- **THEN** each declares an `ARGO_WORKFLOW_NAME` entry in its container `env:`
- **AND** each such entry's `value` is exactly `"{{workflow.name}}"`
