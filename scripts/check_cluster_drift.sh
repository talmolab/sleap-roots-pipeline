#!/usr/bin/env bash
# Compare the WorkflowTemplates registered in the cluster against this repo's copies.
#
# WHY — issue #58: these templates are applied by hand via `argo template update`, separately from
# merging, and nothing checks that the registered copy still matches the repo. That gap is the
# direct cause of #51, #52, #54 and #55, each of which was a stale pin found only by someone
# noticing. `salk-bloom` has a byte-for-byte drift check for the vendored Workflow; the
# WorkflowTemplates have none. This is the missing check, and it is READ-ONLY.
# Also compares the #98 semaphore ConfigMap's data (the concurrency limits).
#
# Run it BEFORE any `argo template update` (it doubles as the rollback pre-image, task 7.1) and
# AFTER, to confirm what you think you applied is what is live.
#
# Usage:  wsl -e bash scripts/check_cluster_drift.sh [namespace]
#         default namespace: runai-busch-lab
# Exit:   0 = in sync, 1 = real drift, 2 = could not reach the cluster.
#
# Ignored by design: metadata stamped by whatever REGISTERED the object rather than by this
# repo -- `argo template create` writes a `workflows.argoproj.io/creator*` LABEL, `kubectl
# apply` writes `kubectl.kubernetes.io/last-applied-configuration`. Nothing else in those two
# namespaces is ignored; see the INJECTED_* note below for why that line is drawn narrowly.
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

# Keys injected into metadata.labels / metadata.annotations by whatever registered the object,
# not by this repo. `argo template create` stamps `workflows.argoproj.io/creator` (a LABEL, on
# create only -- `update` does not add it), and `kubectl apply` stamps
# `kubectl.kubernetes.io/last-applied-configuration`. Either one makes an otherwise-identical
# template report DRIFT forever, which is the cry-wolf behaviour this script exists to avoid.
# Observed live 2026-09-16: registering the exit-gate template with `create` produced exactly
# this false positive while the four `update`d templates stayed clean.
#
# These are deliberately NARROW, not a `workflows.argoproj.io/` + `kubectl.kubernetes.io/`
# prefix sweep. Both of those namespaces also hold keys a user sets ON PURPOSE, which a broad
# sweep would make undriftable: `workflows.argoproj.io/title` and `/description` are documented
# user-set annotations (argo-workflows v3.6.7 docs/title-and-description.md, since v3.4.4), and
# `kubectl.kubernetes.io/default-container` is user-set too (v3.6.7 workflow/common/common.go).
# The CHECK FAILED guard below refuses to report sync when normalise() fails, on the grounds
# that a check whose failure mode is "everything is fine" is worse than no check; a broad
# prefix would reintroduce exactly that failure mode for those keys. The trade is deliberate: if a future
# Argo injects a key this list misses, the check cries wolf and names the key -- loud, and a
# one-line fix. A broad prefix instead fails silently, reporting IN SYNC on genuine drift.
#
# `creator` stays a prefix so it covers the whole injected family without a blind spot:
# v3.6.7 defines exactly LabelKeyCreator, LabelKeyCreatorEmail and LabelKeyCreatorPreferredUsername
# (workflow/common/common.go) -- only `creator` appears under a ServiceAccount token, the other
# two under SSO -- and nothing user-settable lives under that prefix.
INJECTED_PREFIXES = ("workflows.argoproj.io/creator",)
INJECTED_KEYS = ("kubectl.kubernetes.io/last-applied-configuration",)


def strip_injected(d):
    return {
        k: v
        for k, v in d.items()
        if not k.startswith(INJECTED_PREFIXES) and k not in INJECTED_KEYS
    }


def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in ("resourceVersion", "uid", "creationTimestamp", "generation",
                     "managedFields", "selfLink", "namespace", "status"):
                continue
            if k in ("labels", "annotations") and isinstance(v, dict):
                v = strip_injected(v)
            v = clean(v)
            # API-server defaulting: empty containers and empty names are not content.
            if v in ({}, [], "", None) and k in ("arguments", "inputs", "outputs", "metadata",
                                                 "name", "annotations", "labels"):
                continue
            out[k] = v
        return out
    if isinstance(o, list):
        return [clean(i) for i in o]
    return o


# Kubernetes rewrites cpu quantities: '0.5' -> '500m'. Same value, not drift. This is scoped to
# keys that actually hold a CPU quantity: the previous version tested any string ending in 'm'
# under a guard, `float(o[:-1])/1000 == float(o[:-1])/1000`, which is `X == X` and therefore
# always true -- so it also rewrote `backoff.duration: "2m"` to "0.002", making a duration change
# of that shape compare equal to a CPU value. Numerics are coerced to str on both sides so an
# unquoted `cpu: 0.5` cannot read as drift against the live side's `500m`.
def normalise_cpu(o):
    if isinstance(o, dict):
        return {
            k: (_cpu(v) if k == "cpu" else normalise_cpu(v))
            for k, v in o.items()
        }
    if isinstance(o, list):
        return [normalise_cpu(i) for i in o]
    return o


