# Pipeline Concurrency Semaphores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the pipeline to at most 5 concurrent predictor tasks and 5 concurrent images-downloader tasks namespace-wide, via Argo ConfigMap-backed semaphores (#98).

**Architecture:** A new ConfigMap `sleap-roots-pipeline-semaphores` holds two limits. The `predictor` and `images-downloader` WorkflowTemplates acquire one key each through `synchronization.semaphores[].configMapKeyRef`. The launcher creates the ConfigMap if absent; `check_manifests.py` asserts the wiring offline; `check_cluster_drift.sh` compares the live ConfigMap.

**Tech Stack:** Argo Workflows v3.6.7 controller (CLI v3.6.5 in WSL), Kubernetes ConfigMap, bash, Python 3 + PyYAML (the repo's existing check scripts).

**Spec:** `openspec/changes/add-pipeline-concurrency-semaphores/` (proposal.md, design.md, specs/per-batch-pipeline/spec.md) and `docs/superpowers/specs/2026-09-30-pipeline-concurrency-semaphores-design.md`.

## Global Constraints

- ConfigMap name `sleap-roots-pipeline-semaphores`, file `sleap-roots-pipeline-semaphores.yaml`, namespace `runai-busch-lab`, label `project: busch-lab`.
- Keys and values exactly: `pipeline-gpu: "5"` (predictor), `pipeline-stage-in: "5"` (images-downloader). Values are quoted strings.
- Use the plural `synchronization.semaphores:` list, never the deprecated singular `semaphore:`.
- `pipeline-gpu` ≤ 10, derived at predictor `gpu-memory: "8192"` (0.18 GPU per pod → 5 per GPU × 2 GPUs).
- Do not touch or assert anything about the `local-WSL2-*` manifests: unmaintained, to be removed later.
- The launcher creates the ConfigMap only if absent, never updates it, and aborts before registering templates if it cannot read it.
- No cluster-changing command (`kubectl create/apply/edit`, `argo template create/update`, `argo submit/delete`) runs without the owner's explicit go-ahead for that step. Read-only `kubectl get`, `argo list/get` are fine.
- `argo` and `kubectl` exist only in WSL: invoke as `wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; cd /mnt/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98 && <cmd>'` from PowerShell.
- Match the surrounding files' comment density: these manifests carry dense, dated, reasoned comments.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **An unquoted integer in the ConfigMap** (`pipeline-gpu: 5`): `kubectl create` rejects non-string `data` values, so the deploy fails. The check must require a quoted decimal string, not just "parses as int". (Task 1, mutation M3.)
2. **The deprecated singular `semaphore:` key**, or a `mutex`, on a gated template: it lints but isn't the list form the spec requires. The check asserts neither is present. (Task 1, mutation M5.)
3. **A future `gpu-memory` bump without re-deriving the ≤ 10 bound**: the bound silently stops meaning "fits the quota". The check pins the predictor's `gpu-memory` to `"8192"`, so a bump forces someone to revisit it. (Task 1, mutation M6.)
4. **The launcher run without a working kubeconfig**: it must abort before `argo template update`, not skip the ConfigMap step and register templates whose gate may not exist. (Task 2, text assertion plus a stubbed-kubectl run.)
5. **The drift check when the live ConfigMap is missing, or a live retune differs**: it must report drift (exit 1), must never downgrade a CHECK FAILED (exit 2) to exit 1, and must never report sync when the comparison itself crashes. (Task 3, live read-only run against the pre-deploy cluster.)

---

### Task 1: ConfigMap, template gates, and their manifest assertions

**Files:**
- Create: `sleap-roots-pipeline-semaphores.yaml`
- Modify: `sleap-roots-predictor-template.yaml` (insert after `priorityClassName: high`, before `retryStrategy:`)
- Modify: `sleap-roots-images-downloader-template.yaml` (insert after `priorityClassName: interactive-preemptible`, before `retryStrategy:`)
- Modify: `scripts/check_manifests.py` (constants near `BATCH_STAGES`; new block at the end of `main()`, just before the final `print()`)
- Test: `scripts/check_manifests.py` itself, plus a throwaway mutation harness in the session scratchpad (not committed)

**Interfaces:**
- Produces: constants `SEMAPHORES = "sleap-roots-pipeline-semaphores.yaml"`, `SEMAPHORE_CM = "sleap-roots-pipeline-semaphores"`, `SEMAPHORE_KEY_BY_STAGE = {"predictor": "pipeline-gpu", "images-downloader": "pipeline-stage-in"}`, `GPU_SLICE_CAPACITY = 10`, `GPU_SLICE_MEMORY = "8192"`. Task 2 reuses `SEMAPHORES` and `SEMAPHORE_CM`.

- [ ] **Step 1: Add the constants and failing assertions to `check_manifests.py`**

After the `BATCH_STAGES` dict, add:

```python
# #98: namespace-wide concurrency limits. Each gated stage acquires ONE key of one ConfigMap.
SEMAPHORES = "sleap-roots-pipeline-semaphores.yaml"
SEMAPHORE_CM = "sleap-roots-pipeline-semaphores"
SEMAPHORE_KEY_BY_STAGE = {
    "predictor": "pipeline-gpu",
    "images-downloader": "pipeline-stage-in",
}
# Upper bound on pipeline-gpu: predictor slices busch-lab's 2-GPU deserved quota can hold. A live
# predictor pod's RunAI GPU ConfigMap records gpu-memory 8192 MB as RUNAI_NUM_OF_GPUS 0.18
# (2026-09-30), so floor(1/0.18) = 5 per GPU, 10 across 2. Valid ONLY at that gpu-memory, which is
# why the predictor's annotation is pinned below: bumping it must force this bound to be re-derived.
GPU_SLICE_CAPACITY = 10
GPU_SLICE_MEMORY = "8192"
SEMAPHORE_VALUE_RE = re.compile(r"^[1-9][0-9]*$")
```

At the end of `main()`, immediately before the final `print()`, add:

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
    for stage, key in SEMAPHORE_KEY_BY_STAGE.items():
        tmpl = load(BATCH_STAGES[stage])["spec"]["templates"][0]
        sync = tmpl.get("synchronization") or {}
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
        value = sem_data.get(key)
        # A quoted decimal string: kubectl rejects non-string ConfigMap data, so an unquoted 5
        # would lint here and fail at deploy.
        check(
            f"ConfigMap {key} is a quoted decimal integer >= 1",
            isinstance(value, str) and bool(SEMAPHORE_VALUE_RE.match(value)),
            True,
        )
    check(
        "ConfigMap defines no key that no template acquires",
        sorted(set(sem_data) - set(SEMAPHORE_KEY_BY_STAGE.values())),
        [],
    )
    gpu = sem_data.get("pipeline-gpu")
    check(
        f"pipeline-gpu fits the quota's slice capacity (<= {GPU_SLICE_CAPACITY})",
        isinstance(gpu, str) and bool(SEMAPHORE_VALUE_RE.match(gpu)) and int(gpu) <= GPU_SLICE_CAPACITY,
        True,
    )
    pred_tmpl = load(BATCH_STAGES["predictor"])["spec"]["templates"][0]
    check(
        "predictor gpu-memory is the value GPU_SLICE_CAPACITY was derived at",
        ((pred_tmpl.get("metadata") or {}).get("annotations") or {}).get("gpu-memory"),
        GPU_SLICE_MEMORY,
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/check_manifests.py`
Expected: a `FileNotFoundError` traceback for `sleap-roots-pipeline-semaphores.yaml` (the ConfigMap doesn't exist yet).

- [ ] **Step 3: Create `sleap-roots-pipeline-semaphores.yaml`**

```yaml
# Namespace-wide concurrency limits for the per-batch pipeline (#98; A4 design §9).
#
# The `predictor` template acquires `pipeline-gpu`, the `images-downloader` template acquires
# `pipeline-stage-in`, via synchronization.semaphores[].configMapKeyRef. The pool is shared by
# EVERY Workflow in runai-busch-lab that uses those templates -- Bloom prod, Bloom staging and
# manual runs alike -- because they share this namespace's 2-GPU deserved quota.
#
# Why: Bloom submits every 25-scan batch of a run at once (bloom#964), and nothing else bounds how
# many run together. Unbounded, a large experiment queues non-preemptible predictor pods far past
# the quota (NonPreemptibleOverQuota) and fills the namespace with retrying downloader pods.
#
# Values (Argo v3.6.7 semantics, read from source 2026-09-30):
#   - One slot = one TASK, held across all its retries AND the backoff between them.
#   - A task waiting for a slot is a Pending node with NO pod ("Waiting for
#     runai-busch-lab/ConfigMap/sleap-roots-pipeline-semaphores/<key> lock"), queued by Workflow
#     priority then creation time.
#   - The limit is re-read on every acquire, so a live edit takes effect with no restart:
#       kubectl edit configmap sleap-roots-pipeline-semaphores -n runai-busch-lab
#     A live value that differs from this file is reported by scripts/check_cluster_drift.sh.
#   - pipeline-gpu: 5 predictors = 0.9 GPU (8192 MB = 0.18 GPU each). Hard ceiling 10, the
#     quota's slice capacity; scripts/check_manifests.py enforces it.
#
# DEPLOY ORDER: create this ConfigMap BEFORE `argo template update`-ing either gated template. A
# missing ConfigMap or key is an ERROR in Argo, not a wait: the node is marked Error, the DAG stops
# (continueOn is `failed` only) and the run ends red. runai_run_pipeline.sh creates it if absent
# and never overwrites a live one.
#
# Values MUST be quoted: ConfigMap data is string-only and kubectl rejects a bare integer.
apiVersion: v1
kind: ConfigMap
metadata:
  name: sleap-roots-pipeline-semaphores
  namespace: runai-busch-lab
  labels:
    project: busch-lab
data:
  pipeline-gpu: "5"
  pipeline-stage-in: "5"
```

- [ ] **Step 4: Run to verify the template assertions fail**

Run: `python scripts/check_manifests.py`
Expected: exit 1. The ConfigMap assertions PASS; `predictor acquires exactly its own semaphore key` and `images-downloader acquires exactly its own semaphore key` FAIL with `got [], expected [{'name': ..., 'key': ...}]`.

- [ ] **Step 5: Gate the predictor template**

In `sleap-roots-predictor-template.yaml`, between the `priorityClassName: high` line and `retryStrategy:`, insert (same 6-space indent as `priorityClassName`):

```yaml
      # #98: at most `pipeline-gpu` predictor TASKS run at once across runai-busch-lab (prod,
      # staging and manual runs share the pool, as they share the 2-GPU quota). Bloom submits every
      # batch of a run at once (bloom#964), and without this a large experiment queued its
      # non-preemptible pods far past the quota. Argo v3.6.7, read from source: the slot is taken
      # under the RETRY node, so it is held across every attempt below AND the backoff between
      # them (a deterministically failing batch holds it ~14m); a task waiting for a slot is a
      # Pending node with no pod. A MISSING ConfigMap or key is an Error, not a wait -- create
      # sleap-roots-pipeline-semaphores.yaml before updating this template. Limit and rationale:
      # that file.
      synchronization:
        semaphores:
          - configMapKeyRef:
              name: sleap-roots-pipeline-semaphores
              key: pipeline-gpu
```

- [ ] **Step 6: Gate the images-downloader template**

In `sleap-roots-images-downloader-template.yaml`, between `priorityClassName: interactive-preemptible` and `retryStrategy:`, insert:

```yaml
      # #98: at most `pipeline-stage-in` downloader TASKS run at once across runai-busch-lab. This
      # stage is CPU-only, but it is where a large trigger's pod flood lands first: every batch of
      # a run starts here at once, and each failing attempt below is another pod. Same v3.6.7
      # semantics as the predictor's gate (slot held across retries; waiting task has no pod;
      # missing ConfigMap or key = Error, so create sleap-roots-pipeline-semaphores.yaml first).
      # Limit and rationale: that file.
      synchronization:
        semaphores:
          - configMapKeyRef:
              name: sleap-roots-pipeline-semaphores
              key: pipeline-stage-in
```

- [ ] **Step 7: Run to verify all assertions pass**

Run: `python scripts/check_manifests.py`
Expected: `=== ALL N ASSERTIONS PASS ===`, where N is the `main` count plus the new ones.

- [ ] **Step 8: Lint offline**

Run (PowerShell): `wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; cd /mnt/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98 && bash scripts/lint_manifests.sh'`
Expected: `Linting 6 manifests together` (the ConfigMap is not globbed) and no lint errors.

- [ ] **Step 9: Mutation-check the new assertions**

Write `<scratchpad>/mutate.py`. It copies the worktree's tracked files to a temp dir, applies one mutation at a time, runs that copy's `scripts/check_manifests.py`, and requires exit 1 with the named assertion in the output:

```python
import pathlib, shutil, subprocess, sys, tempfile
SRC = pathlib.Path(r"C:\repos\sleap-roots-pipeline\.worktrees\argo-semaphore-98")
CM, PRED, DL = "sleap-roots-pipeline-semaphores.yaml", "sleap-roots-predictor-template.yaml", "sleap-roots-images-downloader-template.yaml"
M = [
    ("M1 gpu over capacity", CM, 'pipeline-gpu: "5"', 'pipeline-gpu: "11"', "fits the quota's slice capacity"),
    ("M2 zero", CM, 'pipeline-stage-in: "5"', 'pipeline-stage-in: "0"', "pipeline-stage-in is a quoted decimal"),
    ("M3 unquoted", CM, 'pipeline-gpu: "5"', "pipeline-gpu: 5", "pipeline-gpu is a quoted decimal"),
    ("M4 wrong key", DL, "key: pipeline-stage-in", "key: pipeline-gpu", "images-downloader acquires exactly"),
    ("M5 singular", PRED, "        semaphores:\n          - configMapKeyRef:", "        semaphore:\n            configMapKeyRef:", "predictor uses only the plural"),
    ("M6 gpu-memory bump", PRED, 'gpu-memory: "8192"', 'gpu-memory: "12288"', "predictor gpu-memory is the value"),
    ("M7 extra key", CM, 'pipeline-stage-in: "5"', 'pipeline-stage-in: "5"\n  unused: "1"', "defines no key that no template"),
]
bad = 0
for label, f, old, new, expect in M:
    with tempfile.TemporaryDirectory() as d:
        dst = pathlib.Path(d) / "r"
        shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns(".git"))
        p = dst / f; s = p.read_text(encoding="utf-8")
        assert s.count(old) == 1, (label, "anchor not unique/found")
        p.write_text(s.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, str(dst / "scripts/check_manifests.py")], capture_output=True, text=True)
        ok = r.returncode == 1 and any(l.startswith("FAIL") and expect in l for l in r.stdout.splitlines())
        print(("OK   " if ok else "MISS ") + label); bad += not ok
sys.exit(bad)
```

Run: `python <scratchpad>/mutate.py`
Expected: seven `OK` lines, exit 0.

- [ ] **Step 10: Commit**

```bash
git add sleap-roots-pipeline-semaphores.yaml sleap-roots-predictor-template.yaml sleap-roots-images-downloader-template.yaml scripts/check_manifests.py
git commit -m "feat(templates): gate predictor and images-downloader on namespace semaphores (#98)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Launcher creates the ConfigMap if absent

**Files:**
- Modify: `runai_run_pipeline.sh` (header manual-steps comment, lines 4-14; new block immediately before `echo -e "${YELLOW}Registering WorkflowTemplates...`)
- Modify: `scripts/check_manifests.py` (launcher assertions, appended to Task 1's block)

**Interfaces:**
- Consumes: `SEMAPHORES`, `SEMAPHORE_CM` from Task 1.

- [ ] **Step 1: Add failing launcher assertions**

Append to the Task 1 block in `main()`:

```python
    # --- Scenario: Launcher creates the semaphore ConfigMap only when absent, before templates ---
    launcher = (ROOT / "runai_run_pipeline.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in launcher.splitlines() if not l.lstrip().startswith("#"))
    check("launcher names the semaphore ConfigMap file", f'SEMAPHORES_FILE="{SEMAPHORES}"' in code, True)
    check("launcher names the semaphore ConfigMap", f'SEMAPHORES_CM="{SEMAPHORE_CM}"' in code, True)
    get_i = code.find('kubectl get configmap "$SEMAPHORES_CM" -n "$NAMESPACE" --ignore-not-found -o name')
    create_i = code.find('kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"')
    loop_i = code.find('for tmpl_file in "${TEMPLATES[@]}"')
    check("launcher reads the ConfigMap with --ignore-not-found", get_i >= 0, True)
    check(
        "launcher's ConfigMap get, then create, both precede the template loop",
        0 <= get_i < create_i < loop_i,
        True,
    )
    check(
        "launcher creates only on the empty-result branch",
        bool(re.search(r'if \[ -z "\$existing" \]; then\s+[^\n]*\n?\s*kubectl create -f "\$SEMAPHORES_FILE"', code)),
        True,
    )
    check(
        "launcher aborts when the ConfigMap get itself fails",
        bool(re.search(r"if ! existing=\$\(kubectl get configmap[^\n]*\); then[\s\S]*?exit 1", code)),
        True,
    )
    check(
        "launcher never applies, replaces, edits or patches a ConfigMap",
        re.findall(r"kubectl\s+(?:apply|replace|edit|patch)\b", code),
        [],
    )
```

Run: `python scripts/check_manifests.py`
Expected: exit 1 with the six new launcher assertions FAILing.

- [ ] **Step 2: Add the launcher block**

Immediately before `echo -e "${YELLOW}Registering WorkflowTemplates in namespace '$NAMESPACE'...${NC}"`, insert:

```bash
# #98: the predictor and images-downloader templates acquire slots from this ConfigMap, and in
# Argo a MISSING ConfigMap is an Error, not a wait -- so it must exist before either template is
# registered. Create it only if absent; never update it, so a manual run cannot silently undo an
# operator's live retune (`kubectl edit configmap sleap-roots-pipeline-semaphores`). Repo changes to
# the limits are deployed deliberately, and check_cluster_drift.sh reports any live difference.
# This is the launcher's only kubectl use: the Argo Server it otherwise talks to has no ConfigMap
# API, so it needs a working KUBECONFIG (in WSL, kubectl lives in $HOME/bin).
SEMAPHORES_FILE="sleap-roots-pipeline-semaphores.yaml"
SEMAPHORES_CM="sleap-roots-pipeline-semaphores"
if ! command -v kubectl >/dev/null 2>&1; then
  echo -e "${RED}✗ kubectl not found (needed to ensure $SEMAPHORES_CM exists). In WSL: export PATH=\$HOME/bin:\$PATH${NC}" >&2
  exit 1
fi
if ! existing=$(kubectl get configmap "$SEMAPHORES_CM" -n "$NAMESPACE" --ignore-not-found -o name); then
  echo -e "${RED}✗ Could not read ConfigMap $SEMAPHORES_CM in $NAMESPACE (check KUBECONFIG/VPN). Not registering templates whose semaphore may not exist.${NC}" >&2
  exit 1
fi
if [ -z "$existing" ]; then
  echo -e "${YELLOW}+ Creating semaphore ConfigMap: $SEMAPHORES_CM${NC}"
  kubectl create -f "$SEMAPHORES_FILE" -n "$NAMESPACE"
else
  echo -e "${GREEN}✓ Semaphore ConfigMap $SEMAPHORES_CM exists; leaving its live limits as they are${NC}"
fi
```

In the header comment, insert as the first command after the `export KUBECONFIG=...` line:

```bash
#   kubectl create -f sleap-roots-pipeline-semaphores.yaml             # once; before any template (#98)
```

- [ ] **Step 3: Verify syntax, assertions, and behaviour without a kubeconfig**

Run: `bash -n runai_run_pipeline.sh && python scripts/check_manifests.py`
Expected: no syntax error; `=== ALL N ASSERTIONS PASS ===`.

Behaviour (Review Focus 4): the script's first cluster call must be the ConfigMap `get`, so a failing `kubectl` must stop it before any `argo` call. Stub both on PATH. Create `<scratchpad>/stub/kubectl` containing `#!/bin/sh\necho "stub: no cluster" >&2; exit 1` and `<scratchpad>/stub/argo` containing `#!/bin/sh\necho "ARGO CALLED: $*"; exit 0`, `chmod +x` both, then:

Run (Git Bash): `PATH="<scratchpad>/stub:$PATH" bash runai_run_pipeline.sh; echo "exit=$?"`
Expected: the `✗ Could not read ConfigMap` line, `exit=1`, and **no** `ARGO CALLED` line.

- [ ] **Step 4: Commit**

```bash
git add runai_run_pipeline.sh scripts/check_manifests.py
git commit -m "feat(launcher): create the semaphore ConfigMap if absent before registering templates (#98)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Drift check covers the semaphore ConfigMap

**Files:**
- Modify: `scripts/check_cluster_drift.sh` (new block after the template `for` loop's `done`, before `echo "Live image pins in $NS:"`)

- [ ] **Step 1: Capture the pre-change baseline (read-only)**

Run (PowerShell): `wsl -e bash /mnt/c/repos/sleap-roots-pipeline/.worktrees/argo-semaphore-98/scripts/check_cluster_drift.sh; echo "exit=$LASTEXITCODE"`
Expected: the five templates' current status. At this point the live predictor and downloader templates lack the gate, so they report `DRIFT`; exit 1. Record the output for the PR.

- [ ] **Step 2: Add the ConfigMap comparison**

After the template loop's `done` (before the blank `echo` preceding `Live image pins`), insert:

```bash

# #98: the semaphore ConfigMap the predictor and images-downloader templates acquire from. Only
# its `data` (the limits) is compared -- metadata carries server-stamped fields. A live value that
# differs is DRIFT even when deliberate (an operator's temporary retune): the point is that nobody
# forgets one. A MISSING ConfigMap is drift too, and a serious one: the gated templates Error
# without it. Never lowers drift=2 (CHECK FAILED) to 1.
SEM_FILE="sleap-roots-pipeline-semaphores.yaml"
sem_name="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['metadata']['name'])" "$SEM_FILE")"
if ! kubectl get configmap "$sem_name" -n "$NS" -o yaml > "$tmp/sem-live.yaml" 2>/dev/null; then
  echo "NOT CREATED     $sem_name  ($SEM_FILE) -- the gated templates Error without it"
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

Also add a line to the script's header `# WHY` block: `# Also compares the #98 semaphore ConfigMap's data (the concurrency limits).`

- [ ] **Step 3: Verify syntax and the missing-ConfigMap path live (read-only)**

Run: `bash -n scripts/check_cluster_drift.sh`, then the Step 1 command again.
Expected: the same template lines as the baseline, plus `NOT CREATED     sleap-roots-pipeline-semaphores ...` (it doesn't exist in the cluster yet); exit 1.

- [ ] **Step 4: Verify the compare branches offline**

Run the heredoc's Python directly against local files. Copy the repo ConfigMap to `<scratchpad>/live-same.yaml` and `<scratchpad>/live-diff.yaml`; in the latter change `pipeline-gpu: "5"` to `"2"`. Then extract the heredoc body to `<scratchpad>/semcmp.py` and run:
- `python3 <scratchpad>/semcmp.py <scratchpad>/live-same.yaml sleap-roots-pipeline-semaphores.yaml; echo $?` → `0`
- `python3 <scratchpad>/semcmp.py <scratchpad>/live-diff.yaml sleap-roots-pipeline-semaphores.yaml; echo $?` → `pipeline-gpu: repo='5' live='2'`, `3`
- `python3 <scratchpad>/semcmp.py /nonexistent sleap-roots-pipeline-semaphores.yaml; echo $?` → a traceback and `1` (neither 0 nor 3, so the script reports CHECK FAILED)

- [ ] **Step 5: Commit**

```bash
git add scripts/check_cluster_drift.sh
git commit -m "feat(drift): compare the semaphore ConfigMap's limits against the repo (#98)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Docs and pre-PR sweep

**Files:**
- Modify: `docs/cluster-identities.md` (new paragraph after the predictor-`high` bullet and its "So non-preemptible work…" paragraph, before `**\`argo submit -n <ns>\` does not redirect…`)
- Modify: `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` (§9, after the "Argo semaphore" bullet)
- Modify: `openspec/project.md` (A4 still-open list, line ~25; External Dependencies, line ~177)
- Modify: `openspec/changes/add-pipeline-concurrency-semaphores/tasks.md` (tick 1.x–4.x)

- [ ] **Step 1: `docs/cluster-identities.md`**

Insert:

```markdown
**The pipeline bounds its own share of the quota (#98).** The `predictor` and `images-downloader`
templates acquire slots from the ConfigMap `sleap-roots-pipeline-semaphores`
(`sleap-roots-pipeline-semaphores.yaml`): `pipeline-gpu` (5 predictor tasks = 0.9 GPU at 0.18 GPU
each; ceiling 10) and `pipeline-stage-in` (5 downloader tasks). The pool is namespace-wide, shared by
Bloom prod, Bloom staging and manual runs. Excess tasks wait in Argo as Pending nodes with no pod, so
a large Bloom trigger no longer queues past the quota. To free GPUs for colleagues, lower the limit
live (`kubectl edit configmap sleap-roots-pipeline-semaphores -n runai-busch-lab`; it takes effect
on the next acquire), then restore it; `scripts/check_cluster_drift.sh` reports the difference until
you do. This does not replace checking who holds the quota before submitting: it caps the
pipeline's use, not anyone else's.
```

- [ ] **Step 2: A4 design §9 annotation**

After the "Argo semaphore (ConfigMap-backed)" bullet, add:

```markdown
  **Built 2026-09-30 ([#98](https://github.com/talmolab/sleap-roots-pipeline/issues/98)):**
  template-level, not per-batch Workflow: `predictor` acquires `pipeline-gpu` (5) and
  `images-downloader` acquires `pipeline-stage-in` (5) from ConfigMap
  `sleap-roots-pipeline-semaphores` in `runai-busch-lab`. The quota in question is **busch-lab's**
  (2 GPUs), not talmo-lab's as the first bullet says. See
  `openspec/changes/add-pipeline-concurrency-semaphores/design.md`.
```

- [ ] **Step 3: `openspec/project.md`**

In Purpose, change "the Bloom-side trigger route/dispatch worker (so a UI click submits this workflow
instead of a manual `argo submit`), the Argo semaphore for concurrent-batch concurrency, and per-run
path isolation" by removing "the Argo semaphore for concurrent-batch concurrency, " (read the
surrounding sentence first and keep it grammatical; do not change its other claims). Under External
Dependencies, after "requires `runai login` + an exported `ARGO_TOKEN`.", add: "`runai_run_pipeline.sh`
also needs a working `KUBECONFIG` for `kubectl`, to create the #98 semaphore ConfigMap if absent."

