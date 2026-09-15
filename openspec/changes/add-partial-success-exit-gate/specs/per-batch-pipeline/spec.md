## RENAMED Requirements

- FROM: `### Requirement: Four-stage per-batch DAG`
- TO: `### Requirement: Per-batch DAG with a terminal exit-code gate`

- FROM: `### Requirement: Launcher registers all four templates`
- TO: `### Requirement: Launcher registers every stage template`

## MODIFIED Requirements

### Requirement: Per-batch DAG with a terminal exit-code gate

The pipeline Workflow SHALL define a five-task DAG: four processing stages — `images-downloader`
(root) → `predictor` → `trait-extractor` → `write-back` — followed by a terminal `exit-gate` task
depending on `write-back`. Each task SHALL depend on the one before it, and `exit-gate` SHALL be
the DAG's only leaf, so the Workflow's final phase is determined by the gate rather than by any
stage's own node phase. The Workflow SHALL declare a `scan-ids` argument parameter that
`images-downloader` consumes, so the batch a run processes is a caller-supplied input rather than a
hardcoded scan. The Workflow SHALL set `spec.serviceAccountName: bloom-workflow` so every step's
pod can report its results back to Argo. Its `hostPath` volumes SHALL use `type: Directory`, not
`type: DirectoryOrCreate`, so a down NFS mount fails the pod loudly instead of silently writing
output to the node's local disk. The DAG SHALL use `dependencies:`, never `depends:`, since the
latter is all-or-nothing per DAG template and would forbid `continueOn` on every task in it.
Because this file is the only canonical, correctly-complete definition of this Workflow's shape —
and is independently reconstructed programmatically elsewhere (`salk-bloom`'s dispatch worker) with
no built-in mechanism to detect drift between the two — the file SHALL carry a header comment
stating plainly that it is vendored (pinned to a commit SHA, CI-checked for drift) by `salk-bloom`
for programmatic dispatch, so an editor of its `volumes`/`entrypoint`/`serviceAccountName`/DAG
structure is warned at the point of editing rather than discovering the drift only when a real
batch dispatch fails.

#### Scenario: Workflow runs all four stages in order, then the gate

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** its DAG has exactly five tasks: `images-downloader`, `predictor`, `trait-extractor`,
  `write-back`, `exit-gate`
- **AND** `predictor` lists `images-downloader` in its `dependencies`
- **AND** `trait-extractor` lists `predictor` in its `dependencies`
- **AND** `write-back` lists `trait-extractor` in its `dependencies`
- **AND** `exit-gate` lists `write-back` in its `dependencies`
- **AND** no task lists `exit-gate` in its `dependencies`, so the gate is the DAG's only leaf
- **AND** the Workflow declares a `scan-ids` entry under `arguments.parameters`

#### Scenario: DAG uses dependencies, not depends

- **WHEN** the Workflow's DAG tasks are inspected
- **THEN** no task declares a `depends` field
- **AND** every task with a predecessor declares `dependencies`

#### Scenario: Workflow sets bloom-workflow as its ServiceAccount

- **WHEN** the Workflow (`sleap-roots-pipeline.yaml`) is inspected
- **THEN** `spec.serviceAccountName` is `bloom-workflow`
- **AND** none of the five stage templates override `serviceAccountName` at the template level

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

### Requirement: Launcher registers every stage template

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, `write-back`, and `exit-gate` templates.

#### Scenario: Launcher's TEMPLATES list contains every stage template

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
death), and the DAG must stop rather than continue on data that was never produced.

`continueOn` SHALL be declared on the failing task itself, never on a downstream task, since Argo
applies it to that task's dependents and placing it downstream both fails to have the intended
effect and triggers a known upstream defect.

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

### Requirement: An exit-code gate determines the Workflow's final phase

The DAG SHALL include a terminal `exit-gate` task, backed by
`sleap-roots-exit-gate-template.yaml`, which receives each producer's real exit code and exits
non-zero unless every one of them is either `0` (all scans succeeded) or the partial-success code
`3`. Because `continueOn` keys only on a node's phase and cannot read exit codes, without this gate
an exhausted-retry crash would be indistinguishable from a partial success and would report the
Workflow `Succeeded`.

The gate SHALL receive the exit codes as template arguments and perform the comparison inside its
container. It SHALL NOT use a `when:` expression for this, because `when:` is evaluated by
govaluate rather than expr — so integer-coercion helpers are unavailable and a mixed
string/number comparison is a parse error — and because an unresolvable task reference in `when:`
causes the controller to requeue the task indefinitely rather than fail it.

Because the gate references producer tasks that are not its direct dependencies, and such
references resolve only via a task's ancestors, every referenced producer SHALL remain an ancestor
of the gate. Restructuring the DAG such that a referenced producer is no longer an ancestor would
cause the Workflow to hang on an unresolvable reference rather than fail.

#### Scenario: Gate accepts success and partial success

- **WHEN** every producer exits either `0` or `3`
- **THEN** the `exit-gate` task exits `0`
- **AND** the Workflow's final phase is `Succeeded`

#### Scenario: Gate rejects a crash-class exit

- **WHEN** any producer exits with a code other than `0` or `3` after exhausting its retries — for
  example `1` (crash), `2` (usage error) or `143` (`SIGTERM`)
- **THEN** the `exit-gate` task exits non-zero
- **AND** the Workflow's final phase is `Failed`

#### Scenario: Gate reads the last attempt's code through a retry node

- **WHEN** a producer task carries a `retryStrategy` and its final attempt exits with a given code
- **THEN** the value the gate receives for that producer is that final attempt's exit code, not an
  empty string

#### Scenario: Gate receives codes as arguments, not via a when expression

- **WHEN** the `exit-gate` DAG task is inspected
- **THEN** it passes the producers' `exitCode` values via `arguments.parameters`
- **AND** it declares no `when` field

#### Scenario: A stage that never ran stops the DAG

- **WHEN** a producer's pod fails to start at all, producing an `Error` rather than a `Failed` node
- **THEN** the DAG does not proceed past that stage
- **AND** the Workflow's final phase is not `Succeeded`
