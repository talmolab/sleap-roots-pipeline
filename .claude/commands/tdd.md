---
description: Test-driven development for this repo — red → green → refactor over the manifest and doc assertion suites
---

# Test-Driven Development (TDD)

Write the assertion first, watch it fail for the right reason, then make the minimum
manifest/script/doc change that turns it green.

This repo has no application code, so "the test" is one of:

| What changes | Where the test goes | Run with (`/test`, from **Git Bash**) |
|---|---|---|
| A manifest convention (priority class, quota label, retry shape, mounts, pins, env, semaphores) | a `check(...)` in `scripts/check_manifests.py` | `uv run --no-project --with pyyaml python scripts/check_manifests.py` |
| A claim in a doc `check_docs.py` reads (see `/test` for the list) | a `check(...)` in `scripts/check_docs.py` | `uv run --no-project python scripts/check_docs.py` |
| Argo schema / `templateRef` resolution | nothing to write — `/lint` already covers it | `wsl -e bash scripts/lint_manifests.sh` |
| Behavior only the live cluster shows (GPU allocation, scheduling, quota, pod logs) | an **acceptance test** — see [Live acceptance](#live-acceptance-tests) | `argo submit` / `kubectl` via WSL (`.claude/skills/runai/SKILL.md` §1a) |

**Run the suites from Git Bash, never PowerShell** — in PowerShell `bash` is the WSL launcher
and `check_manifests.py`'s exit-gate assertion fails for the wrong reason. See `/test`.

Both suites use the same helper, `check(label, got, want)`, which prints `PASS`/`FAIL` and
makes the script exit 1 on any failure.

## Phase 1: Red — write the failing assertion

Add the assertion inside `main()`, next to the related ones. Make `got` something read from
the file, not a value you typed. The shape (names in `<>` are yours to fill):

```python
# scripts/check_manifests.py — load(), BATCH_STAGES and check() are module-level
tmpl = load(BATCH_STAGES["<stage>"])["spec"]["templates"][0]
check(
    "<stage> carries <the behavior the scenario requires>",
    ((tmpl.get("metadata") or {}).get("annotations") or {}).get("<annotation-key>"),
    "<required value>",
)
```

```python
# scripts/check_docs.py — inside main(), `readme`, `ident` and `skill` are already
# read and whitespace-normalised by norm(), so assertions survive re-wrapping
check(
    "README: <the claim that must hold>",
    "<the exact phrase the doc must contain>" in readme,
    True,
)
```

Use a fresh local name (don't reuse one `main()` already binds, e.g. `pred_tmpl`). Assert the
behavior the spec scenario describes, and add the negative (`... False`, or `[]` for "nothing
offending") when the bug is something *present* that must go away.

## Phase 2: Confirm red

```bash
uv run --no-project --with pyyaml python scripts/check_manifests.py | grep -E "FAIL|==="
```

The new assertion must fail **with the value you expected to see today** (e.g. `got None,
expected 'main'`), and it must be the **only** new failure. If it fails with a
`KeyError`/traceback, or passes, the test is wrong — fix the test before touching any manifest.
If an *existing* assertion fails too, stop: check you are in Git Bash (see `/test`) before
suspecting anything else.

A task may not both write an assertion and make the edit it asserts on — the red must be
observed between them. Record the FAIL line you saw; it goes in the commit body (Phase 6).

## Phase 3: Green — minimum change

Edit the manifest/doc until the assertion passes. Don't weaken the assertion to make it pass;
if the assertion was wrong, fix it and say why in the commit message.

## Phase 4: Refactor

Tidy comments and wording with the suite as the safety net. Check the local
(`local-WSL2-*.yaml`) variant for **mount/path parity** — not byte parity: the locals
deliberately differ in template names and `retryStrategy` limits, and the local predictor's
`nvidia.com/gpu: 1` is a known stale spot, so don't mirror GPU/scheduling changes
(`openspec/project.md`, "Cluster vs. local parity").

## Phase 5: Verify

```bash
uv run --no-project --with pyyaml bash scripts/check_all.sh   # /test — both suites
wsl -e bash scripts/lint_manifests.sh                          # /lint — if a manifest changed
```

## Phase 6: Commit

Commit the assertion and the change that turns it green **together**, and paste the red FAIL
line from Phase 2 into the commit body — that is the evidence of red. **Never commit a red
suite**: `/test` must pass at every commit.

```bash
git add scripts/check_manifests.py <manifest>
git commit -m "fix(<stage>): <what changed>

check_manifests.py asserts <behavior>. Red before the fix:
  FAIL  <label>: got <x>, expected <y>"
```

## Live acceptance tests

For behavior only the cluster shows. `runai-busch-lab` is shared by Bloom's staging **and**
production dispatch, so **never register a template from an unmerged branch** — an
`argo template update` there changes every future dispatch.

1. **Red baseline (before the fix).** Record the bug as observed: the live pod spec,
   `kubectl describe pod` events, or a pod log line, with the workflow name and date, in the
   change's `tasks.md`/design doc. If no baseline is observable (a new capability), say why and
   name the observation that will go red → green. "Not observed" is not a baseline.
2. **Pre-merge (optional, recommended for GPU/scheduling changes).** Submit a **throwaway
   Workflow with the edited template inlined** (a `templates:` entry, no `templateRef`) — nothing
   registered, nothing shared changed — and run the same observation.
3. **After merge, from `main`.** Save a rollback copy of what is live
   (`kubectl get workflowtemplate <name> -n runai-busch-lab -o yaml > <name>.pre.yaml`), run
   `wsl -e bash scripts/check_cluster_drift.sh`, register (`argo template update`, or `create`
   for a new template), re-run the drift check, then re-run the **same** observation on the first
   real run and record it green next to the baseline.

## Testing patterns that transfer

- **Vector tables** — when a script's behavior is a function of inputs, execute it over a table
  of input → expected outcome (`check_manifests.py` already runs the exit gate this way).
- **Negative cases** — assert the bad thing is absent (`[]`), not only that the good thing is present.
- **Every member** — when a rule applies to all stages/templates, loop over all of them so a new
  template can't slip past.

## OpenSpec alignment

Every delta-spec scenario that can be read off the manifests or docs maps to a `check(...)`;
scenarios that need the cluster map to an acceptance task (above). Tick each `tasks.md` item as
its red → green commit lands, then:

```bash
openspec validate <change-id> --strict
```

## Related Commands

- `/test` — run the assertion suites (and why Git Bash)
- `/lint` — lint the manifests
- `/pre-merge` — full gate before opening a PR
- `/new-feature` — the workflow this loop runs inside
