# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit (no pytest, no local WSL2 dry-run — GPU fractions are a RunAI-scheduler concept with no
local Docker Desktop equivalent, and the local variant is out of scope for this change). Full
rationale in `design.md` and `docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`.

**Commit shape**: this change produces one code commit (§1's manifest edit, lint-clean before
committing) plus one small close-out commit recording validation evidence and doc updates (§§2-8).
Sections 2-8 are cluster-side validation and doc follow-through with no manifest diff — their
checkboxes don't each need their own commit. Amend §1's commit freely while iterating through live
validation (branch is unpushed, no PR yet).

## 1. Predictor template edit

- [ ] 1.1 Edit `sleap-roots-predictor-template.yaml`: remove **only** the `gpu-fraction: "0.5"`
  line from the object-level `metadata.annotations` block (leave the sibling `preemptible: "true"`
  annotation in that same block untouched — it's out of scope). Add `gpu-memory: "8192"` under a
  new `spec.templates[predictor].metadata.annotations` block (pod-level). Remove
  `resources.limits.nvidia.com/gpu: 1`. Remove `privileged: true` and `runAsUser: 0` from
  `securityContext` (delete the whole `securityContext` block — nothing else populates it).
  Replace the stale `# gpu-fraction "0.5" has no effect today...` comment with a note that the
  pod-level `gpu-memory` annotation is now authoritative, referencing issue #25. See `design.md`
  for the full rationale — don't re-derive it in the file comment, just reference it.
- [ ] 1.2 Inspect the edited file (`grep`/manual read): confirm `gpu-memory: "8192"` appears under
  `spec.templates[0].metadata.annotations`, confirm no `gpu-fraction` or `nvidia.com/gpu` string
  appears anywhere in the file, confirm no `privileged`/`runAsUser` keys remain, confirm
  `preemptible: "true"` is still present in the object-level annotations. Also spot-check the
  fields this edit does NOT touch (image tag, `args`, `WANDB_API_KEY` `secretKeyRef`, no
  models-input mount, `retryStrategy`, `priorityClassName`) are unchanged — closes the
  "Predictor template uses the GHCR predict image..." scenario, which this change doesn't modify
  but should still be confirmed intact.

## 2. Static validation

- [ ] 2.1 `argo lint --offline sleap-roots-predictor-template.yaml` (via WSL, per the `runai`
  skill) → expect no errors (standalone `WorkflowTemplate`, no `templateRef` cross-resolution to
  worry about).

## 3. Live validation (real cluster, closes issue #25's acceptance criteria)

- [ ] 3.1 Register the updated template on the cluster (`argo template create`/`update` against
  `runai-talmo-lab`).
- [ ] 3.2 Submit a real predictor run and inspect the resulting pod's manifest
  (`kubectl get pod <name> -o yaml`): confirm `annotations` contains `gpu-memory: "8192"`, confirm
  no `nvidia.com/gpu` under `resources.limits`/`resources.requests`, confirm
  `schedulerName: runai-scheduler` is present. This is the one part of this change that static
  review can't verify (annotation-only GPU placement depends entirely on RunAI's scheduler
  intercepting it) — do not skip.
- [ ] 3.3 Confirm the run completes successfully (valid output for its scans) using the shared,
  already-writable `a4_poc` output path (this reuses the existing validated path).
- [ ] 3.4 **Cold-path permission test**: submit a second run against a brand-new, never-before-
  written output directory (not the shared `a4_poc` path) to actually exercise the risk this repo
  already documents by name for `images-downloader` — a `DirectoryOrCreate` hostPath created
  root-owned by kubelet, written by a non-root container. Confirm the write succeeds; if it fails
  with permission-denied, that's a real finding to resolve before relying on non-root writes to
  fresh paths generally (not blocking this change's merge if `images-downloader`'s existing
  behavior is the same, but must be recorded either way).

## 4. Concurrent co-scheduling validation (real cluster; closes issue #25's second acceptance criterion)

- [ ] 4.1 **Tenant-safety pre-flight**: before submitting, confirm which GPU node/card has free
  headroom for two 8192 MiB reservations without landing on a card already hosting another
  tenant's live session (`runai node list`, `nvidia-smi` on candidate nodes). Prefer `talmo-lab`
  for this test unless `busch-lab` capacity is confirmed free — both projects are documented
  elsewhere in this change as heavily/fully allocated by pre-existing, unrelated workloads.
