---
name: runai
description: Use when submitting, monitoring, exec-ing into, or troubleshooting RunAI GPU jobs for the sleap-roots pipeline on the Salk cluster (project talmo-lab / namespace runai-talmo-lab) — e.g. running the predictor stage interactively, debugging a stuck pod, or staging data over the /hpi/hpi_dev NFS mount. Adapted from the mosquito-cfd runai-cluster-skill.
---

# RunAI cluster skill — sleap-roots-pipeline

RunAI CLI v2 assistance for the Salk GPU cluster. The **production path is Argo**
(`runai_run_pipeline.sh` → `argo submit`); use the `runai workspace` CLI here for the
**interactive / ad-hoc / debug** path — running a single stage by hand, staging data,
exec-ing into a live pod, or diagnosing scheduling.

> Project: **`talmo-lab`** · Namespace: **`runai-talmo-lab`** · Cluster Argo server:
> `gpu-master:8888`. These are the canonical identifiers (confirmed against the live cluster
> and the GAPIT pipeline). If a manifest still says `tye-lab`, it is stale — fix it.

## 1. WSL command execution pattern

RunAI runs in **WSL**, not Windows PowerShell, and needs an explicit KUBECONFIG:

```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
  runai <command>"
```

- `runai` is assumed on `PATH`; if your install isn't, use its absolute path (e.g.
  `"$HOME/.runai/bin/runai"`). **Verify the `KUBECONFIG` path and the `runai` binary location
  in your own WSL environment** before constructing commands — these are operator-specific.
- In **Git Bash** (not WSL), prefix cluster-path commands with `MSYS_NO_PATHCONV=1` to stop
  `/hpi/...` from being mangled into a Windows path.

## 2. Path mapping (Windows ↔ WSL ↔ cluster)

| Context | Path |
|---|---|
| Windows (local) | `Z:\users\eberrigan\...` |
| WSL | `/mnt/hpi_dev/users/eberrigan/...` |
| Cluster (NFS, in `--host-path` + container mounts) | `/hpi/hpi_dev/users/eberrigan/...` |

`Z:` = `\\multilab-na.ad.salk.edu\hpi_dev` (Salk VPN / multilab-na). Host-path mount syntax:

```
--host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/<dir>,mount=/data,mount-propagation=HostToContainer,readwrite
```

## 3. Workspace lifecycle

All commands take `-p talmo-lab`. Use **`runai workspace`** (does not auto-terminate — you
clean up manually) rather than `runai training` (auto-terminates on completion).

| Operation | Command |
|---|---|
| List | `runai workspace list -p talmo-lab` |
| Describe | `runai workspace describe <name> -p talmo-lab` |
| Logs | `runai workspace logs <name> -p talmo-lab --follow` |
| Exec | `runai workspace exec <name> -p talmo-lab -- <cmd>` |
| Interactive shell | `runai workspace exec <name> -p talmo-lab --stdin --tty -- /bin/bash` |
| Delete | `runai workspace delete <name> -p talmo-lab` |

> Use `runai workspace exec`, **not** `kubectl exec` — RunAI manages its own auth layer.

## 4. Resource flags (CLI v2)

| Need | Flag |
|---|---|
| GPU (whole) | `--gpu-devices-request 1` |
| GPU (fractional) | `--gpu-portion-request 0.5` (the predictor template annotates `gpu-fraction: "0.5"`) |
| CPU cores | `--cpu-core-request 12` |
| Memory | `--cpu-memory-request 32G` |
| Always re-pull image | `--image-pull-policy Always` |

Only the **predictor** stage needs a GPU; `models-downloader` and `trait-extractor` are
CPU-only. (Note: the predictor template pins both `gpu-fraction: "0.5"` and a hard
`nvidia.com/gpu: 1` — under fractional scheduling the annotation governs.)

## 5. Stage images

Current registry is **GitLab** (`registry.gitlab.com/salk-tm/...`); the roadmap A0 target is to
migrate these to GHCR, not yet done — so use the GitLab refs until then.

| Stage | Image |
|---|---|
| models-downloader | `registry.gitlab.com/salk-tm/models-downloader:<tag>` |
| predictor (GPU) | `registry.gitlab.com/salk-tm/sleap-roots-predict:<tag>` |
| trait-extractor | `registry.gitlab.com/salk-tm/sleap-roots-traits:<tag>` |

