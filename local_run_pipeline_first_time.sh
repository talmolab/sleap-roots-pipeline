#!/bin/bash
set -euo pipefail

# Colors for better terminal output
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m' # No Color

# Workflow + template paths
WORKFLOW_FILE="sleap-roots-pipeline.yaml"
TEMPLATES=(
  "models-downloader-template.yaml"
  "sleap-roots-predictor-template.yaml"
  "sleap-roots-trait-extractor-template.yaml"
)

# Timestamped log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="workflow_logs_$TIMESTAMP.txt"

echo -e "${YELLOW}Registering WorkflowTemplates...${NC}"
for tmpl in "${TEMPLATES[@]}"; do
  echo -e "${GREEN}→ Applying $tmpl${NC}"
  kubectl apply -f "$tmpl" -n argo
done

echo -e "${YELLOW}Submitting Workflow...${NC}"
# Capture the workflow name from submission
WORKFLOW_NAME=$(argo submit "$WORKFLOW_FILE" --namespace argo --output name)
echo -e "${GREEN}✓ Submitted as: $WORKFLOW_NAME${NC}"

# Wait a few seconds to ensure pods start up
sleep 5

echo -e "${YELLOW}Streaming logs (also saving to $LOG_FILE)...${NC}"
# Stream logs and tee to a file
argo logs "$WORKFLOW_NAME" --namespace argo --follow | tee "$LOG_FILE"

echo -e "${GREEN}✓ Done! Logs saved to $LOG_FILE${NC}"
