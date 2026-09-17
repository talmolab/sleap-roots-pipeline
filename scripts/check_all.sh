#!/usr/bin/env bash
# Run every offline assertion suite in this repo: manifests, then documentation.
#
# Deliberately does NOT invoke scripts/lint_manifests.sh. That wrapper needs `argo` on PATH and
# exits 127 without it; neither suite here needs `argo`, a cluster, a VPN or credentials, and
# gating offline checks behind a binary most machines lack would mean they never run. Run the
# lint wrapper separately when you have `argo` — see its header for why it exists.
#
# Nor does it invoke scripts/check_cluster_drift.sh, which needs live cluster access. Parity
# between this repo and the cluster is not a property this repo can assert; it is a thing you
# go and measure. See docs/cluster-identities.md.
#
# Usage:  bash scripts/check_all.sh      # from anywhere
# Exit:   0 = every assertion in every suite holds; 1 = at least one failed.

set -uo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "No python interpreter found (tried \$PYTHON, python, python3)." >&2
  exit 127
fi

rc=0

# Both suites always run: a documentation regression and a manifest regression are independent,
# and short-circuiting on the first would hide the second behind a fix for the other.
echo "--- manifests ---"
"$PY" scripts/check_manifests.py || rc=1

echo
echo "--- docs ---"
"$PY" scripts/check_docs.py || rc=1

echo
if [ "$rc" -ne 0 ]; then
  echo "=== FAILED: at least one suite reported a failing assertion ==="
else
  echo "=== OK: all suites pass ==="
fi
exit "$rc"
