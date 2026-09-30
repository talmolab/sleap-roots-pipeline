# Pipeline Concurrency Semaphores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At most 8 concurrent predictor tasks and 5 concurrent images-downloader tasks namespace-wide, via Argo ConfigMap-backed semaphores (#98).

**Architecture:** A new ConfigMap `sleap-roots-pipeline-semaphores` holds two limits. The `predictor` and `images-downloader` WorkflowTemplates acquire one key each through `synchronization.semaphores[].configMapKeyRef`. The launcher ensures the ConfigMap exists and is valid before registering templates. `check_manifests.py` asserts the wiring offline, and `check_cluster_drift.sh` compares the live ConfigMap.

**Tech Stack:** Argo Workflows v3.6.7 controller (CLI v3.6.5, WSL), a Kubernetes ConfigMap, bash, Python 3 + PyYAML.

**Spec:** `openspec/changes/add-pipeline-concurrency-semaphores/` (proposal.md, design.md, tasks.md, specs/per-batch-pipeline/spec.md). design.md's "Verified facts" and "Risks" are required reading.

## Global Constraints

- ConfigMap `sleap-roots-pipeline-semaphores`, file `sleap-roots-pipeline-semaphores.yaml`, namespace `runai-busch-lab`, label `project: busch-lab`, data exactly `pipeline-gpu: "8"` and `pipeline-stage-in: "5"` (quoted).
- Plural `synchronization.semaphores:` only; no singular `semaphore:`, no mutex.
- `pipeline-gpu` ≤ 10, valid only at predictor `gpu-memory: "8192"`.
- Commit order: ConfigMap → launcher → templates → drift → docs. No commit gates a template before something creates the ConfigMap. Every commit leaves `check_all.sh` and `lint_manifests.sh` green; never commit a red TDD step.
- The canonical statement of the gate's semantics, deploy order and safe retune is the ConfigMap file's header. Template, launcher, doc and ci-debug text points there rather than restating it.
- Don't touch or assert anything about the `local-WSL2-*` manifests (unmaintained, to be removed).
- Tooling: `argo` and the busch-lab kubeconfig live in WSL. From PowerShell: `wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; cd /mnt/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98 && <cmd>'`. Offline Python checks and the stub harnesses run in Git Bash, where the interpreter is `python`; `python3` is the Microsoft Store stub.
- Cluster-changing commands (`kubectl create/patch/delete`, `argo template create/update`, `argo submit/delete`) run only with the owner's explicit go-ahead for that step. Read-only `kubectl get` and `argo list/get` are fine.
- Stub harnesses put stubs on a `/c/...` PATH and assert `command -v kubectl` resolves to the stub. Docker Desktop's real `kubectl` is on the Git Bash PATH, so a stub that isn't found would reach a real cluster.
- Scratch dir (Git Bash): `SCR=/c/Users/ELIZAB~1/AppData/Local/Temp/claude/c--repos-sleap-roots-pipeline/fa1446be-9668-406d-90dc-315af2a03fd8/scratchpad`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Unquoted or non-integer values** in the ConfigMap. kubectl rejects non-string `data`, and the controller Errors on non-integers, including for running tasks. Covered by Task 1 mutations M2 and M3.
2. **The launcher with no working kubeconfig, or an incomplete ConfigMap.** It must exit before any `argo` call. Covered by the Task 2 stub harness in modes `fail` and `missingkey`.
3. **A `gpu-memory` bump without re-deriving the ≤ 10 bound.** Covered by Task 3 mutation M6.
4. **Drift check: an unreadable ConfigMap, or a CHECK FAILED followed by drift.** It must exit 2, not 1 or 0. Covered by the Task 4 stub harness in cases `fail` and `garbage+retuned`.
5. **A task that waited, then acquired, must still retry and still pass its exit code to the gate.** The node is created as a Pod type while waiting. Covered only live, by tasks.md 7.5.

---

### Task 1: ConfigMap and its checks

**Files:** Create `sleap-roots-pipeline-semaphores.yaml`. Modify `scripts/check_manifests.py`: constants after `BATCH_STAGES`, and a block at the end of `main()` just before the final `print()`. Create `$SCR/mutate.py` (throwaway).

**Interfaces — produces:** `SEMAPHORES`, `SEMAPHORE_CM`, `SEMAPHORE_KEY_BY_STAGE`, `GPU_SLICE_CAPACITY`, `GPU_SLICE_MEMORY`, `SEMAPHORE_VALUE_RE`, and local `sem_data` inside `main()`. Tasks 2 and 3 use them.

- [ ] **Step 1: Constants** (after `BATCH_STAGES`):

