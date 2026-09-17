# Cluster identities

Three Kubernetes identities are involved in running this pipeline on the Salk cluster, and picking
the wrong one produces failures that don't look like permission problems. This page says what each
one is, what it can actually do, and how to get access. Separately from all three, you have your
own RunAI SSO login — a different authentication plane, not a fourth Kubernetes identity, and the
two are not interchangeable.

Namespace throughout: **`runai-busch-lab`** (RunAI project `busch-lab`). `runai-talmo-lab` is still
live on the cluster but has not been this pipeline's target since 2026-08-13.

## Two auth planes

Kubernetes RBAC and RunAI's own identity are separate. A tool may need one or both:

| Tool / surface | Kubernetes kubeconfig | Per-person RunAI SSO |
|---|---|---|
| `argo` | required | no |
| `kubectl` | required | no |
| `runai` | required | **also required** |
| RunAI console | no — browser SSO only | required |

Operators share one namespace-scoped `argo-user` kubeconfig for the Kubernetes plane; the
`bloom-pipeline` identity below carries its own. RunAI SSO is per person, and it is not automatic:
a new person must be added to the `busch-lab` RunAI project by the cluster admin or a project
owner. Salk SSO will authenticate you regardless — membership is what makes `busch-lab` visible
and actionable once you are signed in.

Confirmed with the repo owner, 2026-09-15.

The failure this prevents: with no SSO session, `runai` commands fail while `argo` keeps working
against the same namespace from the same shell. That does not look like an auth problem. Sign in
with `runai login remote-browser`, then confirm with `runai whoami`.

## The three Kubernetes identities

