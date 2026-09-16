---
name: runai
description: Use when submitting, monitoring, exec-ing into, or troubleshooting RunAI GPU jobs for the sleap-roots pipeline on the Salk cluster (project busch-lab / namespace runai-busch-lab) — e.g. running the predictor stage interactively, debugging a stuck pod, or staging data over the /hpi/hpi_dev NFS mount. Adapted from the mosquito-cfd runai-cluster-skill.
---

# RunAI cluster skill — sleap-roots-pipeline

RunAI CLI v2 assistance for the Salk GPU cluster. The **production path is Argo**
(`runai_run_pipeline.sh` → `argo submit`); use the `runai workspace` CLI here for the
**interactive / ad-hoc / debug** path — running a single stage by hand, staging data,
exec-ing into a live pod, or diagnosing scheduling.

> Project: **`busch-lab`** · Namespace: **`runai-busch-lab`** · Cluster Argo server:
> `gpu-master:8888`. **Updated 2026-08-13 — this pipeline now targets busch-lab only** (was
> `talmo-lab`; see `sleap-roots-pipeline.yaml`'s `metadata.namespace`). `talmo-lab`/
> `runai-talmo-lab` remain live on the cluster (20 GPU quota) but are no longer this pipeline's
> target — don't assume examples elsewhere still apply without checking. If a manifest still
> says `tye-lab`, it is stale — fix it.

## 1. WSL command execution pattern

RunAI runs in **WSL**, not Windows PowerShell, and needs **two** things: an explicit KUBECONFIG
*and* an active SSO session. The kubeconfig is shared across the project; the SSO login is yours
personally.

```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml && \
  runai <command>"
```

- **The kubeconfig alone is not enough.** `runai` commands fail until you have signed in with
  `runai login remote-browser` (confirm with `runai whoami`). `argo` and `kubectl` need only the
  kubeconfig — which is why `argo` keeps working in the very shell where `runai` is failing on auth.
  See `docs/cluster-identities.md` → "Two auth planes".
- `runai` is assumed on `PATH`; if your install isn't, use its absolute path (e.g.
  `"$HOME/.runai/bin/runai"`). **Verify the `KUBECONFIG` path and the `runai` binary location
  in your own WSL environment** before constructing commands — these are operator-specific.
- In **Git Bash** (not WSL), prefix cluster-path commands with `MSYS_NO_PATHCONV=1` to stop
  `/hpi/...` from being mangled into a Windows path.

### 1a. Where the three CLIs actually live

Verified on this workstation **2026-09-15** — re-check before trusting, these are
operator-specific. Several of this repo's slash commands (`/ci-debug`, `/docs-review`,
`/new-feature`, `/pr-description`, `/review-openspec`, `/review-pr`) invoke `argo lint` without
saying where `argo` is; this table is the answer.

| Tool | Location | On PATH? |
|---|---|---|
| `argo` | `/usr/local/bin/argo` (WSL), v3.6.5 | ✅ in WSL. **Not installed on Windows at all** — no `scoop`/`choco` shim, nothing under `Program Files`, so it is absent from Git Bash and PowerShell. |
| `kubectl` | `/home/<user>/bin/kubectl` (WSL) **and** Docker Desktop's `/c/Program Files/Docker/Docker/resources/bin/kubectl`, v1.34.1 | ⚠️ WSL copy needs `export PATH=$HOME/bin:$PATH` — `$HOME/bin` is **not** on the non-login WSL PATH. Docker Desktop's copy *is* already on the Git Bash PATH. |
| `runai` | `/mnt/c/Users/<user>/runai` is on the WSL PATH | ✅ |

Because `argo` is WSL-only, every `argo` command must go through WSL, and the repo path
translates to `/mnt/c/repos/sleap-roots-pipeline`:

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
  cd /mnt/c/repos/sleap-roots-pipeline && argo lint --offline sleap-roots-pipeline.yaml'
