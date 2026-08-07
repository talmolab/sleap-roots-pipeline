# Handoff — continuing the A4 K8s credential / busch-lab work (2026-08-07)

Previous session ran out of context mid-investigation. This doc is self-contained — a new
session should be able to pick up from here without the original chat history.

## Immediate next step (what we were doing when context ran out)

**Elizabeth caught a real problem: this session used `argo-user`'s kubeconfig for every cluster
operation, instead of the real `bloom-pipeline` ServiceAccount the cluster admin (Bryan) actually
created for this purpose.** `argo-user` was always a documented *temporary stopgap* (see
`docs/superpowers/specs/2026-08-03-busch-lab-rbac-investigation-design.md`) — issue #35 exists
specifically to track swapping it out once the real SA landed. It landed (confirmed by Bryan,
smoke-tested, 2026-08-05). This session never switched.

**First thing to do in the new session:**
1. Ask Elizabeth whether she's retrieved `bloom-pipeline`'s token from wherever Bryan sent it
   "out-of-band" (he was explicit: not Slack/email — some other secure channel). Checked
   `~/.kube/` in WSL at end of last session — only `kubeconfig-runai-talmo-lab.yaml` exists there
   (that's `argo-user`'s), no `bloom-pipeline` kubeconfig/token file yet.
