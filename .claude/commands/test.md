---
description: Run the repo's executable assertion suites (manifests + docs)
---

# Run Tests

This repo's test harness is two offline assertion suites. Neither needs `argo`, a cluster, VPN
or credentials.

## Commands

```bash
# Both suites — the full test run (use before every commit)
uv run --no-project --with pyyaml bash scripts/check_all.sh

# One suite at a time (faster during a /tdd loop)
uv run --no-project --with pyyaml python scripts/check_manifests.py
uv run --no-project python scripts/check_docs.py

# Only the failures and the summary
uv run --no-project --with pyyaml python scripts/check_manifests.py | grep -E "FAIL|==="
```

`uv run --no-project --with pyyaml` gives the scripts an isolated interpreter with PyYAML;
don't `pip install` into the base Python. `check_all.sh` uses whatever `python` is first on
`PATH` (or `$PYTHON`), which inside `uv run` is the isolated one.

Exit codes: `0` = every assertion holds, `1` = at least one failed. `check_all.sh` always runs
both suites so a failure in one doesn't hide a failure in the other.

## What each suite covers

| Suite | Asserts on | Typical assertions |
|---|---|---|
| `scripts/check_manifests.py` | the Workflow + every WorkflowTemplate + `sleap-roots-pipeline-semaphores.yaml` | DAG shape, priority classes, quota labels, credential isolation, retry shape, pin/digest hygiene, mount agreement, semaphores; **executes** the exit-gate script over a vector table |
| `scripts/check_docs.py` | `README.md`, `docs/cluster-identities.md`, `.claude/skills/runai/SKILL.md`, `docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md` (and each template's `priorityClassName`, to compare the docs against) | claims about cluster identities, credentials, log access, and priority classes stay true |

Both are the executable form of spec scenarios — `per-batch-pipeline` and
`cluster-access-docs` name them.

## What is NOT in the suite

- **Manifest lint** (`argo lint` schema + `templateRef` resolution) — `/lint`. Needs `argo`,
  which lives only in WSL.
- **Cluster drift** — `wsl -e bash scripts/check_cluster_drift.sh` compares what is
  *registered* in the cluster to this repo. Read-only, needs the busch-lab kubeconfig; run it
  before and after any `argo template update`. Parity with the cluster is measured, not asserted.
- **Live behavior** (GPU allocation, scheduling, quota) — an acceptance test on a real
  `argo submit`; see `/tdd`.
- **Local dry-run** — `local_run_pipeline_first_time.sh` is broken for the current DAG (#21).

## After running

1. **Fix failing assertions** by fixing the manifest/doc — not by weakening the assertion. If the
   assertion itself was wrong, fix it and say why in the commit.
2. **New behavior needs a new assertion**, written red-first (`/tdd`).
3. **Keep the suites offline and deterministic** — no network, no cluster, no wall-clock.

## Related Commands

- `/tdd` — the red → green loop over these suites
- `/lint` — manifest lint
- `/pre-merge` — full gate before opening a PR