```

> A non-login WSL shell (`wsl -e bash -c`) does **not** source `.profile`, so `$HOME/bin` is
> missing from `PATH`. Checking only `$HOME/.local/bin` and concluding a tool is uninstalled is
> a mistake that has actually been made here — search `$HOME/bin` too, or use `bash -lc`.

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

All commands take `-p busch-lab`. Use **`runai workspace`** (does not auto-terminate — you
clean up manually) rather than `runai training` (auto-terminates on completion).

| Operation | Command |
|---|---|
| List | `runai workspace list -p busch-lab` |
| Describe | `runai workspace describe <name> -p busch-lab` |
| Logs | `runai workspace logs <name> -p busch-lab --follow` |
| Exec | `runai workspace exec <name> -p busch-lab -- <cmd>` |
| Interactive shell | `runai workspace exec <name> -p busch-lab --stdin --tty -- /bin/bash` |
| Delete | `runai workspace delete <name> -p busch-lab` |

> Use `runai workspace exec`, **not** `kubectl exec` — RunAI manages its own auth layer.

## 4. Resource flags (CLI v2)

| Need | Flag |
|---|---|
| GPU (whole) | `--gpu-devices-request 1` |
| GPU (fractional, relative) | `--gpu-portion-request 0.5` (fraction of a GPU, 0-1) |
| GPU (fractional, absolute) | `--gpu-memory-request 8192M` (absolute amount, e.g. `1G`/`500M` — the predictor template annotates the pod-level `gpu-memory: "8192"` (MiB); using `8192M` here rather than `8G` since a bare `G` suffix may mean decimal `10^9` bytes elsewhere in this CLI, ~7% less than `8192` MiB/`8Gi` — this hasn't been exercised live to confirm which convention `--gpu-memory-request` actually follows, so `M` avoids the ambiguity rather than resolving it) |
| CPU cores | `--cpu-core-request 12` |
| Memory | `--cpu-memory-request 32G` |
| Always re-pull image | `--image-pull-policy Always` |

Only the **predictor** stage needs a GPU; `models-downloader` and `trait-extractor` are
CPU-only. The predictor template uses a **pod-level** `gpu-memory: "8192"` annotation with **no**
`nvidia.com/gpu` resource (fixed in
[issue #25](https://github.com/talmolab/sleap-roots-pipeline/issues/25) — it previously pinned an
inert *object-level* `gpu-fraction: "0.5"` annotation alongside a hard `nvidia.com/gpu: 1`, which
silently claimed a whole GPU regardless of the annotation). Annotation placement matters: only
`spec.templates[].metadata.annotations` (pod-level) is copied onto the pod by Argo — the
WorkflowTemplate object's own `metadata.annotations` (top of the file) never is.

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
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml && \
runai workspace submit srp-predict-test \
  -p busch-lab \
  --image registry.gitlab.com/salk-tm/sleap-roots-predict:<tag> \
  --image-pull-policy Always \
  --gpu-memory-request 8192M \
  --cpu-core-request 8 \
  --cpu-memory-request 16G \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/images_downloader_output,mount=/workspace/images_input,mount-propagation=HostToContainer \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/models_downloader_output,mount=/workspace/models_input,mount-propagation=HostToContainer \
  --host-path path=/hpi/hpi_dev/users/eberrigan/<dataset>/predictions,mount=/workspace/output,mount-propagation=HostToContainer,readwrite \
  -- bash -c '<predict entrypoint> /workspace/images_input /workspace/models_input /workspace/output; sleep infinity'"
```

`sleep infinity` keeps the pod alive after the run so you can `runai workspace exec` in to
inspect outputs. **Delete it when done** (`runai workspace delete srp-predict-test -p busch-lab`).

## 7. Preemptibility & GPU over-quota

**Preemptibility is set by `priorityClassName`, NOT by the `preemptible: "true"` annotation**
the templates carry (that annotation is a UI/convention breadcrumb only). Run:ai treats
`priorityClassName` **≥ 100 as non-preemptible**, **< 100 as preemptible**:

| Class | Preemptible? | Behaviour |
|---|---|---|
| `very-high` (150) | no | the top non-preemptible tier. **NOT the default for an unset `priorityClassName`** — that claim (present here until 2026-09-16) was never verified; pods observed with no class resolved to priority **0**. See the note below. |
| `high` (125), `build` (100) | no | must fit the project's **deserved quota**; never evicted |
| `interactive-preemptible` (75), `train` (50) | yes | may use **over-quota** GPUs; may be evicted → pair with `retryStrategy` |

