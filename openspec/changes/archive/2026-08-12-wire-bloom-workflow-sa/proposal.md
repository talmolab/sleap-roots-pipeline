## Why

Bloom's step pods need `workflowtaskresults create/patch` RBAC to report results back to Argo, or
every DAG step fails with `workflowtaskresults.argoproj.io is forbidden`. The cluster admin
created a dedicated `bloom-workflow` ServiceAccount for exactly this (separate from
`bloom-pipeline`, which is what Bloom's backend authenticates as to *submit* Workflows) and
confirmed it in both `runai-talmo-lab` and `runai-busch-lab` — the fix on our side is one line.

Separately, the cluster admin flagged a real, previously-only-theoretical storage risk: this
repo's three `hostPath` volumes use `type: DirectoryOrCreate`, which silently creates a local
directory on a node's root disk if the shared NFS mount happens to be down on whichever node a
step lands on — output vanishes, with a successful-looking pipeline result on top. `type:
Directory` fails loudly instead. All three directories already exist and have been in continuous
use throughout this program, so there is no cold-start case left to protect against by staying on
`DirectoryOrCreate`.

## What Changes

- Add `spec.serviceAccountName: bloom-workflow` to `sleap-roots-pipeline.yaml` (Workflow-level —
  applies to all four steps, since none of them set their own `serviceAccountName`).
- Change all three `hostPath` volumes (`images-input-dir`, `predictions-output-dir`,
  `traits-output-dir`) from `type: DirectoryOrCreate` to `type: Directory`.

**BREAKING**: none. The ServiceAccount addition only grants permissions that were previously
missing (steps were failing without it, not succeeding differently); the hostPath type change
only affects behavior on a node where the NFS mount is actually down, which is exactly the
scenario it's meant to fail loudly on instead of silently corrupting output.

## Impact

- **Modified capability:** `per-batch-pipeline` — the "Four-stage per-batch DAG" requirement gets
  a MODIFIED delta adding `serviceAccountName` and hostPath-type assertions.
- **Affected code:** `sleap-roots-pipeline.yaml` only.
- **Untouched:** all four `*-template.yaml` files, `runai_run_pipeline.sh`, all `local-WSL2-*`
  files (the local dev Workflow doesn't reference `bloom-workflow`, and its own hostPath mounts
  are a separate Docker-Desktop-specific concern).
- **External prerequisites:** `bloom-workflow` ServiceAccount must exist in whichever namespace
  this Workflow is submitted into — confirmed present in both `runai-talmo-lab` and
  `runai-busch-lab` as of 2026-08-06 (cluster admin, smoke-tested end-to-end).
