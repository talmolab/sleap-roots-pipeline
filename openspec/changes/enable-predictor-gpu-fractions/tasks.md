# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit (no pytest, no local WSL2 dry-run — GPU fractions are a RunAI-scheduler concept with no
local Docker Desktop equivalent, and the local variant is out of scope for this change). Full
rationale in `docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`.

## 1. Predictor template edit

- [ ] 1.1 Edit `sleap-roots-predictor-template.yaml`: move `gpu-fraction: "0.25"` from the
  WorkflowTemplate's object-level `metadata.annotations` (currently lines 10-12, alongside
  `preemptible: "true"`) to `spec.templates[predictor].metadata.annotations` (new, pod-level).
  Remove `resources.limits.nvidia.com/gpu: 1`. Remove `privileged: true` and `runAsUser: 0` from
  `securityContext` (delete the whole `securityContext` block if nothing else populates it).
  Replace the stale `# gpu-fraction "0.5" has no effect today...` object-metadata comment with a
  note that the pod-level annotation is now what's authoritative, referencing issue #25.
- [ ] 1.2 Inspect the edited file (`grep`/manual read): confirm `gpu-fraction` appears under
  `spec.templates[0].metadata.annotations`, confirm no `nvidia.com/gpu` string appears anywhere in
  the file, confirm no `privileged` or `runAsUser` keys remain.

## 2. Static validation

- [ ] 2.1 `argo lint --offline sleap-roots-predictor-template.yaml` (via WSL, per the `runai`
  skill) → expect no errors (this is a standalone `WorkflowTemplate` file with no `templateRef`
  cross-resolution to worry about, unlike `sleap-roots-pipeline.yaml`).

## 3. Live single-pod validation (real cluster, closes issue #25's first acceptance criterion)

- [ ] 3.1 Register the updated template on the cluster (`argo template create`/`update` against
  `runai-talmo-lab`, via the `argo-user`/available WSL kubeconfig).
- [ ] 3.2 Submit a real predictor run (`argo submit --from workflowtemplate/sleap-roots-predictor-template`
  or via the full pipeline with a small `scan-ids` set) and inspect the resulting pod's manifest
  (`kubectl get pod <name> -o yaml`): confirm `annotations` contains `gpu-fraction: "0.25"`, confirm
  no `nvidia.com/gpu` under `resources.limits` or `resources.requests`, confirm
  `schedulerName: runai-scheduler` is present.
- [ ] 3.3 Confirm the run still completes successfully (predictor produces valid output for its
  scans) — the fractional shape must not regress correctness, only scheduling.

## 4. Concurrent co-scheduling validation (closes issue #25's second acceptance criterion)

- [ ] 4.1 Submit 2 fractional predictor pods concurrently (either two real pipeline runs with
  distinct `scan-ids`, or two ad-hoc `runai workspace submit --gpu-portion-request 0.25` jobs using
  the same image/args) targeting the same physical GPU.
- [ ] 4.2 While both run, poll `nvidia-smi` (via `runai workspace exec` or `kubectl exec`) to
  confirm combined memory usage stays within the card's capacity and neither pod OOMs or gets
  killed.
- [ ] 4.3 Confirm both complete successfully.

## 5. Full DAG end-to-end validation

- [ ] 5.1 Submit the full four-stage `sleap-roots-pipeline.yaml` DAG with the updated predictor
  template registered, using a real `scan-ids` set. Confirm all four stages (`images-downloader`,
  `predictor`, `trait-extractor`, `write-back`) complete successfully — the fractional-GPU change
  to `predictor` must not break `trait-extractor`'s downstream consumption of its output.

## 6. Preemption/retry interaction check

- [ ] 6.1 Confirm the predictor's `priorityClassName: interactive-preemptible` and
  `retryStrategy` (limit 3, backoff 2m factor 2) are unchanged by this edit (inspect the file —
  this change only touches `metadata.annotations`, `resources.limits`, and `securityContext`) and
  still present after the template is re-registered on the cluster.

## 7. Validate + close out

- [ ] 7.1 `openspec validate enable-predictor-gpu-fractions --strict` → must be valid.
- [ ] 7.2 Re-lint the changed file one final time post-edit.
- [ ] 7.3 `/pr-description`; open PR referencing issue #25 and this change-id. Note in the PR body
  that the local-WSL2 predictor variant is deliberately untouched (issue reference: known-stale,
  tracked separately), and that trait-extractor's `privileged`/`runAsUser` TODO is now confirmed
  droppable by this change's findings but is out of scope here (trait-extractor is CPU-only and
  unaffected by GPU-fraction scheduling; a separate small follow-up can apply the same
  security-context removal there if desired).
