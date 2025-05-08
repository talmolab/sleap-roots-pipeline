# 🌱 sleap-roots-pipeline
Container orchestration for sleap-roots inference pipeline.

This repository defines a modular, GPU-accelerated image processing pipeline for plant root phenotyping using [SLEAP](https://sleap.ai), orchestrated via [Argo Workflows](https://argo-workflows.readthedocs.io).

The pipeline consists of three main steps:
1. **models-downloader** – Prepares model files for inference
2. **predictor** – Runs SLEAP predictions on input image sets
3. **trait-extractor** – Extracts phenotypic traits from predictions

It is designed for reproducible, containerized execution using Kubernetes.

---

## 🧰 Requirements

- Kubernetes cluster with GPU support (e.g., Run:AI GPU cluster)
- [`argo` CLI](https://argo-workflows.readthedocs.io/en/stable/cli/) installed
- A valid Argo Bearer token exported to your shell (`ARGO_TOKEN`)
- Storage volumes mounted or available via `hostPath`
- (Optional for local testing) Docker Desktop with WSL2 integration

---

## 🛠️ Setup and Cluster Access

### ✅ Run:AI login and kubernetes context
```bash
runai login remote-browser 
runai whoami
```

```bash
kubectl config use-context system:node:gpu-master@kubernetes
kubectl config get-contexts
```

### 🔑 Token check

```bash
kubectl --server=https://10.7.30.173:6443 \
  --token="<your-token>" \
  --insecure-skip-tls-verify \
  --namespace=runai-talmo-lab \
  get pods
```

### ⚙️ Argo CLI Configuration

```bash
# Argo Server running in HTTP mode
export ARGO_SERVER=gpu-master:8888
export ARGO_HTTP1=true
export ARGO_SECURE=false
export ARGO_NAMESPACE=runai-talmo-lab
export ARGO_TOKEN="Bearer <your-token>"

echo "Argo CLI configured for Argo Server at gpu-master:8888 using token auth."
```

---

## 📦 Folder Structure

```text
.
├── sleap-roots-pipeline.yaml                    # Main Argo Workflow definition
├── models-downloader-template.yaml              # WorkflowTemplate: downloads models
├── sleap-roots-predictor-template.yaml          # WorkflowTemplate: runs predictions
├── sleap-roots-trait-extractor-template.yaml    # WorkflowTemplate: extracts traits
├── runai_run_pipeline.sh                        # GPU cluster launcher for Run:AI (runai-tye-lab)
├── local_run_pipeline_first_time.sh             # Local WSL2/Docker Desktop test runner
├── local-WSL2-*.yaml                            # Local-only templates and workflow configs
└── workflow_logs_<timestamp>.txt                # Log output saved per run
```

---

## 🚀 Running on the GPU Cluster (`runai-tye-lab`)

You can run the pipeline on the Run:AI GPU cluster using the Argo Server exposed at `gpu-master:8888`.

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

The predictor step requires a GPU:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```

Example to test GPU support.

```bash
docker run --gpus all nvidia/cuda:12.2.0-base-ubuntu20.04 nvidia-smi
kubectl describe node docker-desktop | grep -A 5 "Capacity"
```

**Note**: GPU support in Kubernetes with WSL2 backend is not supported. Use the CPU for testing locally.
---

## 📋 Creating WorkflowTemplates (One-Time per Namespace)

```bash
argo template create models-downloader-template.yaml -n runai-talmo-lab
argo template create sleap-roots-predictor-template.yaml -n runai-talmo-lab
argo template create sleap-roots-trait-extractor-template.yaml -n runai-talmo-lab
```

Check with:

```bash
argo template list -n runai-talmo-lab
```

---

## 🚀 Submitting Workflows

```bash
argo list
argo submit sleap-roots-pipeline.yaml --watch
```

---

## 🐛 Troubleshooting

```bash
argo list -n runai-talmo-lab
argo get <workflow-name> -n runai-talmo-lab
argo logs <workflow-name> -n runai-talmo-lab --log-options tail=100
```

Check pod logs:

```bash
kubectl get pods -n runai-talmo-lab
kubectl logs <pod-name> -n runai-talmo-lab
kubectl describe pod <pod-name> -n runai-talmo-lab
```

---

## 🧠 Run:AI-Specific Configuration in WorkflowTemplates

Your `WorkflowTemplates` include annotations and labels that are interpreted by the Run:AI scheduler to manage GPU allocation and job priority.

### 🔖 `annotations`

```yaml
annotations:
  gpu-fraction: "0.5"
  preemptible: "true"
```

- **`gpu-fraction`**: Requests a fractional GPU (e.g., 0.5 of a full GPU). Useful for light inference workloads. Run:AI schedules jobs with this annotation accordingly.
- **`preemptible`**: Allows the job to be evicted if GPU capacity is needed for higher-priority jobs. Recommended to combine with a `retryStrategy` to resubmit the task if it's interrupted.

### 🏷️ `labels`

```yaml
labels:
  project: tye-lab
```

- **`project`**: Used by Run:AI for usage tracking and quota enforcement. Should match a defined project name on the cluster.

### ⚙️ `resources.limits`

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```

- Specifies that a GPU is required. Run:AI combines this with `gpu-fraction` to handle fractional allocation.

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
  - When resubmitting the workflow, **Argo does not resume from the failed step by default** — it starts fresh unless you manually skip steps or use [artifacts/results to track progress](https://argo-workflows.readthedocs.io/en/latest/retry-failed-steps/).

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