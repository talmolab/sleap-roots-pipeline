---
description: Debug a failing GitHub Actions run, or a failing Argo workflow run, for this repo
---

# CI / Run Debug

Diagnose and fix a failing run in this repo. For the `gh` commands below, resolve the repo
first — never hardcode it:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
```

> **Note:** this repo has **no `.github/workflows/` yet** — there is no GitHub Actions CI to
> debug until one is added (likely alongside roadmap tier A4). Until then, the real failure
> surface is the **Argo workflow run on the RunAI cluster**. Both paths are covered below;
> use the GitHub-Actions section once CI exists.

## A. Debug an Argo workflow run (the current failure surface)

`argo` exists only in WSL, and the Windows `kubectl` (Docker Desktop's) points at the
`docker-desktop` cluster — so run every command below **inside WSL** with an explicit
kubeconfig (`.claude/skills/runai/SKILL.md` §1a). Which identity can do what is in
`docs/cluster-identities.md`: the operator `argo-user` kubeconfig can list/get/describe but
**cannot read pod logs** — use the `bloom-pipeline` kubeconfig for `logs`.

### Step 1: Find the failing workflow and node

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
  export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
  argo list -n runai-busch-lab; \
  argo get <workflow-name> -n runai-busch-lab'          # node tree + which step failed
```

### Step 2: Drop to pod/Kubernetes level if needed

```bash
# describe: scheduling / volume / GPU events (argo-user can do this)
wsl -e bash -c 'export PATH=$HOME/bin:$PATH; \
  export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
  kubectl get pods -n runai-busch-lab; kubectl describe pod <pod-name> -n runai-busch-lab'

# logs: needs the bloom-pipeline identity (argo-user is Forbidden; `argo logs` can exit 0 on denial)
wsl -e bash -c 'export PATH=$HOME/bin:$PATH; \
  export KUBECONFIG=$HOME/.kube/kubeconfig-bloom-pipeline-busch-lab.yaml; \
  kubectl logs <pod-name> -c main -n runai-busch-lab --tail 100 2>&1'
```

