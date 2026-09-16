# 🌱 sleap-roots-pipeline
Container orchestration for sleap-roots inference pipeline.

This repository defines a modular, GPU-accelerated image processing pipeline for plant root phenotyping using [SLEAP](https://sleap.ai), orchestrated via [Argo Workflows](https://argo-workflows.readthedocs.io).

The pipeline consists of four stages (A4, updated 2026-07-30 — `models-downloader` was dropped
earlier; models load in-process from the wandb registry):
1. **images-downloader** – Stages a batch of scans in from Bloom via `bloomctl`
2. **predictor** – Runs SLEAP predictions on the staged image sets (GPU)
3. **trait-extractor** – Extracts phenotypic traits from predictions
4. **write-back** – Writes the resulting traits back into Bloom via `bloomctl`

It is designed for reproducible, containerized execution using Kubernetes.

---

## 🧰 Requirements

Three separate CLIs with three different auth mechanisms. You don't need all three for every
task — see the table.

| Tool | Docs | Auth | Use it for |
|---|---|---|---|
| `argo` | [Argo CLI reference](https://argo-workflows.readthedocs.io/en/latest/cli/argo/) | `ARGO_TOKEN` + `ARGO_SERVER`, **or** `KUBECONFIG` (Kubernetes mode) | the production path: template registration, `argo submit`, `argo lint`, `argo logs` |
| `runai` | [Run:AI docs](https://run-ai-docs.nvidia.com/) | interactive SSO — `runai login remote-browser` | interactive/ad-hoc work: `runai workspace submit` / `logs` / `exec` |
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

**Which identity does each tool use?** `runai` uses your own SSO login; `argo` and `kubectl` use
the shared project `argo-user` kubeconfig. Bloom's backend submits as a third identity you don't
hold. See [Cluster identities](docs/cluster-identities.md) before wiring anything new — picking the
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
> `sleap-roots-pipeline.yaml` and exits non-zero. That's an offline-lint artifact — the DAG
> references its stages by `templateRef`, which needs a cluster to resolve. Lint without
> `--offline` for the real answer.

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
argo template create sleap-roots-images-downloader-template.yaml -n runai-busch-lab
argo template create sleap-roots-predictor-template.yaml -n runai-busch-lab
argo template create sleap-roots-trait-extractor-template.yaml -n runai-busch-lab
argo template create sleap-roots-write-back-template.yaml -n runai-busch-lab
```

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
argo logs <workflow-name> -n runai-busch-lab --tail 100
```

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
- If a task fails and `retryStrategy` is exhausted:
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