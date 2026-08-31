## 1. Add the guardrail comment

- [x] 1.1 Add a header comment block to `sleap-roots-pipeline.yaml` (above the existing
  `apiVersion`/`kind`/`metadata`, alongside the file's existing reference-link comments) stating:
  this file is vendored by `salk-bloom` at `services/workflows/vendored/sleap-roots-pipeline.yaml`,
  pinned to a commit SHA recorded in a sibling `SLEAP_ROOTS_PIPELINE_REF` file, and CI there
  diffs the vendored copy against this file at that pinned ref on every PR; changing `volumes`,
  `entrypoint`, `serviceAccountName`, or the DAG structure here requires updating the vendored
  copy and bumping the pin, or that repo's CI will fail.
- [x] 1.2 Validate: `argo lint sleap-roots-pipeline.yaml` still passes (comment-only change, but
  confirm nothing was accidentally broken in the YAML structure). — `no linting errors found!`

## 2. Cross-link

- [x] 2.1 Confirm [bloom #737](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/737)
  references this change/design doc for the companion `salk-bloom`-side implementation. — already
  referenced bloom #737 in its own body when filed.

## 3. Validate and merge

- [ ] 3.1 `openspec validate add-shared-workflow-source-guardrail --strict` passes.
- [ ] 3.2 PR opened, referencing this change-id and bloom #737.
