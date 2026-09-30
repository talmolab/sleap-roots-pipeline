#!/bin/bash
set -euo pipefail

# NOTE: this launcher targets the in-cluster Argo Server (gpu-master:8888) and requires ARGO_TOKEN
# exported — it only works from a machine on the internal cluster LAN. The A4 PoC was NOT run this
# way; it was submitted in Kubernetes mode (no Argo Server) with the argo-user kubeconfig, which is
# also how the real four-stage end-to-end run (2026-07-30) was submitted:
#   export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
#   kubectl create -f sleap-roots-pipeline-semaphores.yaml             # first, once (#98)
#   argo template create sleap-roots-exit-gate-template.yaml         -n runai-busch-lab
#   argo template update sleap-roots-images-downloader-template.yaml -n runai-busch-lab
#   argo template update sleap-roots-predictor-template.yaml         -n runai-busch-lab
#   argo template update sleap-roots-trait-extractor-template.yaml   -n runai-busch-lab
#   argo template update sleap-roots-write-back-template.yaml        -n runai-busch-lab
#   argo submit sleap-roots-pipeline.yaml --parameter scan-ids=<id1>,<id2> -n runai-busch-lab
# Use that path if gpu-master:8888 is unreachable from your box.
# `create`, not `update`, for the exit-gate (#56) the first time: `update` errors on a template
# that does not exist yet. Register it BEFORE submitting any five-task DAG, or submission fails
# on an unresolvable templateRef.
#
# NOTE: `runai-busch-lab` is shared by Bloom's staging AND production dispatch, distinguished only
# by an environment label stamped on each submitted Workflow. An `argo template update` here
# therefore affects both environments' future dispatches, not just your own next run.

# Color output
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m'

# Namespace for the GPU cluster. Keep this equal to sleap-roots-pipeline.yaml's
# metadata.namespace — if they disagree, this script registers templates into one namespace while
# the Workflow still lands in the other.
#
# Deliberately NOT overridable by an environment variable. An earlier revision offered
# NAMESPACE=<other> and it could not work: verified 2026-09-15 that `argo submit -n <other>` does
# NOT redirect the submission — the manifest's metadata.namespace wins (`argo submit
# --server-dry-run -n runai-talmo-lab -o json` → metadata.namespace = runai-busch-lab). All an
# override changed was the -n on `argo template create/update`, i.e. it would publish this
# pipeline's templates into a different project than the one the Workflow runs in. To target
# another project, edit metadata.namespace in the manifest too, and register the templates and
# secrets there first.
NAMESPACE="runai-busch-lab"

# Argo Server in HTTP mode
export ARGO_SERVER=gpu-master:8888
export ARGO_HTTP1=true
export ARGO_SECURE=false
export ARGO_NAMESPACE="$NAMESPACE"

echo "Argo CLI configured for Argo Server at $ARGO_SERVER."
echo "Using namespace: $NAMESPACE"
echo "NOTE: Ensure ARGO_TOKEN is exported in your environment."
echo "NOTE: kubectl + a working KUBECONFIG are also needed (semaphore ConfigMap, #98)."
echo "NOTE: Confirm that volume paths in your workflow YAML are cluster-accessible."

# Workflow and template files
WORKFLOW_FILE="sleap-roots-pipeline.yaml"
# A4: models-downloader dropped — the warm predictor loads models in-process.
TEMPLATES=(
  "sleap-roots-images-downloader-template.yaml"
  "sleap-roots-predictor-template.yaml"
  "sleap-roots-trait-extractor-template.yaml"
  "sleap-roots-write-back-template.yaml"
  # #56: the DAG's terminal exit-code gate. Must be registered before any five-task DAG is
  # submitted, or submission fails on an unresolvable templateRef.
  "sleap-roots-exit-gate-template.yaml"
)

# Log setup
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="workflow_logs_$TIMESTAMP.txt"