| Identity | Who authenticates as it | Can | Cannot | Credential |
|---|---|---|---|---|
| **`bloom-pipeline`** | Bloom's backend, from *outside* the cluster (`bloom-dev`) | `create`/`get`/`list`/`watch` on `workflows`; `get`/`list` on `workflowtemplates`; `get`/`list`/`watch` on `pods`; `get pods --subresource=log` | `create`/`update workflowtemplates`; `delete`/`update workflows`; `create pods`; `create pods --subresource=exec`; `create workflowtaskresults`; `secrets`, `configmaps`, `nodes`, `serviceaccounts`; anything outside this namespace | `kubeconfig-bloom-pipeline-busch-lab.yaml`, deployed to Bloom as `WORKFLOWS_K8S_TOKEN` / `_CA_CERT` / `_API_URL` |
| **`bloom-workflow`** | Each DAG step's own pod, via `spec.serviceAccountName` | `workflowtaskresults` `create`/`patch` — reported by the cluster admin, not read from the cluster (see [What isn't verified](#what-isnt-verified)) | it is not a submitting identity; nobody holds a kubeconfig for it | none — set once on the Workflow, Argo does the rest |
| **`argo-user`** (namespace-scoped, shared across the project) | Operators, by hand | `get`/`list`/`watch pods`; `create`/`update workflowtemplates`; `get`/`list workflowtemplates`; `create`/`delete workflows`; `create pods` | `get pods --subresource=log`; `create pods --subresource=exec`; `get serviceaccounts`, `get`/`list`/`create secrets`, `create workflowtaskresults` | `kubeconfig-runai-busch-lab-argo-user.yaml` |

Both the `bloom-pipeline` and `argo-user` rows were verified live on **2026-09-15** with
`kubectl auth can-i` run under each identity's own kubeconfig — every cell, not a spot-check, and
not inferred from a manifest. Rerun the checks before relying on them; RBAC is
cluster-admin-mutable:

```bash
export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
kubectl auth can-i get pods --subresource=log -n runai-busch-lab 2>/dev/null | grep -E '^(yes|no)'
```

> **Use `--subresource=`, never `pods/log`.** In `kubectl auth can-i`, everything after the slash
> is a resource *name*, not a subresource — `get pods/log` asks "can I get a pod **named** `log`",
> which merely mirrors bare `pods` access and answers `yes` for any identity that can read pods.
> This is not theoretical: three claims on this page were "verified" with the slash form and were
> wrong. `argo-user` answers `yes` to `get pods/log` and **`no`** to `get pods --subresource=log`.

> Filter stderr. `kubectl` prints `Warning: Use tokens from the TokenRequest API...` on stderr,
> which interleaves with the answer — a bare `| head -1` captures the warning instead of the
> verdict.

**`bloom-pipeline-serviceaccount.yaml` in this repo is the *request*, not the grant.** Its comment
says `pods`/`pods/log` were "intentionally omitted"; the applied identity has them. Read the table
above, not the manifest, for what is true.

## Submit vs. report back

This is the split that causes the confusing failure, so it's worth understanding before you wire
anything new.

`bloom-pipeline` submits the Workflow *object* from outside the cluster. It plays no part in
running the DAG. Once Argo starts the workflow, each step's pod needs to report its own result
back to Argo — and it does that as `bloom-workflow`, set on the Workflow at
[`sleap-roots-pipeline.yaml`'s `spec.serviceAccountName`](../sleap-roots-pipeline.yaml). None of the
five workflow templates override `serviceAccountName`, so that single value covers every step
(four stage templates plus the `exit-gate`, which likewise sets none).

Omit it and **every step fails** with:

```
workflowtaskresults.argoproj.io is forbidden
```

The Workflow itself submits cleanly, which is what makes this misleading — the error surfaces per
step and looks unrelated to submission. If you are adding a new Argo DAG to this namespace, set
`spec.serviceAccountName: bloom-workflow` on it.

Corroborating evidence for why the split exists: neither `bloom-pipeline` nor `argo-user` can
`create workflowtaskresults` (both verified **no**). The identity that submits a workflow
structurally cannot report its steps' results.

## What isn't verified

**`bloom-workflow`'s permissions have never been read from the cluster.** It is a pod-mounted
ServiceAccount, so nobody holds a kubeconfig for it and `kubectl auth can-i` cannot be run as it.
Reading its Role object directly is also blocked: `get serviceaccounts` returns **no** under both
`bloom-pipeline` and `argo-user`.

What is known rests on two things: the cluster admin's description of what he created
(`workflowtaskresults create/patch`), and the fact that real pipeline runs succeed — pod admission
works and no `workflowtaskresults.argoproj.io is forbidden` error appears. See
[`wire-bloom-workflow-sa/tasks.md`](../openspec/changes/archive/2026-08-12-wire-bloom-workflow-sa/tasks.md),
step 3.1, which records the same limitation and the same indirect confirmation.

Treat `bloom-workflow`'s row above as reported-and-consistent-with-observation, not measured.

## Getting access (new Bloom-side developer)

**If Bloom dispatches your workflows, you need no new credential.** The token is already deployed
to the workflows service as `WORKFLOWS_K8S_TOKEN` / `_CA_CERT` / `_API_URL` for both staging and
production. Reuse `services/workflows/k8s_client.py` — `build_workflow_body`, `submit_workflow`,
`get_workflow_status` — rather than building a new client. The dispatch pattern to copy is
`dispatch_worker.py` (queue → submit) plus `status_poller.py` (sweep → status write).

**Your WorkflowTemplates must be registered in the namespace first, and `bloom-pipeline` cannot do
it.** It has `get`/`list` on `workflowtemplates` only. Registration needs `argo-user`, which has
`create` and `update`. This is the real prerequisite, not the credential.

**Never state in this repo that the cluster matches it.** The namespace is shared and mutable —
anyone with `argo-user` can re-register a template at any moment, so a parity claim is false as
soon as it is written. This is not hypothetical: a 2026-09-15 spot-check found the registered
predictor matching this repo, and within the hour the templates were re-registered from a newly
merged `main`, leaving both the cluster and that observation ahead of the branch that recorded it.
Run `scripts/check_cluster_drift.sh` when you need to know; nothing enforces parity between runs
([#58](https://github.com/talmolab/sleap-roots-pipeline/issues/58)).

**Pod logs need the `bloom-pipeline` kubeconfig — not `argo-user`.** This is the opposite of what
you would guess from `argo-user` being the operator identity, and the opposite of what this page
said until 2026-09-16. Measured under each kubeconfig with `--subresource=log`: `bloom-pipeline`
**yes**, `argo-user` **no**. So the identity that can submit and delete workflows cannot read a
single line of their output, while the one Bloom holds can. Note also that Bloom's status poller
only surfaces Workflow *phases* (`Running`/`Succeeded`/`Failed`), never the reason for a failure —
so diagnosis means `kubectl logs` under the `bloom-pipeline` kubeconfig, not Bloom's API.

**Nobody can exec.** `create pods --subresource=exec` is **no** under both identities, so there is
no `kubectl exec` route into a running step from any credential in this repo. `argo-user` *can*
`create pods` outright, which is why the slash form `create pods/exec` misleadingly answers `yes`
— it is asking about a pod *named* `exec`. For an interactive shell use `runai workspace exec`
against your own SSO session (see [Two auth planes](#two-auth-planes)), which is a different plane
entirely and is what the runai skill has always recommended.

**Set `spec.serviceAccountName: bloom-workflow`** on any Argo DAG you submit — see
[Submit vs. report back](#submit-vs-report-back).

**Secrets are created in the RunAI console, not with `kubectl`.** No kubeconfig identity here can
create one — `bloom-pipeline` has no `secrets` access at all, and `argo-user` returns **no** for
`get`, `list` and `create` alike (verified 2026-09-15). Use Credentials → Generic secret in the
console, Project-scoped to `busch-lab`. RunAI prefixes the resulting Kubernetes Secret name with
`genericsecret-`, which is why the manifests reference `genericsecret-wandb-api-key` rather than the
asset name you typed. Creating them is **self-service** once you have console access — no
cluster-admin round-trip — but it does need your own RunAI SSO login, so see
[Two auth planes](#two-auth-planes) first.

Secrets are a fourth hand-made precondition, alongside the three directories below, and they fail
the same way: a missing Secret leaves the pod `Pending` (or in `CreateContainerConfigError`), never
`Failed`, so the Workflow hangs rather than erroring. Note also that
`sleap-roots-pipeline.yaml` hardcodes `genericsecret-bloom-staging-pipeline-credentials`, so a
*production*-dispatched Workflow mounts the **staging** Bloom credential — the prod account has
never been created ([#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17)). Dormant
today because nothing drives prod, not because it is correct.

**If you need a new Kubernetes identity**, `bloom-pipeline-serviceaccount.yaml` is the precedent to
copy — a ServiceAccount plus a namespace-scoped Role and RoleBinding — and the cluster admin applies
it. Note from experience that the applied result may differ from what the manifest requests, so
verify with `auth can-i` once you have it.

**Finding the cluster API endpoint:** read it from your own kubeconfig rather than copying it from
anywhere — it travels with the credential.

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

Nothing here is reachable off the Salk VPN.

## Namespace facts that bite

**`runai-busch-lab` is shared by Bloom staging *and* production**, distinguished only by an
environment label stamped on each submitted Workflow, and a production dispatch deployment is live
in it — `bloom_v2_prod-cyl-pipeline-worker-1` and `bloom_v2_prod-cyl-status-poller-1`, last
confirmed running on `bloom-dev.salk.edu` on 2026-09-15 alongside the staging pair. ("Live" means
the dispatcher process is running, not that anything is driving it — no frontend targets prod
yet.) An `argo template update` therefore affects both environments' future
dispatches, not just your next run. Don't update the `sleap-roots-*` templates unless you mean to.

**You share the submitter identity.** Anything Bloom dispatches arrives as `bloom-pipeline`, so
labels are the only way to tell workloads apart. `build_workflow_body` already stamps
`submitted-by`, `pipeline-run-id`, `batch-index` and `environment`; add something distinguishing if
you are dispatching a different kind of work, or two status pollers will trip over each other's
Workflows.

**The GPU quota is 2, and it is often fully used.** Always set `priorityClassName` explicitly —
what an unset value resolves to cannot be verified with this repo's credentials, since the
cluster-scoped `priorityclasses` API is Forbidden to every `argo-user` identity here.
**Corrected 2026-09-16:** this section previously said an unset value lands at `very-high` (150),
"the most aggressive non-preemptible tier". That was never verified — `git log -S` traces it to
PR #41, introduced alongside a `grep` rather than a scheduling observation — and Argo pods observed
with no class resolved to priority **0**, the *lowest* tier, below `train` (50). Treat the default
as unknown-and-probably-lowest: declare the class explicitly on every template.

The 2 is a **deserved** quota in RunAI's sense, not a hard cap — preemptible work may exceed it.
That does not help this pipeline's GPU work, though: the predictor is the only GPU-requesting
stage and it runs non-preemptible `high` (below), so at 2/2 it does not burst above the quota, it
waits — surfacing as `NonPreemptibleOverQuota`. Confirmed with the repo owner, 2026-09-15.

Which value depends on the stage, and this pipeline is deliberately not uniform:

- The four CPU stages use `interactive-preemptible` (75) — preemptible, and permitted to exceed
  the deserved quota. They request no GPU, so that permission buys this pipeline nothing in GPU
  terms; it matters for CPU and for scheduling order.
- **The predictor uses `high` (125), which is non-preemptible, on purpose.** Set per cluster-admin
  guidance 2026-08-06 because `trait-extractor` has no skip-if-done yet
  ([#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37)), so an eviction mid-batch
  would recompute the whole thing. `sleap-roots-predictor-template.yaml` says "never remove this
  field outright" — don't "fix" it to `interactive-preemptible` on the strength of the bullet
  above.

So non-preemptible work in this namespace is normal, not an accident. The consequence: a
non-preemptible submission here **can evict another project's preemptible session**. That has come
close to happening — the recorded expectation is to check who holds the quota
(`kubectl get pods -n runai-busch-lab`) and coordinate with them before submitting
non-preemptible work, not just to set the field and go.

**`argo submit -n <ns>` does not redirect a Workflow submission — the manifest's
`metadata.namespace` wins.** This is non-obvious and worth knowing before you trust a `-n` flag.
Verified 2026-09-15:

```bash
argo submit --server-dry-run -n runai-talmo-lab -o json sleap-roots-pipeline.yaml
  # → metadata.namespace = runai-busch-lab
```

So `-n` governs where `argo template create/update` and `argo list`/`get`/`logs` look, but not
where a submitted Workflow lands. `runai_run_pipeline.sh` therefore hard-codes
`NAMESPACE="runai-busch-lab"` with no env-var override: an override could only have moved the
template registrations away from the namespace the Workflow still runs in.

**Bloom's path is different again.** `k8s_client.py` resolves the namespace from
`WORKFLOWS_K8S_NAMESPACE` and then *overwrites* `body["metadata"]["namespace"]` itself, because the
Kubernetes API rejects a body whose namespace disagrees with the URL's namespace segment. So for
Bloom-dispatched runs the manifest's value is inert; for hand-run `argo submit` it is decisive.

**Storage is three hand-made directories, and a missing one hangs the run rather than failing it.**
All three `hostPath` volumes use `type: Directory`, which requires the path to pre-exist —
deliberately, so a down NFS mount cannot silently write to a node's local disk instead.
Nothing in this repo creates them. The operationally important part for anyone debugging: a pod that
cannot mount its `hostPath` sits **`Pending`**, not `Failed` or `Error`, so neither `retryStrategy`
nor `continueOn` applies and the Workflow **hangs** instead of failing. If a run is stalled with no
step ever starting, check `kubectl describe pod` for mount events before looking anywhere else.

That these directories exist at all is a standing precondition nothing enforces — tracked as
[#63](https://github.com/talmolab/sleap-roots-pipeline/issues/63), which is an
operational-continuity risk rather than a documentation gap, and has a real deadline attached. Note
that per-run directories are **not** the fix: the cluster-side skip-if-done dedup this program
depends on only works because the paths are shared (see
[#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37)).

## Related

- [`bloom-pipeline-serviceaccount.yaml`](../bloom-pipeline-serviceaccount.yaml) — the requested
  RBAC for `bloom-pipeline`, and the template for a new identity
- [`openspec/specs/per-batch-pipeline/spec.md`](../openspec/specs/per-batch-pipeline/spec.md) —
  where `serviceAccountName: bloom-workflow` is specced as a requirement
- [`.claude/skills/runai/SKILL.md`](../.claude/skills/runai/SKILL.md) — where the CLIs live, and
  cluster troubleshooting
- [`README.md`](../README.md) — operator setup for the `argo` / `runai` / `kubectl` CLIs