Pin a tag/digest — never `:latest`. Confirm the tag exists in the registry before submitting.

## 6. Example — run the predictor stage interactively

The predictor reads three container dirs — `/workspace/images_input`, `/workspace/models_input`,
`/workspace/output` — which are also its entrypoint's positional args. **Mount the host dirs
to those exact container paths.** Note the non-obvious remap: the *models-downloader output*
dir (`models_downloader_output`) is what feeds the predictor's `models_input`.

```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
runai workspace submit srp-predict-test \
  -p talmo-lab \
  --image registry.gitlab.com/salk-tm/sleap-roots-predict:<tag> \
  --image-pull-policy Always \
  --gpu-portion-request 0.5 \
  --cpu-core-request 8 \
  --cpu-memory-request 16G \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/images_downloader_output,mount=/workspace/images_input,mount-propagation=HostToContainer \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/models_downloader_output,mount=/workspace/models_input,mount-propagation=HostToContainer \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/predictions,mount=/workspace/output,mount-propagation=HostToContainer,readwrite \
  -- bash -c '<predict entrypoint> /workspace/images_input /workspace/models_input /workspace/output; sleep infinity'"
```

`sleep infinity` keeps the pod alive after the run so you can `runai workspace exec` in to
inspect outputs. **Delete it when done** (`runai workspace delete srp-predict-test -p talmo-lab`).

## 7. Preemptibility & GPU over-quota

**Preemptibility is set by `priorityClassName`, NOT by the `preemptible: "true"` annotation**
the templates carry (that annotation is a UI/convention breadcrumb only). Run:ai treats
`priorityClassName` **≥ 100 as non-preemptible**, **< 100 as preemptible**:

| Class | Preemptible? | Behaviour |
|---|---|---|
| `inference` (125), `build` (100) | no | must fit the project's **deserved quota**; never evicted |
| `interactive-preemptible` (75), `train` (50) | yes | may use **over-quota** GPUs; may be evicted → pair with `retryStrategy` |

The lab's preemptible GPU class is **`interactive-preemptible`**. The predictor's GPU jobs
typically run *within* quota, so over-quota preemption isn't usually exercised — but if a GPU
pod is stuck `Pending`/`Unschedulable` with:

```
NonPreemptibleOverQuota: Non-preemptible workload is over quota. ... talmo-lab quota is 20 GPUs,
while 20 GPUs are already allocated for non-preemptible pods. Use a preemptible workload to go over quota.
```

set the priority class:

- **Argo** WorkflowTemplate/Workflow: `spec.templates[].priorityClassName: interactive-preemptible`
- **`runai` CLI**: submit as a **training** workload (preemptible) instead of a workspace.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Auth error / token expired | `runai login remote-browser` (then `runai whoami`) |
| Job stuck `Pending` | check cluster capacity + resource requests (`runai workspace describe`); if `NonPreemptibleOverQuota`, see §7 |
| Mount error at startup | verify `--host-path` syntax and that the `/hpi/hpi_dev/...` directory exists on the node |
| `ImagePullBackOff` | confirm the `registry.gitlab.com/salk-tm/...` tag exists; test `docker pull` of the same tag |
| `gh` returns HTTP 403 | `unset GITHUB_TOKEN` first (long-lived fine-grained tokens are blocked by the `talmolab` org) |
| Git Bash mangles `/hpi/...` | prefix with `MSYS_NO_PATHCONV=1` (or run in WSL) |

## 9. CLI v1 → v2 migration

| v1 (deprecated) | v2 (current) |
|---|---|
| `runai submit` | `runai workspace submit` |
| `runai list jobs` | `runai workspace list` |
| `runai describe job` | `runai workspace describe` |
| `runai logs` | `runai workspace logs` |
| `runai delete job` | `runai workspace delete` |
| `--cpu 12` | `--cpu-core-request 12` |
| `--memory 32G` | `--cpu-memory-request 32G` |
| `--gpu 1` | `--gpu-devices-request 1` |
| `--host-path /src:/dst:ro` | `--host-path path=/src,mount=/dst,mount-propagation=HostToContainer` |

---

*Adapted from the `mosquito-cfd` `runai-cluster-skill` (CFD/IAMReX → sleap-roots
predict/traits). The same Salk cluster, project `talmo-lab`, and WSL/KUBECONFIG pattern
apply; workloads, images, and the GPU-on-predictor-only shape are sleap-roots-specific.*
