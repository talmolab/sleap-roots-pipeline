# Busch-lab RBAC investigation + argo-user stopgap credential — design

## Context

A4's K8s-side credential gap ([bloom-pipeline-serviceaccount.yaml](../../../bloom-pipeline-serviceaccount.yaml), drafted 2026-07-22) has been blocked on a cluster admin applying it so Bloom's backend can submit Argo Workflows unattended. The admin has been unresponsive for ~12 days (since the 2026-07-22 request). Elizabeth considered reusing her own local `argo-user` kubeconfig as a stopgap, initially theorizing the blocker was that it lacked access to the `busch-lab` project (the project name that appears to have superseded `talmo-lab` in ops conversations — the manifest already ships two variants, "Variant A: runai-talmo-lab" and a **guessed** "Variant B: runai-busch-lab", because nobody had confirmed the real namespace name).

This doc records a live-cluster investigation (read-only `kubectl`/`docker` checks against the real RunAI cluster and `bloom-dev`) that resolved several open questions and produced a tested proof-of-concept.

## Findings

1. **`runai-busch-lab` is confirmed real**, not a guess — `kubectl get namespaces` shows it with the same age as `runai-talmo-lab` (3y164d both), so it's been provisioned as long as talmo-lab has, not newly created.
2. **The "argo-user lacks busch-lab access" theory is false.** `kubectl auth can-i create/get/list/watch workflows.argoproj.io` and `get workflowtemplates.argoproj.io` all return `yes` in `runai-busch-lab`, identical to `runai-talmo-lab`. Testing further (an unrelated namespace `runai-ecker-lab`, `default`, and `--all-namespaces`) shows this access is **cluster-wide**, not scoped to talmo-lab/busch-lab specifically. The identity is `system:serviceaccount:runai-talmo-lab:argo-user` (confirmed via `kubectl auth whoami`) — a ServiceAccount, not Elizabeth's personal SSO login. The actual RoleBinding/ClusterRoleBinding granting this couldn't be read (Forbidden on listing those), consistent with `argo-user`'s otherwise-narrow permissions (also Forbidden on `get secret`/`get serviceaccount`).
3. **Neither `argo-user` nor Elizabeth's readily-available access can self-provision the dedicated SA.** `kubectl auth can-i create serviceaccounts|roles.rbac.authorization.k8s.io|rolebindings.rbac.authorization.k8s.io|secrets` all return `no`, in both `runai-talmo-lab` and `runai-busch-lab`, under `argo-user`. (Her personal RunAI SSO login — separate from `argo-user` — was not tested against the real cluster in this investigation; only a local Docker Desktop context and `argo-user` were available in the working environment.) The cluster-admin dependency for the *correct* fix (applying the drafted SA) is real and has no known workaround right now.
4. **Bloom's `services/workflows` runs as a hardened Docker container**, not a bare process — confirmed via the staging environment's `docker-compose.prod.yml` service definition: `read_only: true`, a size-capped `tmpfs:/tmp` as the only writable path, `cap_drop: ALL`, `no-new-privileges:true`, and **no volume mounts**. Its existing secret (`WORKFLOWS_SUPABASE_EMAIL`/`WORKFLOWS_SUPABASE_PASSWORD`) is supplied purely via environment variables substituted from a top-level `.env` file by docker-compose — not a mounted credentials file. **No code exists yet in `services/workflows` that reads or uses any K8s credential** — Phase 2 (the part that would actually call `argo submit`/the K8s API) hasn't been built (confirmed non-goal in bloom's own `add-cyl-pipeline-trigger/design.md`). So there is currently no real integration point to wire a credential into.
5. **Isolated proof-of-concept, tested and cleaned up**: copied `argo-user`'s kubeconfig to a throwaway directory on `bloom-dev` (`~/argo-user-test-tmp/`, piped directly between hosts, never printed to any log/output), then ran a container matching `workflows`' hardening profile (`--read-only --cap-drop=ALL --security-opt=no-new-privileges:true --user <uid>:<gid>`, mounting the kubeconfig read-only) and confirmed:
   - `kubectl auth can-i create workflows.argoproj.io -n runai-busch-lab` → `yes`
   - `kubectl get workflows -n runai-busch-lab` → `No resources found` (an *empty list*, not a `Forbidden` error — confirms the RBAC check passed; nothing has ever been submitted into `runai-busch-lab`, all prior testing this program used `runai-talmo-lab`)
   Test artifacts (the copied kubeconfig, the temp directory) were deleted from `bloom-dev` immediately after — no live credential left staged, since there's no consuming code to stage it for yet.

## Decision

No live wiring into Bloom's actual service in this change — there's nothing to wire into until Phase 2 exists. Instead:
- Document all findings above.
- Correct `bloom-pipeline-serviceaccount.yaml`'s namespace-uncertainty language now that `runai-busch-lab` is confirmed.
- Record the forward plan for whoever builds Phase 2: supply the K8s credential as environment variable(s) added to the `.env` file, matching the existing `WORKFLOWS_SUPABASE_*` convention — not a mounted kubeconfig file, since the container's `read_only`/no-volume-mounts posture doesn't accommodate one without a compose change anyway.
- Treat `argo-user` (already proven to work non-interactively) as the flagged, temporary stopgap credential *when Phase 2 is actually built* — not something to leave staged now — pending either the cluster admin applying the dedicated SA, or someone else with RBAC-admin rights doing so.
- File two follow-up issues: (a) [#35](https://github.com/talmolab/sleap-roots-pipeline/issues/35) — swap the `argo-user` stopgap for the dedicated SA once it's applied; (b) [#34](https://github.com/talmolab/sleap-roots-pipeline/issues/34) — `argo-user`'s cluster-wide (not just talmo-lab/busch-lab) Workflow access as an independent cluster-hygiene concern, worth a look regardless of this program.

## Out of scope

- Any `salk-bloom` repo code changes (Phase 2 itself).
- Actually applying `bloom-pipeline-serviceaccount.yaml` to the live cluster.
- Escalating to a different cluster admin/project owner (worth pursuing separately, not blocking this doc).
- **Deciding which project (`talmo-lab` or `busch-lab`) Bloom submissions should actually target long-term** — genuinely unresolved (see `bloom-pipeline-serviceaccount.yaml`'s own header); `runai-busch-lab` is simply what this investigation's isolated proof happened to test against, not a decision made here.

## Risks / open questions

- If Phase 2 ships using `argo-user` as environment variables without another explicit review, the cluster-wide scope could be forgotten and become de-facto permanent. Mitigated by the two tracked follow-up issues above; whoever implements Phase 2 should re-read this doc first.
- Whichever project Bloom's trigger route ends up targeting, it should self-constrain to that one namespace at the application layer, even though the `argo-user` credential technically reaches every namespace — this is a recommendation for the bloom-side implementation, not something enforceable from this repo, and not a statement that the target project has been decided (it hasn't — see Out of scope).
- **Shared-identity audit-trail gap**: `argo-user` has been used for manual/test Argo submissions since 2026-07-07 (e.g. the 2026-07-07 PoC and PR #33's real cluster run). If Bloom's backend also submits under this same identity as a Phase-2 stopgap, K8s/Argo audit logs and `kubectl auth whoami`-style attribution can no longer distinguish "an automated Bloom-triggered run" from "a manual human test run" by submitter identity alone — both would show as `system:serviceaccount:runai-talmo-lab:argo-user`. Not a blocker for the stopgap itself, but worth having some other way to tell them apart (e.g. a workflow label) if this stopgap is actually used, and worth weighing when deciding how long to tolerate it.
