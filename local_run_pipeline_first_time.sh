#!/bin/bash
set -euo pipefail

# Colors for better terminal output
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m' # No Color

# Workflow + template paths
# NOTE (2026-07-30): unlike the local-WSL2-*.yaml files, this script submits
# sleap-roots-pipeline.yaml (the cluster manifest) directly against a local "argo" namespace —
# it predates the local-WSL2-* naming convention and isn't in openspec/project.md's documented
# local-testing path. The A4 batch-DAG change (images-downloader/write-back, four stages) was
# validated on the real cluster only (see openspec/changes/add-per-batch-argo-workflow/), not via
# this script — local dev testing for that DAG shape is tracked separately in #21, still open.
# ⚠️ BROKEN for the current DAG as of 2026-09-16 (#56's exit-gate); tracked by #21, not fixed here.
# Two reasons, in the order they bite:
#   1. It applies these templates into namespace `argo` but submits the CLUSTER manifest, whose
#      `metadata.namespace: runai-busch-lab` WINS over `--namespace` (verified 2026-09-15). So it
#      fails on a namespace that doesn't exist on Docker Desktop, before any templateRef is tried.
#   2. If it got past that, ALL of its templateRefs would be unresolvable (the templates live in
#      `argo`, the Workflow looks in `runai-busch-lab`) — not just the new exit-gate.
# The TEMPLATES list below is also now incomplete: the DAG has FIVE templateRefs and this lists
# four, omitting sleap-roots-exit-gate-template.yaml. Deliberately left as-is — adding it would
# imply this path works. An earlier version of this comment claimed TEMPLATES "is updated so this
# doesn't hard-fail on a missing templateRef"; that was true for the four-stage DAG and is now false.
WORKFLOW_FILE="sleap-roots-pipeline.yaml"
TEMPLATES=(
  "sleap-roots-images-downloader-template.yaml"
  "sleap-roots-predictor-template.yaml"
  "sleap-roots-trait-extractor-template.yaml"
  "sleap-roots-write-back-template.yaml"
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