```python
# #98: namespace-wide concurrency limits. Each gated stage acquires ONE key of one ConfigMap.
SEMAPHORES = "sleap-roots-pipeline-semaphores.yaml"
SEMAPHORE_CM = "sleap-roots-pipeline-semaphores"
SEMAPHORE_KEY_BY_STAGE = {
    "predictor": "pipeline-gpu",
    "images-downloader": "pipeline-stage-in",
}
# Upper bound on pipeline-gpu: predictor slices busch-lab's 2-GPU deserved quota can hold. A live
# predictor pod's RunAI GPU ConfigMap recorded gpu-memory 8192 MB as RUNAI_NUM_OF_GPUS 0.18
# (2026-09-30): floor(1/0.18) = 5 per GPU, 10 across 2. Valid ONLY at that gpu-memory, which is why
# the predictor's annotation is pinned below.
GPU_SLICE_CAPACITY = 10
GPU_SLICE_MEMORY = "8192"
# Quoted decimal >= 1. The controller parses it with strconv.Atoi; anything else Errors every gated
# node, running ones included.
SEMAPHORE_VALUE_RE = re.compile(r"^[1-9][0-9]*$")
```

- [ ] **Step 2: Assertions** (end of `main()`, before the final `print()`):

```python
    # --- Requirement: GPU and stage-in concurrency are bounded by namespace semaphores ---
    sem = load(SEMAPHORES)
    sem_meta = sem.get("metadata") or {}
    sem_data = sem.get("data") or {}
    check("semaphore manifest is a ConfigMap", sem.get("kind"), "ConfigMap")
    check("semaphore ConfigMap name", sem_meta.get("name"), SEMAPHORE_CM)
    check(
        "semaphore ConfigMap namespace equals the Workflow's",
        sem_meta.get("namespace"),
        wf["metadata"]["namespace"],
    )
    check("semaphore ConfigMap carries the quota label", (sem_meta.get("labels") or {}).get("project"), "busch-lab")
    check(
        "semaphore ConfigMap defines exactly the keys the templates acquire",
        sorted(sem_data),
        sorted(SEMAPHORE_KEY_BY_STAGE.values()),
    )
    for key in sorted(SEMAPHORE_KEY_BY_STAGE.values()):
        value = sem_data.get(key)
        check(
            f"ConfigMap {key} is a quoted decimal integer >= 1",
            isinstance(value, str) and bool(SEMAPHORE_VALUE_RE.match(value)),
            True,
        )
    gpu = sem_data.get("pipeline-gpu")
    check(
        f"pipeline-gpu fits the quota's slice capacity (<= {GPU_SLICE_CAPACITY})",
        isinstance(gpu, str) and bool(SEMAPHORE_VALUE_RE.match(gpu)) and int(gpu) <= GPU_SLICE_CAPACITY,
        True,
    )
```

- [ ] **Step 3: Run and verify it fails.** `python scripts/check_manifests.py`. Expect a `FileNotFoundError` for the ConfigMap file.

- [ ] **Step 4: Create `sleap-roots-pipeline-semaphores.yaml`.** This header is the canonical text:

```yaml
# Namespace-wide concurrency limits for the per-batch pipeline (#98; A4 design §9).
# THIS HEADER IS THE CANONICAL STATEMENT of the gate's semantics, deploy order and safe retune;
# templates, the launcher and the docs point here. Rationale and source citations:
# openspec/changes/add-pipeline-concurrency-semaphores/design.md.
#
# The `predictor` template acquires `pipeline-gpu`, and the `images-downloader` template acquires
# `pipeline-stage-in`. The pool is shared by EVERY Workflow in runai-busch-lab that uses those
# templates -- Bloom prod, Bloom staging and manual runs -- as they share the 2-GPU deserved quota.
# pipeline-gpu 8 = 1.44 GPU of non-preemptible work (8192 MB = 0.18 GPU per predictor), inside the
# quota RunAI enforces on NON-preemptible allocations; ceiling 10, enforced by
# scripts/check_manifests.py. Preemptible sessions don't count toward that quota, and the predictor
# (priorityClassName high) outranks them.
#
# Argo v3.6.7 behaviour (read from source 2026-09-30):
#   - One slot = one TASK, held across all its retries AND the backoff between them.
#   - A task waiting for a slot is a Pending node with NO pod ("Waiting for
#     runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/<key> lock"), FIFO.
#   - A missing ConfigMap or key, a non-integer value, or a failed API read makes gated nodes ERROR
#     -- including RUNNING ones. So: create this BEFORE `argo template update`-ing either gated
#     template, and never delete it while any gated Workflow exists (running Workflows keep their
#     stored gated template).
#   - After a workflow-controller restart the pool forgets its holders and can over-admit, up to
#     2x the limit, until the old holders finish.
#
# RETUNE LIVE with a validated patch, never `kubectl edit` (a typo Errors running tasks):
#   n=2; [[ $n =~ ^[1-9][0-9]*$ ]] && kubectl patch configmap sleap-roots-pipeline-semaphores \
#     -n runai-busch-lab --type merge -p "{\"data\":{\"pipeline-gpu\":\"$n\"}}"
# A lower limit applies at the next acquire. A raise reaches tasks already waiting only at the next
# slot release or the 20-minute resync. scripts/check_cluster_drift.sh reports the live value until
# it matches this file again. runai_run_pipeline.sh creates this ConfigMap if absent and never
# overwrites it.
#
# Values MUST be quoted: ConfigMap data is string-only.
apiVersion: v1
kind: ConfigMap
metadata:
  name: sleap-roots-pipeline-semaphores
  namespace: runai-busch-lab
  labels:
    project: busch-lab
data:
  pipeline-gpu: "8"
  pipeline-stage-in: "5"
```

