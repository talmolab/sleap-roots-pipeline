#!/bin/bash
set -euo pipefail

# NOTE: this launcher targets the in-cluster Argo Server (gpu-master:8888) and requires ARGO_TOKEN
# exported — it only works from a machine on the internal cluster LAN. The A4 PoC was NOT run this
# way; it was submitted in Kubernetes mode (no Argo Server) with the argo-user kubeconfig, which is
# also how the real four-stage end-to-end run (2026-07-30) was submitted:
#   export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
#   argo template update sleap-roots-images-downloader-template.yaml -n runai-busch-lab
#   argo template update sleap-roots-predictor-template.yaml         -n runai-busch-lab
#   argo template update sleap-roots-trait-extractor-template.yaml   -n runai-busch-lab
#   argo template update sleap-roots-write-back-template.yaml        -n runai-busch-lab
#   argo submit sleap-roots-pipeline.yaml --parameter scan-ids=<id1>,<id2> -n runai-busch-lab
# Use that path if gpu-master:8888 is unreachable from your box.
#
# NOTE: `runai-busch-lab` is shared by Bloom's staging AND production dispatch, distinguished only
# by an environment label stamped on each submitted Workflow. An `argo template update` here
# therefore affects both environments' future dispatches, not just your own next run.

# Color output
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m'

# Namespace for the GPU cluster. Must match sleap-roots-pipeline.yaml's metadata.namespace —
# if they disagree, this script registers templates into one namespace and submits into another.
# Override for a one-off submit into another project:
#   NAMESPACE=runai-talmo-lab ./runai_run_pipeline.sh
NAMESPACE="${NAMESPACE:-runai-busch-lab}"

# Argo Server in HTTP mode
export ARGO_SERVER=gpu-master:8888
export ARGO_HTTP1=true
export ARGO_SECURE=false
export ARGO_NAMESPACE="$NAMESPACE"

echo "Argo CLI configured for Argo Server at $ARGO_SERVER."
echo "Using namespace: $NAMESPACE"
echo "NOTE: Ensure ARGO_TOKEN is exported in your environment."
echo "NOTE: Confirm that volume paths in your workflow YAML are cluster-accessible."

# Workflow and template files
WORKFLOW_FILE="sleap-roots-pipeline.yaml"
# A4: models-downloader dropped — the warm predictor loads models in-process.
TEMPLATES=(
  "sleap-roots-images-downloader-template.yaml"
  "sleap-roots-predictor-template.yaml"
  "sleap-roots-trait-extractor-template.yaml"
  "sleap-roots-write-back-template.yaml"
)

# Log setup
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="workflow_logs_$TIMESTAMP.txt"

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
