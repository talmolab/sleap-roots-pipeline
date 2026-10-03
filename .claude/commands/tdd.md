---
description: Test-driven development for this repo — red → green → refactor over the manifest and doc assertion suites
---

# Test-Driven Development (TDD)

Write the assertion first, watch it fail for the right reason, then make the minimum
manifest/script/doc change that turns it green.

This repo has no application code, so "the test" is one of:

| What changes | Where the test goes | Run with |
|---|---|---|
| A manifest convention (priority class, quota label, retry shape, mounts, pins, env, semaphores) | a `check(...)` in `scripts/check_manifests.py` | `uv run --no-project --with pyyaml python scripts/check_manifests.py` |
| A claim in `README.md`, `docs/cluster-identities.md`, or `.claude/skills/runai/SKILL.md` | a `check(...)` in `scripts/check_docs.py` | `uv run --no-project python scripts/check_docs.py` |
| Argo schema / `templateRef` resolution | nothing to write — `/lint` already covers it | `wsl -e bash scripts/lint_manifests.sh` |
| Behavior only the live cluster shows (GPU allocation, scheduling, quota, pod logs) | an **acceptance test**: a recorded red baseline + the same observation after the fix | `argo submit` / `kubectl` (via WSL — see `.claude/skills/runai/SKILL.md` §1a) |

Both suites use the same helper, `check(label, got, want)`, which prints `PASS`/`FAIL` and
makes the script exit 1 on any failure.

## Phase 1: Red — write the failing assertion

Add the assertion next to the related ones in `main()`. Make `got` something read from the
file, not a value you typed:

```python
# scripts/check_manifests.py
pred_tmpl = load(BATCH_STAGES["predictor"])["spec"]["templates"][0]
check(
    "predictor directs its GPU slice at the main container",
    ((pred_tmpl.get("metadata") or {}).get("annotations") or {}).get("gpu-fraction-container-name"),
    "main",
)
```

```python
# scripts/check_docs.py — doc text is whitespace-normalised by norm(), so
# assertions survive re-wrapping
check(
    "README: lint instructions point at the wrapper, not bare argo lint",
    "scripts/lint_manifests.sh" in readme,
    True,
)
```

Assert the behavior the spec scenario describes, and include the negative too (`... False`) when
the bug is something *present* that must go away.

## Phase 2: Confirm red

```bash
uv run --no-project --with pyyaml python scripts/check_manifests.py | grep -E "FAIL|==="
```

The new assertion must fail **with the value you expected to see today** (e.g. `got None,
expected 'main'`). If it fails with a `KeyError`/traceback, or passes, the test is wrong — fix
the test before touching any manifest.

**Live-cluster acceptance tests:** red means recording the bug as observed, before the fix, so
the after-state can be compared to it. Save the evidence (the pod spec, `kubectl describe pod`
events, or the pod log line) into the change's `tasks.md` or design doc with the workflow name
and date. A claim with no recorded baseline cannot later be shown fixed.

## Phase 3: Green — minimum change

Edit the manifest/doc until the assertion passes. Don't weaken the assertion to make it pass;
if the assertion was wrong, fix it and say why in the commit message.

```bash
uv run --no-project --with pyyaml python scripts/check_manifests.py | grep -E "FAIL|==="
```

## Phase 4: Refactor

Tidy comments and wording with the suite as the safety net. Keep cluster (`*.yaml`) and local
(`local-WSL2-*.yaml`) variants in sync where the change applies to both.

## Phase 5: Verify

```bash
# Both suites (the full test run)
uv run --no-project --with pyyaml bash scripts/check_all.sh

# Manifest lint (only if a manifest changed)
wsl -e bash scripts/lint_manifests.sh
```

For a live-cluster acceptance test, register the changed templates (after checking
`scripts/check_cluster_drift.sh` — it doubles as the rollback pre-image), re-run the same
observation you recorded as red, and record the green result alongside it.

## Phase 6: Commit

Commit the assertion and the fix together, or the assertion first if you want the red state in
history. `check_all.sh` must be green at every commit that touches a manifest or doc.

```bash
git add scripts/check_manifests.py sleap-roots-predictor-template.yaml
git commit -m "fix(predictor): <what changed>

- check_manifests.py asserts <behavior>; red before the fix (got <x>)"
```

## OpenSpec alignment

When the change has an OpenSpec proposal, every delta-spec scenario that can be read off the
manifests or docs should map to a `check(...)`; scenarios that need the cluster map to an
acceptance task. Then:

```bash
openspec validate <change-id> --strict
```

Tick the `tasks.md` items this cycle closes before committing.

## Related Commands

- `/test` — run the assertion suites
- `/lint` — lint the manifests
- `/pre-merge` — full gate before opening a PR
- `/new-feature` — the workflow this loop runs inside