- [ ] **Step 5: Run and verify it passes.** `python scripts/check_manifests.py` → `=== ALL N ASSERTIONS PASS ===`.

- [ ] **Step 6: Write the mutation harness `$SCR/mutate.py`.** Tasks 2 and 3 append to it:

```python
import pathlib, shutil, subprocess, sys, tempfile
SRC = pathlib.Path(r"C:\repos\sleap-roots-pipeline\.worktrees\argo-semaphore-98")
CM, PRED, DL, L = ("sleap-roots-pipeline-semaphores.yaml", "sleap-roots-predictor-template.yaml",
                   "sleap-roots-images-downloader-template.yaml", "runai_run_pipeline.sh")
# (label, [(file, old, new), ...], substring of the FAIL line that must appear)
M = [
    ("M1 gpu over capacity", [(CM, 'pipeline-gpu: "8"', 'pipeline-gpu: "11"')], "fits the quota's slice capacity"),
    ("M2 zero", [(CM, 'pipeline-stage-in: "5"', 'pipeline-stage-in: "0"')], "pipeline-stage-in is a quoted decimal"),
    ("M3 unquoted", [(CM, 'pipeline-gpu: "8"', "pipeline-gpu: 8")], "pipeline-gpu is a quoted decimal"),
    ("M7 extra key", [(CM, 'pipeline-stage-in: "5"', 'pipeline-stage-in: "5"\n  unused: "1"')], "defines exactly the keys"),
    ("M9 key deleted", [(CM, '\n  pipeline-stage-in: "5"', "")], "defines exactly the keys"),
    ("M10 wrong namespace", [(CM, "  namespace: runai-busch-lab", "  namespace: runai-talmo-lab")], "namespace equals the Workflow's"),
]
only = set(sys.argv[1:])
bad = 0
for label, edits, expect in M:
    if only and label.split()[0] not in only:
        continue
    with tempfile.TemporaryDirectory() as d:
        dst = pathlib.Path(d) / "r"
        shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns(".git"))
        for f, old, new in edits:
            p = dst / f
            s = p.read_text(encoding="utf-8")
            assert s.count(old) == 1, (label, f, "anchor not unique/found")
            p.write_text(s.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, str(dst / "scripts/check_manifests.py")], capture_output=True, text=True)
        ok = r.returncode == 1 and any(l.startswith("FAIL") and expect in l for l in r.stdout.splitlines())
        print(("OK   " if ok else "MISS ") + label)
        bad += not ok
sys.exit(bad)
```

Run `python "$SCR/mutate.py"` → six `OK` lines, exit 0.

- [ ] **Step 7: Full suite and lint.** Run `bash scripts/check_all.sh` → OK. Run `lint_manifests.sh` via WSL (see Global Constraints) → "Linting 6 manifests", no errors.

- [ ] **Step 8: Commit.** `git add sleap-roots-pipeline-semaphores.yaml scripts/check_manifests.py`, then `git commit -m "feat(semaphores): add the sleap-roots-pipeline-semaphores ConfigMap and its checks (#98)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 2: Launcher ensures the ConfigMap

**Files:**
- Modify `runai_run_pipeline.sh`:
  - the header manual steps (lines 4–14);
  - the NOTE echoes (lines 50–51);
  - a new block immediately before `echo -e "${YELLOW}Registering WorkflowTemplates...`.
- Modify `scripts/check_manifests.py` (append to the Task 1 block).
- Create `$SCR/stub/` and `$SCR/launcher_stub.sh` (throwaway).

**Interfaces — consumes:** `SEMAPHORES`, `SEMAPHORE_CM`, `sem_data`.

- [ ] **Step 1: Failing assertions** (append to the Task 1 block):

