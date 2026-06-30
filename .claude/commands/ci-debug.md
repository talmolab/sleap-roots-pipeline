---
description: Debug a failing GitHub Actions run, or a failing Argo workflow run, for this repo
---

# CI / Run Debug

Diagnose and fix a failing run in `talmolab/sleap-roots-pipeline`.

> **Note:** this repo has **no `.github/workflows/` yet** — there is no GitHub Actions CI to
> debug until one is added (likely alongside roadmap tier A4). Until then, the real failure
> surface is the **Argo workflow run on the RunAI cluster**. Both paths are covered below;
> use the GitHub-Actions section once CI exists.

## A. Debug an Argo workflow run (the current failure surface)

### Step 1: Find the failing workflow and node

```bash
argo list -n runai-talmo-lab
argo get <workflow-name> -n runai-talmo-lab          # node tree + which step failed
argo logs <workflow-name> -n runai-talmo-lab --tail 100   # or --follow to stream
```

### Step 2: Drop to pod/Kubernetes level if needed

```bash
kubectl get pods -n runai-talmo-lab
kubectl logs <pod-name> -n runai-talmo-lab
kubectl describe pod <pod-name> -n runai-talmo-lab   # scheduling / volume / GPU events
```

### Step 3: Reproduce / fix by failure class

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Manifest rejected on submit | invalid Argo YAML | `argo lint <file>.yaml` locally and fix |
| Pod stuck `Pending` (any stage) | cluster at capacity, or a CPU stage waiting — `preemptible: "true"` is on **all three** templates, not just the GPU step, so this is not necessarily GPU-related | check `argo get`/`kubectl describe pod` events + cluster capacity; add `retryStrategy` |
| GPU pod blocked: `NonPreemptibleOverQuota` | the job is non-preemptible and the project is at its GPU quota — the `preemptible: "true"` annotation is **not** the scheduling mechanism | set `priorityClassName: interactive-preemptible` on the template to go over quota (Run:ai treats `priorityClassName` < 100 as preemptible) |
| Pod fails at startup, volume error | `hostPath type: Directory` does not exist on the node | create the directory first (under `/hpi/hpi_dev/...` on cluster), or fix the path; check cluster↔local *path* parity |
| `ImagePullBackOff` | wrong/missing image tag or registry auth | verify the pinned image tag/digest exists in the registry (`registry.gitlab.com/salk-tm/...`) |
| Stage runs but produces no output | mount-path mismatch between stages | confirm output mount of one stage == input mount of the next |
| Predictor OOM / no GPU | missing `nvidia.com/gpu` limit, GPU on wrong step, or `gpu-fraction` too small | check `resources.limits` is on the predictor step only; raise `gpu-fraction` if the model needs more than half a GPU |

## B. Debug a GitHub Actions run (once CI is added)

### Step 1: Identify the failing run and job

```bash
gh run list --repo talmolab/sleap-roots-pipeline --branch $(git branch --show-current) --limit 5
gh run view <run-id> --repo talmolab/sleap-roots-pipeline
gh run view <run-id> --repo talmolab/sleap-roots-pipeline --log-failed
```

### Step 2: Reproduce locally

Run the failing job's equivalent locally. For a manifest-lint job that is `argo lint`; for a
schema/spec job that is `openspec validate --all --strict`.

### Advanced: download logs

```bash
gh run download <run-id> --repo talmolab/sleap-roots-pipeline --dir ./ci-logs-<run-id>
ls ./ci-logs-<run-id>/
```

### Re-run a failed job

```bash
gh run rerun <run-id> --repo talmolab/sleap-roots-pipeline --failed
gh run watch --repo talmolab/sleap-roots-pipeline
```

### Is main green?

```bash
gh run list --repo talmolab/sleap-roots-pipeline --branch main --limit 3
```

If CI fails in a way unrelated to your change, check https://www.githubstatus.com/.

## Related commands

- `/review-pr` — adversarial multi-lens review (Argo/RunAI/storage lenses)
- `/copilot-review` — triage Copilot inline comments
- `/pr-description` — capture verification state in the PR body