Run: `grep -n "semaphore" openspec/project.md`
Expected: only the new External Dependencies line.

- [ ] **Step 4: Full offline sweep**

Run: `bash scripts/check_all.sh`
Expected: `=== OK: all suites pass ===`.
Run: the Task 1 Step 8 lint command. Expected: clean.
Run: `openspec validate add-pipeline-concurrency-semaphores --strict`. Expected: `is valid`.

- [ ] **Step 5: Tick tasks 1.1–4.4 in the OpenSpec `tasks.md`, then commit**

```bash
git add docs/cluster-identities.md docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md openspec/project.md openspec/changes/add-pipeline-concurrency-semaphores/tasks.md
git commit -m "docs: document the #98 concurrency semaphores; annotate A4 design §9

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: PR, then deploy and live verification (each cluster step gated on the owner)

- [ ] **Step 1: Push the branch and open a PR** with `/pr-description`. Reference `add-pipeline-concurrency-semaphores` and #98, and include the Task 3 Step 1/3 drift outputs. Do not merge.
- [ ] **Step 2 (go-ahead required):** `argo list -n runai-busch-lab`; confirm no `sleap-roots-pipeline-*` Workflow is Running or Pending.
- [ ] **Step 3 (go-ahead required):** `kubectl create -f sleap-roots-pipeline-semaphores.yaml`, then `argo template update` the images-downloader and predictor templates. (Deploying from the branch before merge, or after merge from `main`, is the owner's call.)
- [ ] **Step 4:** `check_cluster_drift.sh` → exit 0, with `IN SYNC sleap-roots-pipeline-semaphores`.
- [ ] **Step 5 (go-ahead required):** the lock test, OpenSpec task 5.4. Set both keys to `"1"` live, submit two labelled manual runs, and confirm the second run's nodes are Pending with the lock message and no pod. Both runs must end `Succeeded`.
- [ ] **Step 6 (go-ahead required):** restore both keys to `"5"`; drift check → exit 0. Tick 5.x in `tasks.md` and push.
- [ ] **Step 7:** after merge, draft the roadmap update and the three follow-up issues (tasks 6.1–6.4) for the owner's approval. File nothing without it.
