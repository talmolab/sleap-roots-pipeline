# Tasks

Declarative repo — a task's "test" is `argo lint`, a manifest-field inspection, or a real cluster
submit (no pytest, no local WSL2 dry-run — GPU fractions are a RunAI-scheduler concept with no
local Docker Desktop equivalent, and the local variant is out of scope for this change). Full
rationale in `design.md` and `docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`.

**Commit shape**: originally planned as 1-2 commits (manifest edit + close-out). In practice this
grew to several as the OpenSpec proposal itself went through a 5-agent adversarial review (before
implementation) and the resulting PR #41 went through a second 5-agent review (after
implementation) — each review round's fixes landed as their own commit rather than amending
history once the branch was pushed/PR opened. Reconciling this note rather than leaving the
original "1-2 commits" plan stale (per PR #41 review).

## 1. Predictor template edit

- [x] 1.1 Edit `sleap-roots-predictor-template.yaml`: remove **only** the `gpu-fraction: "0.5"`
  line from the object-level `metadata.annotations` block (leave the sibling `preemptible: "true"`
  annotation in that same block untouched — it's out of scope). Add `gpu-memory: "8192"` under a
  new `spec.templates[predictor].metadata.annotations` block (pod-level). Remove
  `resources.limits.nvidia.com/gpu: 1`. Remove `privileged: true` and `runAsUser: 0` from
  `securityContext` (delete the whole `securityContext` block — nothing else populates it).
  Replace the stale `# gpu-fraction "0.5" has no effect today...` comment with a note that the
  pod-level `gpu-memory` annotation is now authoritative, referencing issue #25. See `design.md`
  for the full rationale — don't re-derive it in the file comment, just reference it.
- [x] 1.2 Inspect the edited file (`grep`/manual read): confirm `gpu-memory: "8192"` appears under
  `spec.templates[0].metadata.annotations`, confirm no `gpu-fraction` or `nvidia.com/gpu` string
  appears anywhere in the file, confirm no `privileged`/`runAsUser` keys remain, confirm
  `preemptible: "true"` is still present in the object-level annotations. Also spot-check the
  fields this edit does NOT touch (image tag, `args`, `WANDB_API_KEY` `secretKeyRef`, no
  models-input mount, `retryStrategy`, `priorityClassName`) are unchanged — closes the
  "Predictor template uses the GHCR predict image..." scenario, which this change doesn't modify
  but should still be confirmed intact.
- [x] 1.3 **Added per PR #41 review**: set `spec.templates[predictor].schedulerName:
  runai-scheduler` explicitly. Live testing (§3.2) already confirmed this lands automatically in
  `runai-talmo-lab` — this is defense-in-depth against future cluster/namespace config drift, not
  a fix for an observed problem. Re-lint after this addition (§2.1).

## 2. Static validation

- [x] 2.1 `argo lint --offline sleap-roots-predictor-template.yaml` (via WSL, per the `runai`
  skill) → expect no errors (standalone `WorkflowTemplate`, no `templateRef` cross-resolution to
  worry about).

## 3. Live validation (real cluster, closes issue #25's acceptance criteria)

- [x] 3.1 Registered on `runai-talmo-lab` (`argo template update`, generation bumped to 6).
  Confirmed via `argo template get -o yaml`: predictor template now shows
  `annotations: {gpu-memory: "8192"}` at the per-template metadata, object-level annotations show
  only `preemptible: "true"`.
- [x] 3.2 Submitted `sleap-roots-pipeline-m7mjp` (full pipeline, `scan-ids=289,577,1009`).
  `kubectl get pod sleap-roots-pipeline-m7mjp-predictor-4092641486 -o yaml` confirms: pod
  annotations include `gpu-memory: "8192"`, `received-resource-type: Fraction`,
  `runai-podgroup-requested-gpus-memory: "8192"` (RunAI's own accounting matches exactly);
  `schedulerName: runai-scheduler` present; `resources.limits`/`requests` have no
  `nvidia.com/gpu`; no `privileged`/`runAsUser` anywhere in the pod spec. All acceptance
  criteria confirmed on a real pod.
- [x] 3.3 Run succeeded (`Status: Succeeded`, all 4 stages `Completed`, 0 restarts). Predictor log:
  clean skip-if-done (`0 ok, 3 skipped, 0 failed`, exit nil) against the existing shared path —
  proves the new manifest shape doesn't regress existing behavior.
- [x] 3.4 **Cold-path permission test**: submitted a standalone ad-hoc Workflow (not committed —
  throwaway, deleted after) targeting a brand-new, never-before-written output directory. Forced a
  real (non-skipped) inference run. Result: **write succeeded** — `scan_1009`/`scan_289`/`scan_577`
  prediction files were created in the freshly kubelet-created directory (mounted `0777` on this
  NFS config, not the restrictive mode the theoretical risk assumed). The cold-path permission risk
  does not materialize on this cluster's actual NFS mount. Test artifacts cleaned up.
- [x] 3.5 **Warm-path permission test (added per PR #41 review — 3 of 5 reviewers independently
  flagged this gap).** §3.3 and §3.4 both left a real risk untested: §3.3's run against the real
  `a4_poc/predictions` path hit skip-if-done for all 3 scans (zero actual writes attempted there
  under the new non-root context); §3.4's cold-path test used a brand-new `DirectoryOrCreate`
  directory, not a directory that already existed before this change. Neither exercised "a
  non-root process creating new files inside a pre-existing directory tree originally populated
  by the old `runAsUser: 0` predictor" — the exact scenario the real next production run will hit
  the first time it processes a not-yet-done scan under the real shared path.
  **Test definition (written before running, per TDD):** backed up, then deleted, the 4 prediction
  files inside the pre-existing `a4_poc/predictions/scan_1009/` directory (leaving the directory
  itself, created 2026-07-29 under the old root-owned predictor, untouched) so skip-if-done
  couldn't short-circuit; resubmitted the real production `sleap-roots-pipeline.yaml` with
  `scan-ids=1009` against the unmodified, real shared path (not an ad-hoc test workflow). **Pass**
  = predictor log shows `N ok, ... skipped, 0 failed` and fresh files appear in `scan_1009/` with
  the new run's timestamp. **Fail** = a permission-denied error in the predictor's logs, or the
  job errors out.
  **Result: PASS.** `sleap-roots-pipeline-sk8p9`, predictor step (`sleap-roots-pipeline-sk8p9-predictor-3457220062`,
  2m duration — genuine inference, not a skip): log shows `Batch complete: 1 ok, 2 skipped, 0
  failed` (scan_1009 reprocessed for real — 72 frames, 168 instances detected; scan_289/577
  correctly skipped since their files were untouched). `ls -la --time-style=full-iso` on
  `scan_1009/` confirms 4 files with the new run's timestamp (`2026-08-05 12:08:35`) while the
  directory itself (`.`/`..`) still shows its original `2026-07-29 21:02:42` creation time — proof
  the non-root process wrote successfully into a directory root created seven days earlier. No
  permission error anywhere in the log. `trait-extractor` also succeeded reading the fresh output
  (12s). `write-back` failed on this same run, but for a reason entirely unrelated to this PR: its
  content-addressed blob store correctly refused to overwrite `scan_1009`'s already-ingested blob
  with a different checksum (deliberately re-running inference produces slightly different, still
  valid, numeric output) — expected behavior given this test intentionally reprocessed
  already-ingested data, not a defect. Test workflow and original `scan_1009` files
  (restored from backup, byte-identical to originals) both cleaned up.

## 4. Concurrent co-scheduling validation (real cluster; closes issue #25's second acceptance criterion)

- [x] 4.1 **Tenant-safety pre-flight**: surveyed `kubectl get pods -n runai-talmo-lab -o wide` and
  `kubectl describe node` across the 16 GPU nodes (4 physical GPUs each, talmo-lab quota 20).
  `talmo-lab` had ample lightly-loaded nodes (most running 1-2 single-GPU jobs out of 4); confirmed
  `gpu-node2` had 5% CPU / 2% memory allocated despite `nvidia.com/gpu: 4/4` already claimed by
  other (non-fractional) tenants — RunAI's fraction mechanism tracks GPU-memory separately from
  that counter, so this didn't block scheduling. Used `talmo-lab` (busch-lab not needed for this
  test).
- [x] 4.2 Submitted two standalone ad-hoc Workflows (not committed — throwaway, deleted after),
  each with `templateRef` to the now-registered predictor template and its own fresh output
  directory (real overlapping inference, not skip-if-done). First attempt let RunAI's scheduler
  place them independently (landed on 2 different nodes — instructive but not what this task
  needs); redirected the second pod via `nodeSelector: {kubernetes.io/hostname: gpu-node2}` to
  force genuine co-location with the first. Used `argo submit` against the registered template
  rather than an ad-hoc `runai workspace submit` flag — at the time this ran, no
  node/GPU-co-location flag was confirmed to exist for `workspace submit` (note: `--gpu-memory-request`
  itself was later verified real in §7.3 — that's a *sizing* flag, not a co-location one; no
  equivalent to force two ad-hoc jobs onto the same physical device was found).
- [x] 4.3 `kubectl exec`/`nvidia-smi` was not available (this identity lacks `pods/exec` RBAC for
  ad-hoc Argo-submitted pods — `runai workspace exec` manages its own separate auth layer per the
  `runai` skill, and doesn't apply here). Confirmed co-scheduling a different way instead: both
  pods' `kubectl get pod -o yaml` show the **identical `runai-gpu-group` UUID**
  (`2f254411-445d-40de-83bf-328add9dbb8e`) — **strong evidence** RunAI assigned both to the same
  physical GPU, not just the same node (per PR #41 review: no RunAI doc is cited anywhere in this
  change defining exactly what `runai-gpu-group` encodes, so this is strong corroborating evidence
  rather than a documented guarantee — flagged as a follow-up to find/cite the authoritative
  definition, not something this change can close on its own). No pre-existing tenant session on
  `gpu-node2` was disrupted (checked before/after: same jobs, same status).
- [x] 4.4 Both completed successfully (`Succeeded`, real inference output in each pod's separate
  output directory, no truncation/errors in logs) while genuinely overlapping in execution time on
  the same physical GPU. Neither OOMed. Test artifacts (workflows, throwaway directories) deleted.

## 5. Full DAG end-to-end validation (real cluster)

- [x] 5.1 Covered by the same `sleap-roots-pipeline-m7mjp` run as 3.2/3.3: all four stages
  (`images-downloader`, `predictor`, `trait-extractor`, `write-back`) show `Completed`, 0 restarts,
  overall `Status: Succeeded`. `trait-extractor` did **not** hit a `privileged`-related admission
  error — so the "is trait-extractor already broken by the broader admission policy" open question
  from `design.md` is resolved: it isn't, at least not today, on this namespace/cluster
  configuration. Worth noting for a future trait-extractor `privileged`-removal follow-up, not a
  blocker for anything here.

## 6. Preemption/retry interaction check

- [x] 6.1 (static) Confirmed via diff: this edit only touched `metadata.annotations`,
  `resources.limits`, and `securityContext` — `priorityClassName`/`retryStrategy` lines untouched.
- [x] 6.2a (live cluster, field presence only) Confirmed on the live
  `sleap-roots-pipeline-m7mjp-predictor` pod: both `priorityClassName: interactive-preemptible`
  and the full `retryStrategy` (`limit:3, retryPolicy:Always, backoff:{duration:2m,factor:2}`) are
  present, unchanged, and correctly propagated through the re-registered template.
- [ ] 6.2b (live cluster, actual interaction — NOT exercised, per PR #41 review) A real
  forced-eviction-and-retry observation under the fractional `gpu-memory` shape was not run. This
  section's own title ("interaction check") oversells 6.2a alone — field presence is confirmed,
  but whether eviction+retry actually behaves correctly under the new annotation-only scheduling
  remains unverified. Stretch goal, not required to close this change, but left honestly
  unchecked rather than folded into 6.2a's checkmark.
- [x] 6.3 Note in the PR (not a code fix) — **mechanism corrected, this entry previously stated
  the wrong one (caught by a targeted post-review verification pass, not the original 5-agent
  review).** If a Workflow is retrying (per `retryStrategy limit: 3`) at the moment the template
  is updated on the cluster, the retry does NOT hit a permission-denied-on-overwrite error — the
  predictor's own `retryStrategy` comment states skip-if-done is existence-only, so a retry that
  finds a file already exists (even truncated/corrupt, root- or non-root-authored) just *skips*
  it, never attempting to overwrite it. The real risk is the pre-existing one this repo already
  tracks separately (predict #26 / sleap-roots #259: existence-only skip + non-atomic write can
  trust a truncated file as "done") — this change doesn't introduce a new failure mode, it just
  means that pre-existing risk's next occurrence could involve a mix of root- and
  non-root-authored files. Low probability for a controlled first rollout; not fixed by this
  change, just flagged so it isn't rediscovered as a surprise later (see `design.md`'s Risks
  section, which has the same correction).

## 7. Documentation follow-through

- [x] 7.1 Updated `openspec/project.md`'s Tech Stack line to describe the pod-level `gpu-memory`
  annotation and the object-vs-pod-level metadata distinction that caused #25.
- [x] 7.2 Updated `README.md`'s "GPU Support" (clarified local-WSL2 vs. cluster now differ) and
  "Run:AI-Specific Configuration in WorkflowTemplates" (rewrote to show the pod-level `gpu-memory`
  annotation, explained the annotation-placement root cause of #25, corrected the false
  "Run:AI combines this with gpu-fraction" claim).
- [x] 7.3 Updated `.claude/skills/runai/SKILL.md` §4 and §6. Verified `--gpu-memory-request`
  against the live `runai workspace submit --help` output — it's a real, documented CLI flag
  (format `1G`/`500M`), not invented; added it to the resource-flags table and the §6 worked
  example (`--gpu-portion-request 0.5` → `--gpu-memory-request 8G`). Dropped the stale
  "gpu-fraction + nvidia.com/gpu, annotation governs" note.
- [x] 7.4 Appended a 2026-08-05 status-log entry to `docs/bloom-integration/roadmap.md` closing
  #25, with the live-cluster evidence (pod inspection, `runai-gpu-group` UUID match, cold-path
  test) summarized inline.

## 8. Validate + close out

- [x] 8.1 `openspec validate enable-predictor-gpu-fractions --strict` → valid.
- [x] 8.2 No manifest edit happened after §2.1's lint (§3/§4 findings didn't require tuning
  `8192`) — re-ran anyway to confirm: still clean, no-op as expected.
- [x] 8.3 `/pr-description` generated; PR #41 opened
  (https://github.com/talmolab/sleap-roots-pipeline/pull/41), referencing issue #25 and this
  change-id. Pasted the live evidence from §3.2 (pod YAML annotation slice) directly into the PR
  body; corrected the instruction to paste an `nvidia-smi` trace from §4.3 — that command was
  unavailable (see §4.3), the actual evidence used was the `runai-gpu-group` UUID match, which is
  what the PR body contains. Note the local-WSL2 predictor
  variant is deliberately untouched, that trait-extractor's `privileged`/`runAsUser` TODO is now
  confirmed-droppable by this change's findings but is a separate out-of-scope follow-up, and that
  `runai_run_pipeline.sh`'s documented manual re-registration alternative (`argo template update`
  run by hand) has no enforced ordering against `argo submit` — forgetting it silently serves the
  stale template. Not fixed by this change (launcher script behavior is out of scope), just
  flagged for whoever runs the manual path next.