```python
    # --- Scenario: Launcher creates the semaphore ConfigMap only when absent, before templates ---
    launcher = (ROOT / "runai_run_pipeline.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in launcher.splitlines() if not l.lstrip().startswith("#"))
    check("launcher names the semaphore ConfigMap file", f'SEMAPHORES_FILE="{SEMAPHORES}"' in code, True)
    check("launcher names the semaphore ConfigMap", f'SEMAPHORES_CM="{SEMAPHORE_CM}"' in code, True)
    keys_m = re.search(r"^SEMAPHORE_KEYS=\(([^)]*)\)", code, re.M)
    check(
        "launcher validates exactly the ConfigMap's keys",
        sorted(re.findall(r'"([^"]+)"', keys_m.group(1))) if keys_m else None,
        sorted(sem_data),
    )
    create_line = 'kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"'
    check(
        "launcher's only kubectl create is the ConfigMap file",
        re.findall(r"kubectl\s+create\b[^\n]*", code),
        [create_line],
    )
    get_i = code.find('kubectl get configmap "$SEMAPHORES_CM" -n "$NAMESPACE" --ignore-not-found -o name')
    loop_i = code.find('for tmpl_file in "${TEMPLATES[@]}"')
    check(
        "launcher's ConfigMap get, then create, both precede the template loop",
        0 <= get_i < code.find(create_line) < loop_i,
        True,
    )
    check(
        "launcher creates only on the empty-result branch",
        bool(re.search(r'if \[ -z "\$existing" \]; then\n(?:(?!\n\s*(?:else|fi)\b).)*?' + re.escape(create_line), code, re.S)),
        True,
    )

    def aborts(head: str) -> bool:
        # the `if <head>; then` block reaches `exit 1` before its own `else`/`fi`
        return bool(re.search(re.escape(head) + r"[^\n]*; then\n(?:(?!\n\s*(?:else|fi)\b).)*?\bexit 1", code, re.S))

    check("launcher aborts when kubectl is absent", aborts("if ! command -v kubectl"), True)
    check("launcher aborts when the ConfigMap get fails", aborts("if ! existing=$(kubectl get configmap"), True)
    check("launcher aborts when reading a key fails", aborts("if ! value=$(kubectl get configmap"), True)
    check("launcher aborts on an invalid existing key", aborts('if ! [[ "$value" =~'), True)
    check(
        "launcher never applies, replaces, edits or patches",
        re.findall(r"kubectl\s+(?:apply|replace|edit|patch)\b", code),
        [],
    )
```

Run `python scripts/check_manifests.py` → exit 1, with the launcher checks FAILing. Do not commit.

- [ ] **Step 2: The launcher block** (immediately before `echo -e "${YELLOW}Registering WorkflowTemplates in namespace '$NAMESPACE'...${NC}"`):

```bash
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
```

Also make two small edits:
- In the header manual steps, insert `#   kubectl create -f sleap-roots-pipeline-semaphores.yaml             # first, once (#98)` after the `export KUBECONFIG=...` line.
- After `echo "NOTE: Ensure ARGO_TOKEN is exported in your environment."`, add `echo "NOTE: kubectl + a working KUBECONFIG are also needed (semaphore ConfigMap, #98)."`

- [ ] **Step 3: Verify.** Run `bash -n runai_run_pipeline.sh && python scripts/check_manifests.py` → all pass.

- [ ] **Step 4: Add the launcher mutations to `$SCR/mutate.py`'s `M`, then run it.**

```python
    ("L1 create after loop", [(L, '  kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"\n', "  :\n"),
                               (L, 'echo -e "${YELLOW}Submitting Workflow', 'kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"\necho -e "${YELLOW}Submitting Workflow')],
     "precede the template loop"),
    ("L2 apply", [(L, 'kubectl create -f "$SEMAPHORES_FILE"', 'kubectl apply -f "$SEMAPHORES_FILE"')], "never applies"),
    ("L3 no abort", [(L, "(check KUBECONFIG/VPN). No template registered.${NC}\" >&2\n  exit 1\n", "(check KUBECONFIG/VPN). No template registered.${NC}\" >&2\n  true\n")],
     "aborts when the ConfigMap get fails"),
    ("L4 key list", [(L, 'SEMAPHORE_KEYS=("pipeline-gpu" "pipeline-stage-in")', 'SEMAPHORE_KEYS=("pipeline-gpu")')], "validates exactly"),
```

Run `python "$SCR/mutate.py"` → ten `OK` lines.

- [ ] **Step 5: Behaviour harness.** Create `$SCR/launcher_stub.sh`, then run `bash "$SCR/launcher_stub.sh"`:

```bash
#!/usr/bin/env bash
# Throwaway: exercise runai_run_pipeline.sh's ConfigMap branches with stubbed kubectl/argo.
set -u
SCR=/c/Users/ELIZAB~1/AppData/Local/Temp/claude/c--repos-sleap-roots-pipeline/fa1446be-9668-406d-90dc-315af2a03fd8/scratchpad
SRC=/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98
STUB="$SCR/stub"; rm -rf "$STUB"; mkdir -p "$STUB"
cat > "$STUB/kubectl" <<'EOF'
#!/bin/sh
echo "kubectl $*" >> "$CALLS"
case "$*" in "config current-context") echo stub-ctx; exit 0;; esac
case "$KSTUB_MODE:$*" in
  "fail:get configmap"*) echo "stub: unreachable" >&2; exit 1;;
  "empty:get configmap"*) exit 0;;
  *"--ignore-not-found"*) echo configmap/sleap-roots-pipeline-semaphores; exit 0;;
  "valid:get configmap"*jsonpath*) printf 5; exit 0;;
  "missingkey:get configmap"*pipeline-gpu*) printf 5; exit 0;;
  "missingkey:get configmap"*jsonpath*) exit 0;;
  *":create "*) exit 0;;
esac
echo "stub: unexpected kubectl $*" >&2; exit 99
EOF
cat > "$STUB/argo" <<'EOF'
#!/bin/sh
echo "argo $*" >> "$CALLS"
case "$1" in submit) echo stub-wf;; esac
exit 0
EOF
printf '#!/bin/sh\nexit 0\n' > "$STUB/sleep"
chmod +x "$STUB"/*
export PATH="$STUB:$PATH"
[ "$(command -v kubectl)" = "$STUB/kubectl" ] || { echo "ABORT: kubectl stub not first on PATH"; exit 2; }
fails=0
run() {  # mode expected_rc expect_create expect_argo
  local mode=$1 want_rc=$2 want_create=$3 want_argo=$4 work
  work=$(mktemp -d); cp -r "$SRC"/. "$work"/ 2>/dev/null; rm -rf "$work/.git"
  export CALLS="$work/calls.log" KSTUB_MODE=$mode; : > "$CALLS"
  (cd "$work" && bash runai_run_pipeline.sh >/dev/null 2>&1); local rc=$?
  local created=no argo=no first_argo create_ln
  grep -q '^kubectl create ' "$CALLS" && created=yes
  grep -q '^argo ' "$CALLS" && argo=yes
  if [ "$created" = yes ] && [ "$argo" = yes ]; then
    create_ln=$(grep -n '^kubectl create ' "$CALLS" | head -1 | cut -d: -f1)
    first_argo=$(grep -n '^argo ' "$CALLS" | head -1 | cut -d: -f1)
    [ "$create_ln" -lt "$first_argo" ] || created=after-argo
  fi
  if [ "$rc" = "$want_rc" ] && [ "$created" = "$want_create" ] && [ "$argo" = "$want_argo" ]; then
    echo "OK   $mode (rc=$rc create=$created argo=$argo)"
  else
    echo "MISS $mode (rc=$rc create=$created argo=$argo; want $want_rc/$want_create/$want_argo)"; sed 's/^/     /' "$CALLS"; fails=$((fails+1))
  fi
  rm -rf "$work"
}
run fail 1 no no
run empty 0 yes yes
run valid 0 no yes
run missingkey 1 no no
exit $fails
```

Expect four `OK` lines, exit 0.

- [ ] **Step 6: Full suite, then commit.** Run `bash scripts/check_all.sh` → OK. Then `git add runai_run_pipeline.sh scripts/check_manifests.py` and `git commit -m "feat(launcher): ensure the semaphore ConfigMap before registering templates (#98)" -m "BREAKING (operators): the launcher now also needs kubectl and a KUBECONFIG that can read and create ConfigMaps in runai-busch-lab." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 3: Gate the two templates

**Files:** Modify `sleap-roots-predictor-template.yaml` (between `priorityClassName: high` and `retryStrategy:`), `sleap-roots-images-downloader-template.yaml` (between `priorityClassName: interactive-preemptible` and `retryStrategy:`), and `scripts/check_manifests.py`.

- [ ] **Step 1: Failing assertions** (append):

```python
    for stage, key in SEMAPHORE_KEY_BY_STAGE.items():
        sync = load(BATCH_STAGES[stage])["spec"]["templates"][0].get("synchronization") or {}
        check(
            f"{stage} acquires exactly its own semaphore key",
            [r.get("configMapKeyRef") for r in (sync.get("semaphores") or [])],
            [{"name": SEMAPHORE_CM, "key": key}],
        )
        check(
            f"{stage} uses only the plural semaphores list (no singular semaphore, no mutex)",
            sorted(k for k in sync if k != "semaphores"),
            [],
        )
    pred_tmpl = load(BATCH_STAGES["predictor"])["spec"]["templates"][0]
    check(
        "predictor gpu-memory is the value GPU_SLICE_CAPACITY was derived at",
        ((pred_tmpl.get("metadata") or {}).get("annotations") or {}).get("gpu-memory"),
        GPU_SLICE_MEMORY,
    )