# #98: the predictor and images-downloader templates acquire slots from this ConfigMap; semantics,
# deploy order and safe retuning are in the header of sleap-roots-pipeline-semaphores.yaml. Create
# it only if absent and never update it, so a manual run cannot undo an operator's live retune.
# Abort if it cannot be read or is incomplete: an incomplete one makes every gated node Error. This
# is the launcher's only kubectl use -- the Argo Server it otherwise talks to has no ConfigMap API --
# so it needs a working KUBECONFIG (in WSL, kubectl lives in $HOME/bin).
SEMAPHORES_FILE="sleap-roots-pipeline-semaphores.yaml"
SEMAPHORES_CM="sleap-roots-pipeline-semaphores"
SEMAPHORE_KEYS=("pipeline-gpu" "pipeline-stage-in")
if ! command -v kubectl >/dev/null 2>&1; then
  echo -e "${RED}✗ kubectl not found; it is needed to ensure $SEMAPHORES_CM exists (in WSL: export PATH=\$HOME/bin:\$PATH). No template registered.${NC}" >&2
  exit 1
fi
echo "kubectl context for the semaphore ConfigMap: $(kubectl config current-context 2>/dev/null || echo '<none>')"
if ! existing=$(kubectl get configmap "$SEMAPHORES_CM" -n "$NAMESPACE" --ignore-not-found -o name); then
  echo -e "${RED}✗ Could not read ConfigMap $SEMAPHORES_CM in $NAMESPACE (check KUBECONFIG/VPN). No template registered.${NC}" >&2
  exit 1
fi
if [ -z "$existing" ]; then
  echo -e "${YELLOW}+ Creating semaphore ConfigMap: $SEMAPHORES_CM${NC}"
  kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"
else
  for key in "${SEMAPHORE_KEYS[@]}"; do
    if ! value=$(kubectl get configmap "$SEMAPHORES_CM" -n "$NAMESPACE" -o "jsonpath={.data.$key}"); then
      echo -e "${RED}✗ Could not read '$key' from $SEMAPHORES_CM. No template registered.${NC}" >&2
      exit 1
    fi
    if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
      echo -e "${RED}✗ $SEMAPHORES_CM has no valid '$key' (got '$value'); every gated node would Error. No template registered.${NC}" >&2
      exit 1
    fi
  done
  echo -e "${GREEN}✓ $SEMAPHORES_CM exists with valid limits; leaving them as they are${NC}"
fi

echo -e "${YELLOW}Registering WorkflowTemplates in namespace '$NAMESPACE'...${NC}"
for tmpl_file in "${TEMPLATES[@]}"; do
  # Extract base name and strip the .yaml extension
  tmpl_name=$(basename "$tmpl_file" .yaml)

  echo -e "${GREEN}→ Checking template: $tmpl_name${NC}"

  if argo template get "$tmpl_name" -n "$NAMESPACE" &>/dev/null; then
    echo -e "${YELLOW}↺ Updating existing template: $tmpl_name${NC}"
    argo template update "$tmpl_file" -n "$NAMESPACE"
  else
    echo -e "${YELLOW}+ Creating new template: $tmpl_name${NC}"
    argo template create "$tmpl_file" -n "$NAMESPACE"
  fi
done

echo -e "${YELLOW}Submitting Workflow to namespace '$NAMESPACE'...${NC}"
WORKFLOW_NAME=$(argo submit "$WORKFLOW_FILE" -n "$NAMESPACE" --output name)
echo -e "${GREEN}✓ Submitted as: $WORKFLOW_NAME${NC}"

sleep 5

echo -e "${YELLOW}Streaming logs (also saving to $LOG_FILE)...${NC}"
argo logs "$WORKFLOW_NAME" -n "$NAMESPACE" --follow | tee "$LOG_FILE"

echo -e "${GREEN}✓ Done! Logs saved to $LOG_FILE${NC}"
