## MODIFIED Requirements

### Requirement: Four-stage per-batch DAG

The pipeline Workflow SHALL define a four-task DAG: `images-downloader` (root) → `predictor` →
`trait-extractor` → `write-back`, with each stage depending on the one before it. The Workflow
SHALL declare a `scan-ids` argument parameter that `images-downloader` consumes, so the batch a run
processes is a caller-supplied input rather than a hardcoded scan. The Workflow SHALL set
`spec.serviceAccountName: bloom-workflow` so every step's pod can report its results back to Argo.
Its `hostPath` volumes SHALL use `type: Directory`, not `type: DirectoryOrCreate`, so a down NFS
mount fails the pod loudly instead of silently writing output to the node's local disk. Because
this file is the only canonical, correctly-complete definition of this Workflow's shape — and is
independently reconstructed programmatically elsewhere (`salk-bloom`'s dispatch worker) with no
built-in mechanism to detect drift between the two — the file SHALL carry a header comment stating
plainly that it is vendored (pinned to a commit SHA, CI-checked for drift) by `salk-bloom` for
programmatic dispatch, so an editor of its `volumes`/`entrypoint`/`serviceAccountName`/DAG
structure is warned at the point of editing rather than discovering the drift only when a real
batch dispatch fails.

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

#### Scenario: File carries a cross-repo vendoring guardrail

- **WHEN** `sleap-roots-pipeline.yaml` is inspected
- **THEN** its header comments name `salk-bloom` as vendoring a pinned copy of this file for
  programmatic dispatch
- **AND** the comment names the drift-check mechanism (a CI check comparing the vendored copy
  against this file at the pinned commit)
- **AND** the comment states that changing this file's `volumes`, `entrypoint`,
  `serviceAccountName`, or DAG structure requires updating the vendored copy and its pinned
  reference in `salk-bloom`
