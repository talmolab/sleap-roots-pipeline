#!/usr/bin/env bash
# Compare the WorkflowTemplates registered in the cluster against this repo's copies.
#
# WHY — issue #58: these templates are applied by hand via `argo template update`, separately from
# merging, and nothing checks that the registered copy still matches the repo. That gap is the
# direct cause of #51, #52, #54 and #55, each of which was a stale pin found only by someone
# noticing. `salk-bloom` has a byte-for-byte drift check for the vendored Workflow; the
# WorkflowTemplates have none. This is the missing check, and it is READ-ONLY.
#
# Run it BEFORE any `argo template update` (it doubles as the rollback pre-image, task 7.1) and
# AFTER, to confirm what you think you applied is what is live.
#
# Usage:  wsl -e bash scripts/check_cluster_drift.sh [namespace]
#         default namespace: runai-busch-lab
# Exit:   0 = in sync, 1 = real drift, 2 = could not reach the cluster.
#
# Requires the busch-lab kubeconfig (WSL): ~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
# See .claude/skills/runai/SKILL.md §1 — argo/kubectl live in WSL, not Windows.

set -uo pipefail

NS="${1:-runai-busch-lab}"
export PATH="$HOME/bin:/usr/local/bin:$PATH"
: "${KUBECONFIG:=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml}"
export KUBECONFIG

cd "$(dirname "$0")/.."
REPO="$(pwd)"

if ! kubectl get workflowtemplates -n "$NS" >/dev/null 2>&1; then
  echo "Cannot list workflowtemplates in $NS (VPN down, or wrong KUBECONFIG: $KUBECONFIG)" >&2
  exit 2
fi

# The API server defaults a number of empty fields on registration and normalises resource
# quantities. Those are not drift. Strip them from BOTH sides so the comparison is semantic.
normalise() {
  python3 - "$1" <<'PY'
import sys, yaml

def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in ("resourceVersion", "uid", "creationTimestamp", "generation",
                     "managedFields", "selfLink", "namespace", "status"):
                continue
            v = clean(v)
            # API-server defaulting: empty containers and empty names are not content.
            if v in ({}, [], "", None) and k in ("arguments", "inputs", "outputs", "metadata",
                                                 "name", "annotations", "labels"):
                continue
            out[k] = v
        return out
    if isinstance(o, list):
        return [clean(i) for i in o]
    if isinstance(o, str):
        # Kubernetes rewrites cpu quantities: '0.5' -> '500m'. Same value.
        try:
            if o.endswith("m") and float(o[:-1]) / 1000 == float(o[:-1]) / 1000:
                return str(float(o[:-1]) / 1000)
        except ValueError:
            pass
    return o

d = clean(yaml.safe_load(open(sys.argv[1], encoding="utf-8")))
print(yaml.safe_dump(d, sort_keys=True, default_flow_style=False))
PY
}

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
drift=0

echo "Comparing registered templates in $NS against $REPO"
echo
for f in sleap-roots-*-template.yaml; do
  name="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['metadata']['name'])" "$f")"
  if ! kubectl get workflowtemplate "$name" -n "$NS" -o yaml > "$tmp/live.yaml" 2>/dev/null; then
    echo "NOT REGISTERED  $name  ($f)"
    drift=1
    continue
  fi
  normalise "$tmp/live.yaml" > "$tmp/live.norm"
  normalise "$f"             > "$tmp/repo.norm"
  if diff -q "$tmp/live.norm" "$tmp/repo.norm" >/dev/null; then
    echo "IN SYNC         $name"
  else
    echo "DRIFT           $name"
    diff "$tmp/repo.norm" "$tmp/live.norm" | sed 's/^/                  /'
    drift=1
  fi
done

echo
echo "Live image pins in $NS:"
for f in sleap-roots-*-template.yaml; do
  name="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['metadata']['name'])" "$f")"
  img="$(kubectl get workflowtemplate "$name" -n "$NS" -o jsonpath='{.spec.templates[0].container.image}' 2>/dev/null)"
  printf '  %-42s %s\n' "$name" "${img:-<not registered>}"
done

echo
if [ "$drift" -eq 0 ]; then echo "=== cluster is IN SYNC with the repo ==="; else echo "=== DRIFT DETECTED (see above) ==="; fi
exit "$drift"
