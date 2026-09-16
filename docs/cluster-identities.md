# Cluster identities

Three different identities are involved in running this pipeline on the Salk cluster, and picking
the wrong one produces failures that don't look like permission problems. This page says what each
one is, what it can actually do, and how to get access.

Namespace throughout: **`runai-busch-lab`** (RunAI project `busch-lab`). `runai-talmo-lab` is still
live on the cluster but has not been this pipeline's target since 2026-08-13.

## The three identities

| Identity | Who authenticates as it | Can | Cannot | Credential |
|---|---|---|---|---|
| **`bloom-pipeline`** | Bloom's backend, from *outside* the cluster (`bloom-dev`) | `create`/`get`/`list`/`watch` on `workflows`; `get`/`list` on `workflowtemplates`; `get`/`list`/`watch` on `pods`; `get pods/log` | `create`/`update workflowtemplates`; `delete`/`update workflows`; `create pods/exec`; `create workflowtaskresults`; `secrets`, `configmaps`, `nodes`, `serviceaccounts`; anything outside this namespace | `kubeconfig-bloom-pipeline-busch-lab.yaml`, deployed to Bloom as `WORKFLOWS_K8S_TOKEN` / `_CA_CERT` / `_API_URL` |
| **`bloom-workflow`** | Each DAG step's own pod, via `spec.serviceAccountName` | `workflowtaskresults` `create`/`patch` — reported by the cluster admin, not read from the cluster (see [What isn't verified](#what-isnt-verified)) | it is not a submitting identity; nobody holds a kubeconfig for it | none — set once on the Workflow, Argo does the rest |
| **`argo-user`** (namespace-scoped, shared across the project) | Operators, by hand | `get`/`list`/`watch pods`, `get pods/log`, `create pods/exec`; `create`/`update workflowtemplates`; `create`/`delete workflows` | `get serviceaccounts`, `get secrets`, `create workflowtaskresults` | `kubeconfig-runai-busch-lab-argo-user.yaml` |

Both the `bloom-pipeline` and `argo-user` rows were verified live on **2026-09-15** with
`kubectl auth can-i` run under each identity's own kubeconfig — not inferred from a manifest. Rerun
the checks before relying on them; RBAC is cluster-admin-mutable:

```bash
export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
kubectl auth can-i get pods/log -n runai-busch-lab 2>/dev/null | grep -E '^(yes|no)'
```

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
four stage templates override `serviceAccountName`, so that single value covers every step.

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

**You can read pod logs.** Both `bloom-pipeline` and `argo-user` have `get pods/log`. Note that
Bloom's own status poller only surfaces Workflow *phases* (`Running`/`Succeeded`/`Failed`), not the
reason for a failure — so for diagnosis use the CLI against the namespace rather than Bloom's API.

**But only `argo-user` can open a shell.** `bloom-pipeline` cannot `create pods/exec`; `argo-user`
can. So reading logs works from either identity, while `kubectl exec` into a running step needs the
`argo-user` kubeconfig.

**Set `spec.serviceAccountName: bloom-workflow`** on any Argo DAG you submit — see
[Submit vs. report back](#submit-vs-report-back).

**There is no per-person RunAI console access.** Work is driven from the `argo` / `runai` CLI
against a kubeconfig. If you need a new identity, `bloom-pipeline-serviceaccount.yaml` is the
precedent to copy — a ServiceAccount plus a namespace-scoped Role and RoleBinding — and the cluster
admin applies it. Note from experience that the applied result may differ from what the manifest
requests, so verify with `auth can-i` once you have it.

**Finding the cluster API endpoint:** read it from your own kubeconfig rather than copying it from
anywhere — it travels with the credential.

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

Nothing here is reachable off the Salk VPN.

## Namespace facts that bite

**`runai-busch-lab` is shared by Bloom staging *and* production**, distinguished only by an
environment label stamped on each submitted Workflow, and a production dispatch deployment is live
in it. An `argo template update` therefore affects both environments' future dispatches, not just
your next run. Don't update the `sleap-roots-*` templates unless you mean to.

**You share the submitter identity.** Anything Bloom dispatches arrives as `bloom-pipeline`, so
labels are the only way to tell workloads apart. `build_workflow_body` already stamps
`submitted-by`, `pipeline-run-id`, `batch-index` and `environment`; add something distinguishing if
you are dispatching a different kind of work, or two status pollers will trip over each other's
Workflows.

**The GPU quota is 2, and it is often fully used.** Always set `priorityClassName` explicitly:
leaving it unset lands at `very-high` (150) on this cluster, the most aggressive non-preemptible
tier, not a neutral default.

Which value depends on the stage, and this pipeline is deliberately not uniform:

- The three CPU stages use `interactive-preemptible` (75) — preemptible, may use over-quota GPUs.
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

## Related

- [`bloom-pipeline-serviceaccount.yaml`](../bloom-pipeline-serviceaccount.yaml) — the requested
  RBAC for `bloom-pipeline`, and the template for a new identity
- [`openspec/specs/per-batch-pipeline/spec.md`](../openspec/specs/per-batch-pipeline/spec.md) —
  where `serviceAccountName: bloom-workflow` is specced as a requirement
- [`.claude/skills/runai/SKILL.md`](../.claude/skills/runai/SKILL.md) — where the CLIs live, and
  cluster troubleshooting
- [`README.md`](../README.md) — operator setup for the `argo` / `runai` / `kubectl` CLIs
