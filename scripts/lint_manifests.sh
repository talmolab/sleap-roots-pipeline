#!/usr/bin/env bash
# Run `argo lint` over the Workflow AND every WorkflowTemplate it references, together, offline.
#
# WHY THIS WRAPPER EXISTS — the obvious command does not work on this repo's manifests:
#
#     argo lint --offline sleap-roots-pipeline.yaml sleap-roots-*-template.yaml
#     ✖ templates.pipeline.tasks.images-downloader couldn't find workflow template
#       "sleap-roots-images-downloader-template" in namespace "runai-busch-lab"
#
# `--offline` resolves a `templateRef` by (namespace, name). `sleap-roots-pipeline.yaml` declares
# `namespace: runai-busch-lab`, but the templates deliberately declare no namespace — they are
# registered with an explicit `-n` at apply time, so that the same files can be applied to
# runai-busch-lab or runai-talmo-lab. The lookup therefore searches namespace "runai-busch-lab"
# while the supplied templates sit in "", and never matches. Nothing is wrong with the manifests.
#
# This script lints a temporary copy with the Workflow's `namespace` stripped, so both sides are ""
# and resolution succeeds. It never modifies the repo. Verified against argo v3.6.5 (CLI) against a
# v3.6.7 cluster, 2026-09-15.
#
# This is the ONLY check that cross-resolves templateRef — i.e. the only one that catches a DAG task
# pointing at a template nobody added. This repo has no CI, so it will not run unless you run it.
#
# Usage:  bash scripts/lint_manifests.sh        # from the repo root (needs `argo` on PATH)

set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v argo >/dev/null 2>&1; then
  echo "argo not found on PATH." >&2
  echo "On this workstation argo lives in WSL at /usr/local/bin/argo — run this from WSL:" >&2
  echo "  wsl -e bash /mnt/c/<path-to-repo>/scripts/lint_manifests.sh" >&2
  exit 127
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cp sleap-roots-pipeline.yaml sleap-roots-*-template.yaml "$tmp"/

# Strip only the Workflow's namespace line, so the offline (namespace, name) lookup matches the
# namespace-less templates. Deliberately not done with sed -i on the repo copy.
python3 - "$tmp/sleap-roots-pipeline.yaml" <<'PY'
import pathlib
import re
import sys

p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
stripped, n = re.subn(r"(?m)^  namespace: .*\n", "", text, count=1)
if n != 1:
    sys.exit("expected exactly one top-level namespace line in sleap-roots-pipeline.yaml")
p.write_text(stripped, encoding="utf-8")
PY

echo "Linting $(ls -1 "$tmp"/*.yaml | wc -l) manifests together (offline, templateRefs resolved)..."
cd "$tmp"
argo lint --offline sleap-roots-pipeline.yaml sleap-roots-*-template.yaml