Cluster-admin-confirmed naming (2026-08-06): the 125 tier's real name on this cluster is
**`high`**, not `inference` — corrected here after an earlier assumption. The predictor template
uses `high` (set 2026-08-06, per cluster-admin guidance, since trait-extractor has no
skip-if-done yet — see issue #37 — so avoiding eviction-triggered whole-batch recomputation
outweighs bursting above quota for now). The other three stage templates
(images-downloader/trait-extractor/write-back) stay on **`interactive-preemptible`** —
**never remove that field outright** — but not for the reason recorded here until 2026-09-16.
What an unset `priorityClassName` resolves to is **unverifiable with these credentials**
(`priorityclasses` is cluster-scoped and Forbidden to every `argo-user` identity), and Argo pods
observed with no class resolved to priority **0** — the lowest tier, below `train` (50), not
`very-high` (150). The old claim traces to PR #41, introduced alongside a `grep` rather than a
scheduling observation. So the risk of omitting the field is that the pod is **starved**, not that
it preempts GPU work; either way, declare it explicitly on every template. The predictor's GPU jobs typically run *within*
quota, so over-quota preemption isn't usually exercised — but if a GPU
pod is stuck `Pending`/`Unschedulable` with:

```
NonPreemptibleOverQuota: Non-preemptible workload is over quota. ... busch-lab quota is 2 GPUs,
while 2 GPUs are already allocated for non-preemptible pods. Use a preemptible workload to go over quota.
```

busch-lab's deserved quota is only **2 GPUs** (vs. talmo-lab's 20) — over-quota scheduling is far
more likely to actually happen here. Check current usage before submitting anything
non-preemptible (`kubectl get pods -n runai-busch-lab` — other jobs holding whole GPUs, not just
fractional ones, will block a fractional predictor pod from landing even though the memory math
looks fine).

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
| `argo: command not found` | `argo` is WSL-only here — see §1a. Not installed on Windows. |
| `argo lint --offline` "fails" on `sleap-roots-pipeline.yaml` | **The manifest is fine, and there IS a cluster-free way to lint it.** Offline lint *does* index sibling files passed on the same command line — it matches `templateRef` on **(namespace, name)**. The Workflow declares `namespace: runai-busch-lab` while the five templates declare none, so the lookup searches a namespace no template is indexed under and reports `couldn't find workflow template … in namespace "runai-busch-lab"` (exit **1**). Strip `metadata.namespace` from a **temp copy** and all six manifests resolve clean with no cluster (`scripts/lint_manifests.sh` does exactly this): `T=$(mktemp -d); cp sleap-roots-*.yaml "$T/"; sed -i '/^  namespace: runai-busch-lab$/d' "$T/sleap-roots-pipeline.yaml"; argo lint --offline "$T"/sleap-roots-*.yaml` → `✔ no linting errors found!` (verified 2026-09-15). Non-offline lint against `runai-busch-lab` with the `argo-user` kubeconfig also passes clean, but needs VPN — prefer the offline recipe for a gate that works anywhere. **Never delete that namespace line from the real file**: Bloom's dispatch depends on the manifest, and `runai_run_pipeline.sh` keeps its default equal to it. Credit: mechanism identified by the `#56`/PR #60 session; an earlier note here claimed offline lint ignored sibling files, which was wrong. |
| `kubectl auth can-i` returns a deprecation warning instead of `yes`/`no` | `kubectl` writes `Warning: Use tokens from the TokenRequest API...` to stderr, which interleaves with the verdict — a bare `\| head -1` captures the warning. Always filter: `kubectl auth can-i <verb> <resource> -n runai-busch-lab 2>/dev/null \| grep -E '^(yes\|no)'` |
| Need to know what an identity can do | `kubectl auth can-i` under that identity's kubeconfig. Note `argo-user` returns **no** for `get serviceaccounts`/`get secrets`, so you cannot read another ServiceAccount's Role from it — `bloom-workflow`'s RBAC is not verifiable this way (verified 2026-09-15). |

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
predict/traits). The same Salk cluster and WSL/KUBECONFIG pattern apply (project is
`busch-lab` here, not `mosquito-cfd`'s); workloads, images, and the GPU-on-predictor-only shape
are sleap-roots-specific.*