2. Once she has it, help her construct a proper kubeconfig for `bloom-pipeline` (needs: the
   token, the CA cert, and the API URL `https://10.7.30.173:6443` — use the IP, not the hostname,
   per Bryan, the cert doesn't carry the hostname as a SAN).
3. **Important nuance to flag to her**: switching identities will NOT fix the busch-lab
   `workflowtemplates` permission gap found this session (see below) — `bloom-pipeline`'s own
   Role (`bloom-pipeline-serviceaccount.yaml`) only grants `workflowtemplates: get, list`, not
   `create`. Registering (creating) WorkflowTemplates was never something either identity should
   be able to do — that's an admin operation. Bryan's claim ("your argo-user access retains
   write there") was likely just wrong, independent of which identity is used.
4. **Re-run key validations under `bloom-pipeline`'s identity, not `argo-user`'s.** Everything
   validated so far (PR #41, PR #42) used `argo-user`, which has broader (cluster-wide,
   not-properly-scoped — see issue #34) access than `bloom-pipeline`'s intentionally-scoped Role.
   A test that passed under `argo-user` is not proof it'll pass under the actual production
   identity. At minimum, re-submit a real pipeline run using `bloom-pipeline`'s kubeconfig and
   confirm it still succeeds (workflows create/get/list/watch, workflowtemplates get/list,
   reading the `bloom-credentials`/`WANDB_API_KEY` secrets it mounts).
5. Going forward, treat `argo-user` as for ad-hoc human debugging only, not for anything meant to
   represent "does Bloom's actual submission process work."

## What's fully done this session (validated, not just claimed)

- **Issue #25 (GPU fractions) — PR #41**, `fix-gpu-fraction` branch, OPEN, not yet merged.
  - Moved predictor's GPU request from an inert object-level `gpu-fraction` annotation to a
    working pod-level `gpu-memory: "8192"` annotation (absolute MiB, not relative — sized from a
    real measured VRAM trace, ~4,676 MiB peak on a 46GB card). Removed
    `resources.limits.nvidia.com/gpu: 1`, removed `privileged`/`runAsUser: 0`.
  - Went through **two full 5-agent adversarial reviews** (proposal-stage, then PR-stage) plus a
    targeted post-review verification pass. Every finding fixed with real live-cluster evidence,
    not just softened language — including a warm-path write test (forced a real non-root write
    into a 7-day-old, previously root-owned directory) that closed the one BLOCKING finding.
  - **Cluster admin (Bryan) then confirmed our approach was correct** (his own suggested
    alternative — `spec.podMetadata.annotations` — would have deadlocked the DAG, applying the
    GPU annotation to all four steps) and confirmed the sizing math (A40s, 48305 MiB each, `8192`
    gives 5 slots/GPU not 4).
  - Bryan then **set `priorityClassName: high` (125, non-preemptible) live** on
    `runai-talmo-lab`'s registered copy of the predictor template, directly on the cluster
    (bypassing git). This session synced the repo file to match (a later commit on the same
    branch/PR) so a future `argo template update` from the repo doesn't silently revert his
    change. Rationale: trait-extractor has no skip-if-done yet (#37), so avoiding
    eviction-triggered whole-batch recomputation matters more than bursting above quota right
    now.
  - Corrected `.claude/skills/runai/SKILL.md`'s priority-tier naming: the 125 tier's real name on
    this cluster is `high`, not `inference` (an earlier wrong assumption). Added an explicit
    warning that an unset `priorityClassName` on this cluster defaults to `very-high` (150) —
    worse than either named tier, never delete the field from the other three templates.
  - `openspec validate enable-predictor-gpu-fractions --strict` passes. `argo lint` passes.

- **`bloom-workflow` SA wiring + hostPath hardening — PR #42**, `wire-bloom-workflow-sa` branch,
  OPEN, not yet merged.
  - Added `spec.serviceAccountName: bloom-workflow` to `sleap-roots-pipeline.yaml` (Workflow
    level, applies to all four steps). This is the SA the cluster admin created specifically so
    step pods can report results back to Argo (`workflowtaskresults create/patch`) — separate
    from `bloom-pipeline`, which is what Bloom's backend authenticates as to *submit* Workflows.
  - Switched all three `hostPath` volumes from `type: DirectoryOrCreate` to `type: Directory`,
    per cluster-admin guidance: `DirectoryOrCreate` silently creates a local directory on a
    node's root disk if the NFS mount is down, producing a successful-looking result with output
    that actually vanished. All three paths have existed continuously since this program's PoC,
    so there's no cold-start case left to protect.
  - **Live-cluster validated** (under `argo-user` — see "immediate next step" above about
    re-validating under `bloom-pipeline`): submitted `sleap-roots-pipeline-6ndlb`, confirmed
    `serviceAccountName: bloom-workflow` on the real predictor pod via
    `kubectl get pod ... -o jsonpath='{.spec.serviceAccountName}'`, all four stages completed
    successfully, zero `workflowtaskresults` RBAC errors.
  - `openspec validate wire-bloom-workflow-sa --strict` passes. `argo lint` passes (one expected,
    pre-existing offline-`templateRef`-resolution limitation, not a new issue).

- **Roadmap entries** — both committed directly to `main` (not the PR branches, since they're
  unrelated to either PR's specific scope):
  - 2026-08-05: cluster admin responded (supersedes "unresponsive since 2026-07-22").
  - 2026-08-06: cluster admin follow-up — GPU annotation confirmed correct, priority decision,
    real-capacity consideration surfaced (see below), attribution-labeling requirement for
    Bloom's future Phase 2 code (tracked in the `bloom trigger route` row of the A4
    change-breakdown table — **this is work "we" (Elizabeth's team) are building, not another
    team**, per her explicit correction this session).

## What's found but NOT yet resolved

- **busch-lab `workflowtemplates` create permission gap (blocks issue #40).** Attempted to
  register all four WorkflowTemplates into `runai-busch-lab` (needed before any busch-lab
  Workflow can resolve its `templateRef`s). All four failed:
  ```
  Error: ... workflowtemplates.argoproj.io is forbidden: User
  "system:serviceaccount:runai-talmo-lab:argo-user" cannot create resource "workflowtemplates"
  in API group "argoproj.io" in the namespace "runai-busch-lab"
  ```
  Confirmed directly (not just from the error text):
  ```
  $ kubectl auth can-i create workflowtemplates.argoproj.io -n runai-busch-lab   → no
  $ kubectl auth can-i create workflowtemplates.argoproj.io -n runai-talmo-lab   → yes  (control)
  ```
  This contradicts what the cluster admin told us ("The WorkflowTemplates, you can apply those,
  your argo-user access retains write there"). Filed as a comment on issue #40. **Per the
  "immediate next step" section above, switching to `bloom-pipeline`'s identity will not fix
  this** — that SA's own Role only grants `get`/`list` on `workflowtemplates`, not `create`, by
  original design (least-privilege). Worth clarifying with Bryan whether he meant something else
  (e.g., a `ClusterWorkflowTemplate`, which was the original recommendation before this session's
  "you can just apply the WorkflowTemplates" simplification) rather than assuming this is a
  simple oversight to re-request.

- **busch-lab needs two Secrets, cluster-admin-only to create**: `genericsecret-wandb-api-key`
  (referenced by the predictor template) and `genericsecret-bloom-staging-pipeline-credentials`
  (mounted by the submitted Workflow). Per Bryan: "no kubectl identity of yours can create
  secrets" — these have to be created via the RunAI console UI by him or someone with that
  access. **Decision made this session**: use the **staging** Bloom credential for busch-lab too
  (matching talmo-lab), not production — deliberately deferred, not a final answer; revisit once
  actually ready to process real Busch-lab data for keeps.

- **busch-lab GPU capacity / preemption**: busch-lab is at 2/2 of its deserved quota; one of
  those GPUs is on a node currently cordoned for maintenance. A non-preemptible run there would
  evict `linwang@salk.edu`'s active session on `gpu-node13` (confirmed by Bryan directly — this
  matches something this session had already flagged as a live possibility before he confirmed
  it). **Decision made this session: talk to Lin first**, before submitting anything
  non-preemptible into busch-lab. This is a manual/social step for Elizabeth, not something an
  AI session can do. Bryan noted talmo-lab currently has ~1 GPU of non-preemptible headroom with
  zero contention, as a fallback that avoids this entirely if wanted.

- **Bloom's Phase 2 code (actual `argo submit`-equivalent from Bloom's backend) does not exist
  yet** — it lives in the `salk-bloom` repo, not this one. This session confirmed (from that
  repo's own prior investigation) that Bloom will submit Workflow objects via the Kubernetes API
  directly, not through Argo Server or the `argo` CLI — meaning Argo's automatic `creator` label
  never gets applied. Tracked as a concrete requirement in this repo's roadmap (`bloom trigger
  route` row, 2026-08-06 addition): Phase 2's submission code needs to stamp its own
  `submitted-by`/scan-id labels on the Workflow object. Not implemented — no Phase 2 code exists
  to implement it in yet.

## A reply to Bryan was drafted but NOT sent

Elizabeth reviews and sends these herself; this session only drafts. The last draft (covering:
`bloom-workflow` done+validated, priority sync done, hostPath hardening done, the busch-lab
`workflowtemplates` RBAC gap, the staging-credential decision, and "talking to Lin first") was
in the session's temp scratchpad, which does **not** survive into a new session. If Elizabeth
still wants that reply, it needs to be re-drafted — the content above (particularly "What's found
but NOT yet resolved") has everything needed to reconstruct it, now also incorporating the
`argo-user`-vs-`bloom-pipeline` correction, which the previous draft did not yet include.

## Repo/environment facts worth knowing

- Repo root: `c:\repos\sleap-roots-pipeline`. Current branch as of handoff: `wire-bloom-workflow-sa`
  (clean working tree, nothing uncommitted).
- Open PRs authored this session: **#41** (`fix-gpu-fraction`, issue #25) and **#42**
  (`wire-bloom-workflow-sa`). Both fully validated, not yet merged — merging is Elizabeth's call.
- `argo`/`kubectl`/`runai` CLIs run via WSL, not native Windows — see `.claude/skills/runai/SKILL.md`
  for the exact invocation pattern (`wsl -e bash -c "export KUBECONFIG=... && <command>"`).
  `argo-user`'s kubeconfig: `~/.kube/kubeconfig-runai-talmo-lab.yaml` (WSL home).
- Cluster API: `https://10.7.30.173:6443` (IP, not hostname — the cert doesn't carry the hostname
  as a SAN).
- Two RunAI projects/namespaces in play: `talmo-lab`/`runai-talmo-lab` (20 GPU quota, A40s) and
  `busch-lab`/`runai-busch-lab` (2 GPU quota, A40s, currently contended — see above).
- **Do not repeat, anywhere written/shared, any characterization of Lin Wang beyond neutral
  scheduling facts** (per explicit user instruction earlier this program — this is a durable
  constraint, not specific to this handoff).