def _cpu(v):
    s = str(v)
    if s.endswith("m"):
        try:
            return str(float(s[:-1]) / 1000)
        except ValueError:
            return s
    try:
        return str(float(s))
    except ValueError:
        return s


d = normalise_cpu(clean(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))))
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
    [ "$drift" -eq 0 ] && drift=1
    continue
  fi
  # `set -e` is deliberately NOT in effect for this script, so a normalise() failure would
  # otherwise leave BOTH files empty, diff -q would call them identical, and every template would
  # be reported IN SYNC with exit 0 -- a check whose failure mode is "everything is fine". Assert
  # both sides produced real output before believing any comparison.
  if ! normalise "$tmp/live.yaml" > "$tmp/live.norm" || ! [ -s "$tmp/live.norm" ]; then
    echo "CHECK FAILED    $name  (could not normalise the LIVE object; refusing to report sync)" >&2
    drift=2
    continue
  fi
  if ! normalise "$f" > "$tmp/repo.norm" || ! [ -s "$tmp/repo.norm" ]; then
    echo "CHECK FAILED    $name  (could not normalise $f; refusing to report sync)" >&2
    drift=2
    continue
  fi
  if diff -q "$tmp/live.norm" "$tmp/repo.norm" >/dev/null; then
    echo "IN SYNC         $name"
  else
    echo "DRIFT           $name"
    diff "$tmp/repo.norm" "$tmp/live.norm" | sed 's/^/                  /'
    [ "$drift" -eq 0 ] && drift=1
  fi
done

# #98: the semaphore ConfigMap the gated templates acquire from. Only `data` (the limits) is
# compared; metadata carries server-stamped fields. A deliberate live retune still reports DRIFT, so
# nobody forgets to restore it. A missing ConfigMap is drift, and serious: gated nodes Error without
# it. An unreadable one is CHECK FAILED, never "missing" and never "in sync".
SEM_FILE="sleap-roots-pipeline-semaphores.yaml"
sem_name="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['metadata']['name'])" "$SEM_FILE" 2>/dev/null)"
if [ -z "$sem_name" ]; then
  echo "CHECK FAILED    $SEM_FILE  (could not read its name; refusing to report sync)" >&2
  drift=2
elif ! kubectl get configmap "$sem_name" -n "$NS" --ignore-not-found -o yaml > "$tmp/sem-live.yaml" 2>/dev/null; then
  echo "CHECK FAILED    $sem_name  (could not read the live ConfigMap; refusing to report sync)" >&2
  drift=2
elif ! [ -s "$tmp/sem-live.yaml" ]; then
  echo "NOT CREATED     $sem_name  ($SEM_FILE) -- gated nodes Error without it"
  [ "$drift" -eq 0 ] && drift=1
else
  python3 - "$tmp/sem-live.yaml" "$SEM_FILE" > "$tmp/sem.out" 2>&1 <<'PY'
import sys, yaml
live, repo = ((yaml.safe_load(open(p, encoding="utf-8")) or {}).get("data") or {} for p in sys.argv[1:3])
for k in sorted(set(live) | set(repo)):
    if live.get(k) != repo.get(k):
        print(f"{k}: repo={repo.get(k)!r} live={live.get(k)!r}")
sys.exit(0 if live == repo else 3)
PY
  case $? in
    0) echo "IN SYNC         $sem_name" ;;
    3) echo "DRIFT           $sem_name"
       sed 's/^/                  /' "$tmp/sem.out"
       [ "$drift" -eq 0 ] && drift=1 ;;
    *) echo "CHECK FAILED    $sem_name  (could not compare data; refusing to report sync)" >&2
       sed 's/^/                  /' "$tmp/sem.out" >&2
       drift=2 ;;
  esac
fi

echo
echo "Live image pins in $NS:"
for f in sleap-roots-*-template.yaml; do
  name="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['metadata']['name'])" "$f")"
  img="$(kubectl get workflowtemplate "$name" -n "$NS" -o jsonpath='{.spec.templates[0].container.image}' 2>/dev/null)"
  printf '  %-42s %s\n' "$name" "${img:-<not registered>}"
done

echo
if [ "$drift" -eq 0 ]; then
  echo "=== cluster is IN SYNC with the repo ==="
elif [ "$drift" -eq 2 ]; then
  echo "=== CHECK FAILED — this is NOT a clean result, do not treat it as one ==="
else
  echo "=== DRIFT DETECTED (see above) ==="
fi
exit "$drift"