```

Run it → the two "acquires exactly" checks FAIL. Do not commit.

- [ ] **Step 2: Predictor** (6-space indent, like `priorityClassName`):

```yaml
      # #98: at most `pipeline-gpu` predictor tasks run at once across runai-busch-lab. The slot is
      # held across every retry below AND the backoff between them (>= ~14m for a failing batch).
      # The ConfigMap must exist before this template is updated. Semantics, limit, deploy order
      # and safe retune: the header of sleap-roots-pipeline-semaphores.yaml.
      synchronization:
        semaphores:
          - configMapKeyRef:
              name: sleap-roots-pipeline-semaphores
              key: pipeline-gpu
```

- [ ] **Step 3: Downloader:**

```yaml
      # #98: at most `pipeline-stage-in` downloader tasks run at once across runai-busch-lab -- the
      # stage where a large trigger's pod flood lands first. Same gate as the predictor's; see the
      # header of sleap-roots-pipeline-semaphores.yaml.
      synchronization:
        semaphores:
          - configMapKeyRef:
              name: sleap-roots-pipeline-semaphores
              key: pipeline-stage-in
```

- [ ] **Step 4: Verify.** `python scripts/check_manifests.py` → all pass. Lint via WSL → "Linting 6 manifests", clean.

- [ ] **Step 5: Add the template mutations to `M` and run.**

```python
    ("M4 wrong key", [(DL, "key: pipeline-stage-in", "key: pipeline-gpu")], "images-downloader acquires exactly"),
    ("M5 singular", [(PRED, "        semaphores:\n          - configMapKeyRef:", "        semaphore:\n            configMapKeyRef:")], "predictor uses only the plural"),
    ("M6 gpu-memory bump", [(PRED, 'gpu-memory: "8192"', 'gpu-memory: "12288"')], "predictor gpu-memory is the value"),
```

Run `python "$SCR/mutate.py"` → thirteen `OK` lines.

- [ ] **Step 6: Commit.** Run `check_all.sh` → OK. Then `git add sleap-roots-predictor-template.yaml sleap-roots-images-downloader-template.yaml scripts/check_manifests.py` and `git commit -m "feat(templates): gate predictor and images-downloader on the namespace semaphores (#98)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 4: Drift check covers the ConfigMap

**Files:** Modify `scripts/check_cluster_drift.sh`:
- the header's WHY block;
- lines ~146 and ~168 (`drift=1` → `[ "$drift" -eq 0 ] && drift=1`);
- a new block after the template loop's `done`, before the blank `echo` preceding `Live image pins`.

Create `$SCR/drift_stub.sh` (throwaway).

- [ ] **Step 1: The block:**

```bash

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
```

Also:
- Replace both `drift=1` lines in the template loop with `[ "$drift" -eq 0 ] && drift=1`.
- Add this header line: `# Also compares the #98 semaphore ConfigMap's data (the concurrency limits).`

- [ ] **Step 2: Stub harness `$SCR/drift_stub.sh`.** It stubs `python3` as `python`, and sets `HOME` so the script's `$HOME/bin` PATH prefix can't shadow the stub:

```bash
#!/usr/bin/env bash
set -u
SCR=/c/Users/ELIZAB~1/AppData/Local/Temp/claude/c--repos-sleap-roots-pipeline/fa1446be-9668-406d-90dc-315af2a03fd8/scratchpad
SRC=/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98
STUB="$SCR/dstub"; rm -rf "$STUB"; mkdir -p "$STUB"
cat > "$STUB/kubectl" <<'EOF'
#!/bin/sh
case "$*" in
  "get workflowtemplates"*) exit 0;;
  "get workflowtemplate "*"-o yaml"*)
    name=$3
    if [ "$DMODE" = garbage+retuned ] && [ "$name" = sleap-roots-write-back-template ]; then echo "[unterminated"; exit 0; fi
    cat "$SRC/$name.yaml"; exit 0;;
  "get workflowtemplate "*jsonpath*) echo stub-image; exit 0;;
  "get configmap"*)
    case "$DMODE" in
      sync) cat "$SRC/sleap-roots-pipeline-semaphores.yaml";;
      retuned|garbage+retuned) sed 's/pipeline-gpu: "8"/pipeline-gpu: "2"/' "$SRC/sleap-roots-pipeline-semaphores.yaml";;
      missing) :;;
      fail) echo "stub: unreachable" >&2; exit 1;;
    esac; exit 0;;
esac
echo "stub: unexpected kubectl $*" >&2; exit 99
EOF
printf '#!/bin/sh\nexec python "$@"\n' > "$STUB/python3"
chmod +x "$STUB"/*
export PATH="$STUB:$PATH" HOME="$SCR/dhome" SRC; mkdir -p "$HOME"
[ "$(command -v kubectl)" = "$STUB/kubectl" ] || { echo "ABORT: stub not first"; exit 2; }
fails=0
for case_ in "sync 0 IN.SYNC" "retuned 1 DRIFT" "missing 1 NOT.CREATED" "fail 2 CHECK.FAILED" "garbage+retuned 2 DRIFT"; do
  set -- $case_
  out=$(DMODE=$1 bash "$SRC/scripts/check_cluster_drift.sh" 2>&1); rc=$?
  if [ "$rc" = "$2" ] && echo "$out" | grep -q "$3 *sleap-roots-pipeline-semaphores"; then echo "OK   $1 (rc=$rc)"
  else echo "MISS $1 (rc=$rc, want $2 + '$3')"; echo "$out" | sed 's/^/     /'; fails=$((fails+1)); fi
done
exit $fails
```

In the `garbage+retuned` case the live write-back template is unparseable YAML, so `normalise()` fails (CHECK FAILED, 2) and the later ConfigMap DRIFT must not lower it to 1. Expect five `OK` lines.

The stub path matters. The script prepends `$HOME/bin:/usr/local/bin` to PATH, and in Git Bash `/usr/local/bin` has no kubectl. Confirm that with `ls /usr/local/bin/kubectl`, which should say no such file.

- [ ] **Step 3: Read-only live baseline (WSL).** Run `bash scripts/check_cluster_drift.sh`. Expect DRIFT for the predictor and images-downloader templates, NOT CREATED for the ConfigMap, and exit 1. Save the output for the PR as the pre-deploy baseline.

- [ ] **Step 4: Commit.** `bash -n scripts/check_cluster_drift.sh` then `check_all.sh` → OK. Then `git add scripts/check_cluster_drift.sh` and `git commit -m "feat(drift): compare the semaphore ConfigMap; never downgrade CHECK FAILED (#98)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 5: Docs

**Files:** `README.md`, `docs/cluster-identities.md`, `.claude/commands/ci-debug.md`, `.claude/skills/runai/SKILL.md`, `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`, `openspec/project.md`, and ticks in `openspec/changes/add-pipeline-concurrency-semaphores/tasks.md`.

- [ ] **Step 1: README.md.**
  - One-Time Setup (~l.185): after "Ensure that `ARGO_TOKEN` is exported…", add: "The launcher also needs `kubectl` and a `KUBECONFIG` that can read and create ConfigMaps in `runai-busch-lab` (the #98 semaphore ConfigMap; in WSL, `export PATH=$HOME/bin:$PATH`)."
  - "This script will:" (~l.193): prepend the bullet "Create the `sleap-roots-pipeline-semaphores` ConfigMap if absent (never updates it; aborts if it can't read it or it is incomplete)".
  - Folder tree (~l.149): add `├── sleap-roots-pipeline-semaphores.yaml         # ConfigMap: namespace-wide GPU / stage-in concurrency limits (#98)` after the pipeline line.
  - "Creating WorkflowTemplates" (~l.257): before the first `argo template create`, add `kubectl create -f sleap-roots-pipeline-semaphores.yaml -n runai-busch-lab   # first: the predictor and downloader templates Error without it`.

- [ ] **Step 2: `docs/cluster-identities.md`.** Insert after the "So non-preemptible work in this namespace is normal…" paragraph, before the `argo submit -n` paragraph:

```markdown
**The pipeline caps its own share of the quota (#98).** The `predictor` and `images-downloader`
templates acquire slots from the ConfigMap `sleap-roots-pipeline-semaphores`. The pool is
namespace-wide, shared by Bloom prod, Bloom staging and manual runs, and a task waiting for a slot
is a Pending Argo node with no pod. `pipeline-gpu` keeps the pipeline's non-preemptible GPU use
inside the quota RunAI enforces on non-preemptible allocations, so a large trigger no longer puts a
predictor pod per batch into `NonPreemptibleOverQuota`. Preemptible sessions don't count toward
that quota and the predictor outranks them, so it can preempt them when GPUs are physically short;
coordinating before a large run still applies. To change the limit, use the validated patch in the
header of `sleap-roots-pipeline-semaphores.yaml` — never `kubectl edit`, since a non-integer value
makes every running gated task Error — and `scripts/check_cluster_drift.sh` reports the difference
until the repo matches. Never delete that ConfigMap while any gated Workflow exists.
```