- [ ] 4.2 Submit 2 fractional predictor pods concurrently via `argo submit` against the
  now-registered template (using distinct `scan-ids` via the full pipeline, or two direct
  `argo submit --from workflowtemplate/sleap-roots-predictor-template` calls) targeting the node
  identified in 4.1. Do not use an ad-hoc `runai workspace submit` flag for this — no
  `--gpu-memory-request`-equivalent flag is documented anywhere in `.claude/skills/runai/SKILL.md`;
  submitting against the already-registered, already-verified template is both more representative
  and avoids relying on an unconfirmed CLI flag.
- [ ] 4.3 While both run, poll `nvidia-smi` (via `kubectl exec`) to confirm combined memory usage
  stays within the card's capacity and neither pod OOMs or gets killed — and confirm no pre-existing
  tenant session on that card was disrupted.
- [ ] 4.4 Confirm both pods complete successfully.

## 5. Full DAG end-to-end validation (real cluster)

- [ ] 5.1 Submit the full four-stage `sleap-roots-pipeline.yaml` DAG with the updated predictor
  template registered, using a real `scan-ids` set. Confirm all four stages complete successfully.
  If the run fails specifically at `trait-extractor` with a `privileged`-related admission error,
  that's evidence of a pre-existing issue this change's research surfaced (cluster policy now
  broadly rejects `privileged`, and `trait-extractor`'s template still sets it) — record and file
  separately, it is not a regression caused by this change.

## 6. Preemption/retry interaction check

- [ ] 6.1 (static) Inspect the file: confirm `priorityClassName: interactive-preemptible` and
  `retryStrategy` (limit 3, backoff 2m factor 2) fields are byte-identical before/after this edit
  (this change only touches `metadata.annotations`, `resources.limits`, and `securityContext`).
- [ ] 6.2 (live cluster) After the template is re-registered, confirm a submitted pod still carries
  `priorityClassName: interactive-preemptible`. A real forced-eviction-and-retry observation is a
  stretch goal, not required to close this task — if not exercised, note explicitly in the PR that
  live eviction/retry under the fractional shape remains unverified, matching the pre-existing
  caveat already in the templates' own comments about eviction risk.
- [ ] 6.3 Note in the PR (not a code fix): if a Workflow is retrying (per `retryStrategy limit: 3`)
  at the moment the template is updated on the cluster, the retry could resolve to the new
  non-root template while a root-owned partial file from a prior (old-template) attempt still sits
  in the shared output path — a non-root process may lack permission to overwrite it. Low
  probability for a controlled first rollout; not fixed by this change, just flagged so it isn't
  rediscovered as a surprise later (see `design.md`'s Risks section).

## 7. Documentation follow-through

- [ ] 7.1 Update `openspec/project.md`'s Tech Stack line ("fractional GPU via `gpu-fraction`") to
  reference `gpu-memory` instead.
- [ ] 7.2 Update `README.md`'s "Run:AI-Specific Configuration in WorkflowTemplates" and "GPU
  Support" sections to reflect the `gpu-memory` pod-level annotation shape instead of
  `gpu-fraction` + `nvidia.com/gpu`.
- [ ] 7.3 Update `.claude/skills/runai/SKILL.md` §4 and §6 (drop the "predictor template pins
  `gpu-fraction` + `nvidia.com/gpu`" note; update the fractional-GPU flag guidance once/if an
  absolute-memory CLI flag is confirmed to exist — do not invent one; if none exists, say so
  explicitly rather than guessing).
- [ ] 7.4 Append a dated `docs/bloom-integration/roadmap.md` status-log entry closing out issue
  #25, per this repo's established per-merge logging convention (it's referenced twice there
  already as filed/open).

## 8. Validate + close out

- [ ] 8.1 `openspec validate enable-predictor-gpu-fractions --strict` → must be valid.
- [ ] 8.2 If any manifest edit happened after §2.1's lint (e.g., tuning `8192` based on §3/§4
  findings), re-lint; otherwise this is a no-op and doesn't need repeating.
- [ ] 8.3 `/pr-description`; open PR referencing issue #25 and this change-id. Paste the live
  evidence from §3.2 (pod YAML annotation slice) and §4.3 (`nvidia-smi` trace) directly into the
  PR body — a reviewer can't reproduce live-cluster runs themselves. Note the local-WSL2 predictor
  variant is deliberately untouched, that trait-extractor's `privileged`/`runAsUser` TODO is now
  confirmed-droppable by this change's findings but is a separate out-of-scope follow-up, and that
  `runai_run_pipeline.sh`'s documented manual re-registration alternative (`argo template update`
  run by hand) has no enforced ordering against `argo submit` — forgetting it silently serves the
  stale template. Not fixed by this change (launcher script behavior is out of scope), just
  flagged for whoever runs the manual path next.