### Step 3: Reproduce / fix by failure class

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Manifest rejected on submit | invalid Argo YAML | `wsl -e bash scripts/lint_manifests.sh` locally and fix (`/lint` — bare `argo lint --offline` fails on this tree) |
| Pod stuck `Pending` (any stage) | cluster at capacity, or a CPU stage waiting — not necessarily GPU-related. (The inert `preemptible: "true"` annotation is on **two** of the five workflow templates, predictor and trait-extractor; it is a breadcrumb, not the scheduling mechanism.) A pod that cannot be scheduled, or cannot pull its image, or cannot mount a `hostPath`, stays `Pending` **forever** — not `Failed`, not `Error` — so neither `retryStrategy` nor `continueOn` applies. Since `exit-gate` is the DAG's only leaf, a `Pending` gate leaves an otherwise-complete batch `Running` indefinitely. | check `argo get`/`kubectl describe pod` events + cluster capacity; add `retryStrategy` |
| GPU pod blocked: `NonPreemptibleOverQuota` | the job is non-preemptible and the project is at its GPU quota — the `preemptible: "true"` annotation is **not** the scheduling mechanism; `priorityClassName` is | `interactive-preemptible` (75) lets a workload go over quota (Run:ai treats < 100 as preemptible). **But do not "fix" the predictor this way** — it is deliberately `high` (125, non-preemptible) per cluster-admin guidance 2026-08-06, because trait-extractor has no skip-if-done yet (#37), so eviction would recompute a whole batch. Check `kubectl get pods -n runai-busch-lab` for who holds the 2-GPU quota and coordinate instead. |
| Predictor or downloader node `Pending`, **no pod**, message `Waiting for runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/<key> lock` | expected (#98): the namespace-wide concurrency limit is full | nothing, or retune live — see the header of `sleap-roots-pipeline-semaphores.yaml`. A raise reaches waiting tasks only at the next release or within 20 minutes |
| Predictor or downloader node `Error`: `configmaps "sleap-roots-pipeline-semaphores" not found`, or `Sync configuration key ... not found in ConfigMap` | the semaphore ConfigMap is missing, lacks a key, or holds a non-integer (`strconv.Atoi: parsing "…": invalid syntax`) — this Errors running tasks too, at their next reconcile; a running pod is not killed and finishes, but its node ends Error | `kubectl create -f sleap-roots-pipeline-semaphores.yaml` (or fix the value with the header's patch), then resubmit the batch |
| Every gated run in the namespace stalled: all `pipeline-gpu` (or `pipeline-stage-in`) slots held by pods stuck `Pending` (hostPath mount failure, `ImagePullBackOff`, `NonPreemptibleOverQuota`) | #98: a slot is taken before the pod exists, and a pod that never schedules has no timeout, so it holds its slot | fix the cause, and delete or `argo stop` the stuck Workflows; their slots free within about a minute |
| Pod fails at startup, volume error | `hostPath type: Directory` does not exist on the node | create the directory first (under `/hpi/hpi_dev/...` on cluster), or fix the path; check cluster↔local *path* parity |
| `ImagePullBackOff` | wrong/missing image tag or registry auth | verify the pinned reference resolves in GHCR (`ghcr.io/talmolab/...` for the producers, `ghcr.io/salk-harnessing-plants-initiative/bloomctl` for the rest) — pull the exact string in `image:`, digest included |
| Stage runs but produces no output | mount-path mismatch between stages | confirm output mount of one stage == input mount of the next |
| Predictor runs on CPU (`device=cpu` in the `main` log; `main` has `NVIDIA_VISIBLE_DEVICES=void`) | RunAI gave the slice to `wait`: the `podSpecPatch` reorder is missing, wrong, or broken by an Argo/Run:ai upgrade (#117) | restore the `podSpecPatch` (and `gpu-fraction-container-name: "main"`, used from Run:ai 2.24) in `sleap-roots-predictor-template.yaml` (the comments there explain why), then re-run the #117 probe. **Do NOT raise `gpu-memory`**: a bigger slice for the wrong container changes nothing. |
| Predictor CUDA out-of-memory | the pod-level `gpu-memory` slice is too small for the largest model's inference pass (or the annotation is on the wrong step/level) | raise `gpu-memory` (an absolute amount in MB of 10^6 bytes, e.g. `"8192"`), and retune `pipeline-gpu` / `GPU_SLICE_*` to match, at `spec.templates[predictor].metadata.annotations` — pod level, the only placement Argo copies onto the pod. **Do NOT add an `nvidia.com/gpu` limit**: coexisting with the annotation is exactly what caused [#25](https://github.com/talmolab/sleap-roots-pipeline/issues/25), silently claiming a whole GPU. `gpu-fraction` is not used by this repo. |

## B. Debug a GitHub Actions run (once CI is added)

### Step 1: Identify the failing run and job

```bash
gh run list --repo "$REPO" --branch $(git branch --show-current) --limit 5
gh run view <run-id> --repo "$REPO"
gh run view <run-id> --repo "$REPO" --log-failed
```

### Step 2: Reproduce locally

Run the failing job's equivalent locally: for an assertion job, `/test` (from Git Bash);
for a manifest-lint job, `/lint`; for a schema/spec job,
`openspec validate --all --strict`. `/pre-merge` runs all three.

### Advanced: download logs

```bash
gh run download <run-id> --repo "$REPO" --dir ./ci-logs-<run-id>
ls ./ci-logs-<run-id>/
```

### Re-run a failed job

```bash
gh run rerun <run-id> --repo "$REPO" --failed
gh run watch --repo "$REPO"
```

### Is main green?

```bash
gh run list --repo "$REPO" --branch main --limit 3
```

If CI fails in a way unrelated to your change, check https://www.githubstatus.com/.

## Related commands

- `/test`, `/lint`, `/pre-merge` — the local checks that stand in for CI
- `/review-pr` — adversarial multi-lens review (Argo/RunAI/storage lenses)
- `/copilot-review` — triage Copilot inline comments
- `/pr-description` — capture verification state in the PR body
