#!/bin/bash
set -euo pipefail

# Color output
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m'

# Namespace for the GPU cluster
NAMESPACE="runai-tye-lab"

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
TEMPLATES=(
  "models-downloader-template.yaml"
  "sleap-roots-predictor-template.yaml"
  "sleap-roots-trait-extractor-template.yaml"
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