- [ ] **Step 3: ci-debug.md table.** Add two rows after the `NonPreemptibleOverQuota` row:

```markdown
| Predictor or downloader node `Pending`, **no pod**, message `Waiting for runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/<key> lock` | expected (#98): the namespace-wide concurrency limit is full | nothing, or retune live — see the header of `sleap-roots-pipeline-semaphores.yaml`. A raise reaches waiting tasks only at the next release or within 20 minutes |
| Predictor or downloader node `Error`: `configmaps "sleap-roots-pipeline-semaphores" not found`, or `Sync configuration key ... not found in ConfigMap` | the semaphore ConfigMap is missing, lacks a key, or holds a non-integer — this Errors running tasks too | `kubectl create -f sleap-roots-pipeline-semaphores.yaml` (or fix the value with the header's patch), then resubmit the batch |
```

- [ ] **Step 4: runai SKILL.md §8.** Change the "Job stuck `Pending`" fix cell to append: "; an Argo node `Pending` with **no pod** and a `Waiting for … sleap-roots-pipeline-semaphores/<key> lock` message is the #98 concurrency limit, not RunAI (see `.claude/commands/ci-debug.md`)".

- [ ] **Step 5: A4 §9 annotation.** After the "Argo semaphore (ConfigMap-backed)" bullet:

```markdown
  **Built 2026-09-30 ([#98](https://github.com/talmolab/sleap-roots-pipeline/issues/98)), differently
  from the above:** template-level, bounding **tasks**, not batches — `predictor` acquires
  `pipeline-gpu` and `images-downloader` acquires `pipeline-stage-in` from ConfigMap
  `sleap-roots-pipeline-semaphores`; trait-extractor and write-back are not gated, so it does not
  bound the write-back rate. The quota is **busch-lab's** (2 GPUs), not talmo-lab's. See
  `openspec/changes/add-pipeline-concurrency-semaphores/design.md`.
```

- [ ] **Step 6: `openspec/project.md`.**
  - Purpose (l.~22–27): rewrite the "Still open:" sentence to match the roadmap. The Bloom trigger route and dispatch worker have shipped (roadmap A4 row, 2026-09-16 note), and the semaphore is built (#98). Keep "per-run path isolation" only if the roadmap still lists it as open; check #71's row first. End with "— see the roadmap's A4 change-breakdown table".
  - Domain Context: fix "the Bloom-side trigger route … is not yet built" to match.
  - Architecture Patterns (l.97–101): replace "set `priorityClassName: interactive-preemptible` to go over quota" with "do **not** move the predictor to `interactive-preemptible` (it is deliberately `high`, #37); check who holds the quota — see `docs/cluster-identities.md`".
  - External Dependencies (l.~177): add "`runai_run_pipeline.sh` also needs `kubectl` + a working `KUBECONFIG` (the #98 semaphore ConfigMap)."

- [ ] **Step 7: Verify.** `python scripts/check_docs.py` → all pass. `grep -n "semaphore" openspec/project.md` shows no open-work claim.

- [ ] **Step 8: Tick tasks.md 1.x–5.x and commit.** `git add README.md docs/cluster-identities.md .claude/commands/ci-debug.md .claude/skills/runai/SKILL.md docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md openspec/project.md openspec/changes/add-pipeline-concurrency-semaphores/tasks.md`, then `git commit -m "docs: document the #98 concurrency semaphores and correct stale project.md claims" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

---

### Task 6: Pre-PR sweep and PR

- [ ] **Step 1:** Run `bash scripts/check_all.sh`, lint via WSL, `openspec validate add-pipeline-concurrency-semaphores --strict`, and `python "$SCR/mutate.py"`, `bash "$SCR/launcher_stub.sh"` and `bash "$SCR/drift_stub.sh"`. All must be green. Tick tasks.md 6.1.
- [ ] **Step 2:** Final whole-branch review by one fresh reviewer (native execution).
- [ ] **Step 3:** Push and open the PR with `/pr-description`. Title: `feat: bound predictor and images-downloader concurrency with Argo semaphores (#98)`. The body should include:
  - the change id;
  - the BREAKING operator note;
  - the Task 4 baseline drift output;
  - section 7 as unchecked, post-merge boxes.

  Never merge.

### Task 7: After merge (owner go-ahead per cluster step)

Carry out tasks.md 7.0–7.6, then 8.1–8.6, in a post-merge PR that ticks section 7, archives the change and repoints its links. No roadmap edit or issue filing without the owner's approval of each draft.
