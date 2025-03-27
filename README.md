# 🌱 sleap-roots-pipeline
Container orchestration for sleap-roots inference pipeline.

This repository defines a modular, GPU-accelerated image processing pipeline for plant root phenotyping using [SLEAP](https://sleap.ai), orchestrated via [Argo Workflows](https://argo-workflows.readthedocs.io).

The pipeline consists of three main steps:
1. **models-downloader** – Prepares model files for inference
2. **predictor** – Runs SLEAP predictions on input image sets
3. **trait-extractor** – Extracts phenotypic traits from predictions

It is designed for reproducible, containerized execution using Kubernetes.

---

## 🚀 Getting Started

### 🧰 Requirements

- GPU-enabled system with NVIDIA drivers
- Kubernetes cluster
- Argo Workflows installed (`argo` CLI + controller in cluster)
- Volumes exposed via WSL2 (`/run/desktop/mnt/host/...`) for Docker Desktop cluster on WSL2 only.

---

## 📦 Folder Structure

```text
.
├── sleap_roots_pipeline.yaml                # Main Argo Workflow definition
├── models-downloader-template.yaml          # WorkflowTemplate: downloads models
├── sleap-roots-predictor-template.yaml      # WorkflowTemplate: runs predictions
├── sleap-roots-trait-extractor-template.yaml# WorkflowTemplate: extracts traits
├── run_pipeline.sh                          # CLI tool to register & run pipeline
└── workflow_logs_<timestamp>.txt            # Log output saved per run
```

---

## 🛠 Configuring Volume Paths (Important!)

The workflow uses `hostPath` volumes to map local data directories into each container. **You must modify these paths to match your own setup.**

### 🔍 Where to change them:

See this block in [`sleap_roots_pipeline.yaml`](./sleap_roots_pipeline.yaml):

```yaml
volumes:
  - name: models-input-dir
    hostPath:
      path: /run/desktop/mnt/host/wsl/your/path/models_downloader_input
      type: Directory  # ❗️ Directory must exist
  - name: models-output-dir
    hostPath:
      path: /run/desktop/mnt/host/wsl/your/path/models_downloader_output
      type: Directory
  # ... and so on for images, predictions, traits
```

### ⚠️ hostPath & WSL2 Caveats

- Kubernetes will **fail to start a pod** if a `hostPath` volume with `type: Directory` does not exist.
- Docker Desktop (WSL2) exposes your Windows filesystem under `/run/desktop/mnt/host/...`.
- These paths must:
  - Be **pre-created on the host filesystem**
  - Be accessible via WSL2 and Kubernetes
- See [Kubernetes hostPath docs](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath) for behavior by `type`.
- This can be easilly adapted to other Kubernetes setups and will likely work better.

---

## 🔁 Running the Pipeline

1. **Create all required directories** on your host machine.

2. **Run the pipeline**:
   ```bash
   ./run_pipeline.sh
   ```

This will:
- Register workflow templates
- Submit the workflow
- Stream logs to your terminal
- Save logs to a file

---

## ⚙️ GPU Support

The predictor step requests a GPU:
   ```yaml
   resources:
     limits:
       nvidia.com/gpu: 1
   ```

To enable GPU inference in Docker Desktop:

1. Enable GPU in **Docker Desktop > Settings > Resources > Advanced**
2. Verify GPU works:
   ```bash
   docker run --gpus all nvidia/cuda:12.2.0-base-ubuntu20.04 nvidia-smi
   ```
3. Confirm Kubernetes node shows GPU:
   ```bash
   kubectl describe node docker-desktop | grep -A 5 "Capacity"
   ```

---

## 🐛 Troubleshooting

Check workflow status:

```bash
argo list -n <namespace>
argo get <workflow-name> -n <namespace>
argo logs <workflow-name> --log-options tail=100 -n <namespace>

```

To see pod logs:

```bash
kubectl get pods -n <namespace>
kubectl logs <pod-name> -n <namespace>
kubectk describe <pod-name> -n <namespace>
```

### Pod stuck in `PodInitializing`?
- Check that all directories specified in `hostPath` exist on the host and are accessible to Docker/Kubernetes.

### Pod unschedulable due to GPU?
- Make sure GPU is enabled in Docker Desktop and visible to Kubernetes (`nvidia.com/gpu` shows up in `kubectl describe node`).

---

## 📈 Resources

- [Argo Workflows Concepts](https://argo-workflows.readthedocs.io/en/latest/workflow-concepts/)
- [Kubernetes Volumes: hostPath](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath)
- [Argo DAG tutorial](https://argo-workflows.readthedocs.io/en/latest/walk-through/dag/)
- [Argo Workflow YAML schema](https://argo-workflows.readthedocs.io/en/latest/fields/#workflowspec)

---

## 🧪 License & Attribution

Developed as part of the [Salk Harnessing Plants Initiative](https://github.com/salk-harnessing-plants-initiative).
[SLEAP](https://github.com/talmolab/sleap) maintained by [talmolab](https://github.com/talmolab).  
Trait extraction and workflow architecture by Elizabeth B.