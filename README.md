# 🌱 sleap-roots-pipeline
Container orchestration for sleap-roots inference pipeline.

This repository defines a modular, GPU-accelerated image processing pipeline for plant root phenotyping using [SLEAP](https://sleap.ai), orchestrated via [Argo Workflows](https://argo-workflows.readthedocs.io).

The pipeline consists of four processing stages followed by a terminal gate task (A4, updated
2026-09-15 — `models-downloader` was dropped earlier; models load in-process from the wandb
registry):
1. **images-downloader** – Stages a batch of scans in from Bloom via `bloomctl`
2. **predictor** – Runs SLEAP predictions on the staged image sets (GPU)
3. **trait-extractor** – Extracts phenotypic traits from predictions
4. **write-back** – Writes the resulting traits back into Bloom via `bloomctl`
5. **exit-gate** – Re-derives the Workflow's final phase from the producers' real exit codes
   (see *DAG Behavior and Step Failures* below)

It is designed for reproducible, containerized execution using Kubernetes.

---

## 🧰 Requirements

Three separate CLIs with three different auth mechanisms. You don't need all three for every
task — see the table.

| Tool | Docs | Auth | Use it for |
|---|---|---|---|
| `argo` | [Argo CLI reference](https://argo-workflows.readthedocs.io/en/latest/cli/argo/) | `ARGO_TOKEN` + `ARGO_SERVER`, **or** `KUBECONFIG` (Kubernetes mode) | the production path: template registration, `argo submit`, `argo lint`, `argo logs` |
| `runai` | [Run:AI docs](https://run-ai-docs.nvidia.com/) | `KUBECONFIG` **and** interactive SSO — `runai login remote-browser` | interactive/ad-hoc work: `runai workspace submit` / `logs` / `exec` |
| `kubectl` | [kubectl install](https://kubernetes.io/docs/tasks/tools/) | `KUBECONFIG` | pod inspection, `kubectl auth can-i`, diagnosing failures |

Also required:

- **Salk VPN** (or on-campus network). The cluster API and Argo Server are unreachable from
  outside.
- **A POSIX shell, not PowerShell.** Every cluster command here assumes an explicit `KUBECONFIG`
  export. On this project's workstation `argo` is installed in WSL only, so `argo` commands run
  through WSL; `kubectl` is available both in WSL and from Docker Desktop on the Windows PATH. See
  [the runai skill](.claude/skills/runai/SKILL.md) for exact locations. In Git Bash, prefix
  cluster-path commands with `MSYS_NO_PATHCONV=1` so `/hpi/...` isn't rewritten into a Windows
  path.
- A GPU-capable Kubernetes cluster and storage available via `hostPath`.
- (Optional, local testing only) Docker Desktop with WSL2 integration — CPU-only, see
  [Local Testing](#-local-testing-docker-desktop--wsl2).

**Which identity does each tool use?** `runai` needs *both* the shared project `argo-user`
kubeconfig and your own RunAI SSO login; `argo` and `kubectl` need only the kubeconfig. Bloom's
backend submits as a third identity you don't hold. See [Cluster identities](docs/cluster-identities.md) before wiring anything new — picking the
wrong one produces failures that don't look like permission errors.

---

## 🛠️ Setup and Cluster Access

> This section covers the **operator** path (`argo-user`). If you're wiring Bloom-side dispatch
> instead, you likely need no new credential at all — see
> [Cluster identities → Getting access](docs/cluster-identities.md#getting-access-new-bloom-side-developer).

### ✅ Run:AI login (interactive path)

```bash
runai login remote-browser
runai whoami
```

### ⚙️ Argo CLI — Kubernetes mode (what the launcher uses)

Point `KUBECONFIG` at the `argo-user` kubeconfig. No `ARGO_TOKEN` is needed in this mode, and
`templateRef`s resolve against the registered templates:

```bash
export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
kubectl config get-contexts
argo list -n runai-busch-lab
argo lint sleap-roots-pipeline.yaml    # expect: no linting errors found!
```

> `argo lint --offline` reports a `couldn't find workflow template ...` error on
> `sleap-roots-pipeline.yaml` and exits non-zero — but **not because it needs a cluster**. Offline
> lint *does* resolve `templateRef` from the files you pass it; it matches on **(namespace, name)**,
> and this Workflow declares `metadata.namespace` while the templates declare none, so the lookup
> misses. Strip that line from a **temp copy** and all six manifests resolve with no cluster and no
> VPN:
>
> `scripts/lint_manifests.sh` does exactly that — it lints a temp copy with the namespace stripped,
> never touching the tracked files:
>
> ```bash
> bash scripts/lint_manifests.sh      # from WSL, where argo is installed → no linting errors found!
> ```
>
> **Never strip that line from the real file** — Bloom's dispatch reads the manifest and the
> launcher keeps its namespace equal to it. Non-offline lint against `runai-busch-lab` needs VPN
> **and** every referenced template to be registered there already, so it will fail until
> `sleap-roots-exit-gate-template` is `argo template create`d; prefer the script for a gate that
> works anywhere. Note what offline lint can and cannot see: it catches a `templateRef` with no
> matching **file in this repo**, and says nothing about what is registered in the **cluster** —
> that is `scripts/check_cluster_drift.sh`'s job.
>
> This is the only check that cross-resolves `templateRef` — i.e. the only one that catches a DAG
> task pointing at a template nobody registered. There is no CI in this repo, so it runs only when
> you run it.

### 🔑 Token check

```bash
kubectl --server=https://10.7.30.173:6443 \
  --certificate-authority=/path/to/ca.crt \
  --token="<your-token>" \
  --namespace=runai-busch-lab \
  get pods
```

Prefer `--certificate-authority` over `--insecure-skip-tls-verify`: skipping verification removes
the protection that makes sending a bearer token safe.

Never commit the token or the CA file. `.gitignore` covers the obvious filenames (`*token*.txt`,
`*.token`, `*.crt`, `*.pem`, `*kubeconfig*`, `credentials*.txt`) — but treat that as a backstop,
not a guarantee: it only matches those patterns, and this repo is public. Keep credentials outside
the working tree.

If you need the endpoint for a different cluster or context, read it from your own kubeconfig
rather than copying it, since it travels with the credential:

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

### ⚙️ Argo CLI — Argo Server mode

Use this only if `gpu-master:8888` is reachable from your machine. Never commit a token value:

```bash
# Argo Server running in HTTP mode
export ARGO_SERVER=gpu-master:8888
export ARGO_HTTP1=true
export ARGO_SECURE=false
export ARGO_NAMESPACE=runai-busch-lab
export ARGO_TOKEN="Bearer <your-token>"

echo "Argo CLI configured for Argo Server at gpu-master:8888 using token auth."
```

---

## 📦 Folder Structure

```text
.
├── sleap-roots-pipeline.yaml                    # Main Argo Workflow definition
├── sleap-roots-images-downloader-template.yaml  # WorkflowTemplate: stages scans in via bloomctl
├── sleap-roots-predictor-template.yaml          # WorkflowTemplate: runs predictions
├── sleap-roots-trait-extractor-template.yaml    # WorkflowTemplate: extracts traits
├── sleap-roots-write-back-template.yaml         # WorkflowTemplate: writes traits back via bloomctl
├── sleap-roots-exit-gate-template.yaml          # WorkflowTemplate: fails the run on a crash-class exit
├── runai_run_pipeline.sh                        # GPU cluster launcher for Run:AI (runai-busch-lab)
├── local_run_pipeline_first_time.sh             # Local WSL2/Docker Desktop test runner
├── local-WSL2-*.yaml                            # Local-only templates and workflow configs
└── workflow_logs_<timestamp>.txt                # Log output saved per run
```

---

## 🚀 Running on the GPU Cluster (`runai-busch-lab`)

You can run the pipeline on the Run:AI GPU cluster using the Argo Server exposed at `gpu-master:8888`.

> `runai-talmo-lab` remains live on the cluster but is no longer this pipeline's target (changed
> 2026-08-13). `runai_run_pipeline.sh` hard-codes `runai-busch-lab`, and **there is no environment
> variable to override it** — setting `NAMESPACE` has no effect. That is deliberate: `argo submit
> -n <ns>` does not redirect a submission (the manifest's `metadata.namespace` wins), so an
> override could only have moved the template registrations away from the namespace the Workflow
> still runs in. Targeting another project means editing `metadata.namespace` in the manifest and
> registering that project's templates *and* secrets first.
>
> ⚠️ This namespace is shared by Bloom's staging **and** production dispatch. An
> `argo template create`/`update` here affects both environments' future runs — see
> [Cluster identities](docs/cluster-identities.md).

### ▶️ One-Time Setup

```bash
chmod +x runai_run_pipeline.sh
```

Ensure that `ARGO_TOKEN` is exported and you have access to the cluster.

### ▶️ Run the Pipeline

```bash
./runai_run_pipeline.sh
```

This script will:
- Automatically create or update your `WorkflowTemplates`
- Submit the pipeline as a `Workflow`
- Stream logs to your terminal
- Save logs to `workflow_logs_<timestamp>.txt`

---

## 🧪 Local Testing (Docker Desktop + WSL2)

You can test the pipeline locally using Docker Desktop and WSL2. This setup is useful for rapid iteration on template logic and file handling.

### ▶️ Run Locally

```bash
./local_run_pipeline_first_time.sh
```

This uses the `local-WSL2-*` templates and pipeline files.

---

## 🛠 Configuring Volume Paths

You **must** update volume paths in the workflow YAML to point to valid directories on your machine or cluster node.

```yaml
volumes:
  - name: models-input-dir
    hostPath:
      path: /run/desktop/mnt/host/wsl/your/path/models_downloader_input
      type: Directory
```

> ⚠️ Kubernetes will fail pod startup if a `hostPath` volume with `type: Directory` does not already exist.

---

## ⚙️ GPU Support

The predictor step requires a GPU. **Local/WSL2 dev** (`local-WSL2-sleap-roots-predictor-template.yaml`)
still uses the standard Kubernetes device-plugin resource:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```

**On the cluster**, the predictor template (`sleap-roots-predictor-template.yaml`) instead uses a
RunAI pod-level `gpu-memory` annotation with no `nvidia.com/gpu` resource at all — see
"Run:AI-Specific Configuration in WorkflowTemplates" below.

Example to test GPU support.

```bash
docker run --gpus all nvidia/cuda:12.2.0-base-ubuntu20.04 nvidia-smi
kubectl describe node docker-desktop | grep -A 5 "Capacity"
```

**Note**: GPU support in Kubernetes with WSL2 backend is not supported. Use the CPU for testing locally.
---

## 📋 Creating WorkflowTemplates (One-Time per Namespace)

```bash
argo template create sleap-roots-exit-gate-template.yaml -n runai-busch-lab
argo template create sleap-roots-images-downloader-template.yaml -n runai-busch-lab
argo template create sleap-roots-predictor-template.yaml -n runai-busch-lab
argo template create sleap-roots-trait-extractor-template.yaml -n runai-busch-lab
argo template create sleap-roots-write-back-template.yaml -n runai-busch-lab
```

> Register `sleap-roots-exit-gate-template.yaml` **before** submitting the workflow: the DAG
> references it, so submission fails on an unresolvable `templateRef` if it is missing. `create`
> rather than `update` the first time — `update` errors on a template that does not exist yet.

Check with:

```bash
argo template list -n runai-busch-lab
```

---

## 🚀 Submitting Workflows

```bash
argo list
argo submit sleap-roots-pipeline.yaml --parameter scan-ids=<id1>,<id2> --watch
```

---

## 🐛 Troubleshooting

```bash
argo list -n runai-busch-lab
argo get <workflow-name> -n runai-busch-lab
argo logs <workflow-name> -n runai-busch-lab --tail 100 2>&1
```

> ⚠️ **Logs need the `bloom-pipeline` kubeconfig, not `argo-user`.** `argo-user` is denied
> `get pods --subresource=log`, so under the operator kubeconfig every command below returns no log
> output at all. Worse, **`argo logs` exits `0` when it is denied** — it writes the `Forbidden` to
> *stderr* only and leaves stdout empty, so `argo logs <wf> | grep ...` looks exactly like a
> successful run that logged nothing, and `$?` will not tell you otherwise. Always capture `2>&1`.
> To actually read logs:
>
> ```bash
> export KUBECONFIG=~/.kube/kubeconfig-bloom-pipeline-busch-lab.yaml
> kubectl logs <pod-name> -n runai-busch-lab
> ```
>
> This is the failure the identity note above warns about — it does not look like a permission
> error. See [Cluster identities](docs/cluster-identities.md) for the measured capability matrix.
> Nobody can `kubectl exec`; use `runai workspace exec` against your own SSO session instead.

Check pod logs:

```bash
kubectl get pods -n runai-busch-lab
kubectl logs <pod-name> -n runai-busch-lab
kubectl describe pod <pod-name> -n runai-busch-lab
```

---

## 🧠 Run:AI-Specific Configuration in WorkflowTemplates

Your `WorkflowTemplates` include annotations and labels that are interpreted by the Run:AI scheduler to manage GPU allocation and job priority.

**Important: annotation placement matters.** Argo only copies **pod-level**
`spec.templates[].metadata.annotations` onto the actual pod — annotations on the
`WorkflowTemplate` object's own `metadata` (top of the file) are never copied anywhere and have
no effect. This was the root cause of
[issue #25](https://github.com/talmolab/sleap-roots-pipeline/issues/25): an object-level
`gpu-fraction` annotation silently did nothing while the container's `nvidia.com/gpu: 1` limit
claimed a whole GPU regardless.

### 🔖 `annotations`

Object-level (`WorkflowTemplate.metadata.annotations`) — a UI/convention breadcrumb only, **not**
copied to the pod:

```yaml
annotations:
  preemptible: "true"
```

- **`preemptible`**: inert breadcrumb; actual preemptibility is governed by `priorityClassName`
  (see below), not this annotation.

Pod-level (`spec.templates[<name>].metadata.annotations`) — this is what Run:AI's scheduler
actually reads:

```yaml
annotations:
  gpu-memory: "8192"
```

- **`gpu-memory`**: requests an absolute amount of GPU memory (MiB) rather than a whole GPU —
  multiple pods can then share one physical GPU. RunAI also supports a relative `gpu-fraction`
  (e.g. `"0.5"`) annotation instead; this repo uses the absolute `gpu-memory` form, sized from a
  real measured VRAM trace (see `docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`)
  — precision RunAI's own docs recommend over a flat percentage.

### 🏷️ `labels`

```yaml
labels:
  project: busch-lab
```

- **`project`**: Used by Run:AI for usage tracking and quota enforcement. Should match a defined project name on the cluster.

### ⚙️ `resources.limits`

The predictor template sets **no** `nvidia.com/gpu` resource — GPU access comes entirely from the
pod-level `gpu-memory` annotation above. `nvidia.com/gpu` and RunAI's fractional/absolute-memory
annotations are mutually exclusive: including both makes RunAI treat the request as a whole GPU
and ignore the annotation (this combination is exactly what caused #25).

---

## 🔄 How the Workflow and Templates Work Together

The file `sleap-roots-pipeline.yaml` defines the **Argo Workflow**. It serves as the entry point for running the pipeline.

Inside it, you'll see a `DAG` template that references external steps using `templateRef`. These templates — defined separately — encapsulate logic for downloading models, running inference, and extracting traits.

```yaml
- name: predictor
  templateRef:
    name: sleap-roots-predictor-template
    template: sleap-roots-predictor
```

This allows you to version, share, and reuse components across workflows.

---

## 📐 DAG Behavior and Step Failures

Argo’s `DAG` execution has these key properties:

- **Task dependencies** are enforced using the `dependencies:` field.
- **All steps run in parallel** where possible, unless blocked by a dependency.
- **Retries** are configured per step using `retryStrategy`. This is necessary for handling failures like preemptions or transient errors.
- **A partially-failing images-downloader no longer kills the run** (`sleap-roots-pipeline-#56`). The three producer stages — images-downloader, predictor, trait-extractor — carry `continueOn: {failed: true}`, so a stage that completes its batch while isolating per-scan failures does not stop the DAG.
  - ⚠️ **This currently delivers the intended end-to-end outcome for images-downloader only.** A partial *predictor* or *trait-extractor* leaves the failed scans listed in `run_manifest.json`, so write-back reports them as missing, marks them retriable, exits non-zero and retries to exhaustion — the Workflow still ends `Failed` and the gate never runs. Tracked as [bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859); until it lands, read #56 as fixing the stage-in case.
  - ⚠️ **bloom#859 is a latch, not a per-run inconvenience.** `write_run_manifest` unions this run's `ok`/`skipped` keys into any existing `run_manifest.json` and **never prunes** (`download_for_predict.py`), and the three `a4_poc` directories are fixed, shared by prod/staging/manual, and have nothing that cleans them ([#63](https://github.com/talmolab/sleap-roots-pipeline/issues/63)). So a scan that stages in fine and then fails at predict or traits stays in the manifest **permanently** with no `result.json` — and write-back reports a manifest key with no envelope as a batch failure. Consequence: **every subsequent run over those directories exits non-zero at write-back and ends `Failed`, including runs whose own scans all succeeded**, after having already ingested them. This PR is what makes it reachable: previously a partial producer killed the DAG so write-back never ran. Manual remedy until bloom#859 lands: prune or delete `run_manifest.json` in all three directories. Root cause is shared with [#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37) and bloom#703 — per-run path isolation was deliberately rejected (it would break the skip-if-done dedup the whole program relies on), so the manifest, not the path, is what needs per-run identity.
  - Producers signal this with a distinct exit code: **`0`** = every scan succeeded, **`3`** = the batch ran to completion but some scans isolated-failed. Anything else (`1` crash, `2` usage error, `143` SIGTERM) is crash-class.
  - The terminal **`exit-gate`** task re-derives the Workflow's final phase from those real exit codes: it passes only if every producer reported `0` or `3`, and fails the Workflow otherwise. This is what stops `continueOn` from silently reporting an exhausted-retry crash as success — `continueOn` keys only on a node's *phase*, not its exit code.
  - A stage whose pod is **deleted out from under Argo** (preemption — `markNodeError`, "pod deleted") produces an `Error` node, which `continueOn` deliberately does **not** cover, so the DAG stops there and the Workflow ends `Failed`. A pod that **never starts** is a different and worse case: at v3.6.7 `assessNodeStatus` maps `PodPending` unconditionally to `NodePending`, so `ImagePullBackOff` or a failed `hostPath` mount stays `Pending` — not `Error`, not `Failed` — and neither `retryStrategy` nor `continueOn` applies, so the workflow **hangs** rather than failing. The `exit-gate` template carries a `timeout` for exactly this reason, since as the DAG's only leaf it is where such a hang would strand an otherwise-complete batch; the four stage templates do not, so a `Pending` producer still hangs indefinitely.
- **A crash does not stop the DAG either.** `continueOn` keys on node phase, not exit code, so a crashed images-downloader still schedules the GPU predictor, trait-extraction and write-back before the gate concludes. Downstream stages are scoped by `run_manifest.json`, which is **cumulative across every run that shares the stage directories** — so on a crash path they may act on a previous run's scan set, and write-back may record per-scan outcomes, before the Workflow is declared `Failed`. A `Failed` Workflow therefore does not imply nothing was written.
- ⚠️ **A green Workflow does not mean every scan succeeded.** A partial run is `Succeeded` by design. Check `cyl_pipeline_runs.done_count` / `failed_count` for the real per-scan outcome. (The run's own status reads `complete` rather than `partial` until [bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857) lands.) The gate reports whether the machinery ran, not whether any scan was processed: it mounts no volumes, so it cannot observe whether output landed. The outcome for a zero-scan or zero-staged batch depends on what is already present in the shared input directory and is **not yet characterised** — do not rely on it either way until it is measured.
- If write-back fails, or the gate rejects a crash-class exit:
  - The **entire workflow fails**.
  - When resubmitting the workflow, **Argo does not resume from the failed step by default** — it starts fresh unless you manually skip steps or use artifacts/results to track progress (see [retries](https://argo-workflows.readthedocs.io/en/latest/retries/) and [retrying failed or errored steps](https://argo-workflows.readthedocs.io/en/latest/walk-through/retrying-failed-or-errored-steps/)).

> For full resumability between steps, consider writing success markers to disk or using `workflow.taskResults` to detect completed stages.

---

## 📈 References

- [Argo Workflows Concepts](https://argo-workflows.readthedocs.io/en/latest/workflow-concepts/)
- [Argo DAG Example](https://argo-workflows.readthedocs.io/en/latest/walk-through/dag/)
- [Kubernetes Volumes: hostPath](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath)
- [Argo YAML Field Reference](https://argo-workflows.readthedocs.io/en/latest/fields/)

---

## 🧪 License & Attribution

Developed as part of the [Salk Harnessing Plants Initiative](https://github.com/salk-harnessing-plants-initiative).  
[SLEAP](https://github.com/talmolab/sleap) maintained by [talmolab](https://github.com/talmolab).  
Trait extraction and workflow architecture by **Elizabeth B.**