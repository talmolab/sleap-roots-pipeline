# Standardize `.claude/commands` against the lab templates — design

**Date:** 2026-10-02 · **Branch:** `chore/standardize-dev-commands` · **Status:** approved (plan table)

## Why

Running `/new-feature` on #117 produced a test-after `tasks.md` and skipped `/review-openspec`,
because this repo's `new-feature.md` (from A0, `f0d0c3a`) had dropped the canonical template's
TDD discipline and only listed `/review-openspec` under Related Commands. The A0 premise — "no
unit-test harness, so the test/TDD commands don't apply" — stopped being true when
`scripts/check_manifests.py` and `scripts/check_docs.py` landed: they are executable assertion
suites, and TDD applies to them like any other test.

Source of truth: the vault `standardize-dev-commands` skill and its
`references/commands/*.md.tmpl`. Sibling repos were read for reference only.

## Toolchain profile

| Slot | Value |
|---|---|
| `TEST` | `uv run --no-project --with pyyaml bash scripts/check_all.sh` — **from Git Bash**; in PowerShell `bash` is the WSL launcher and the suite gives a false FAIL (documented, not fixed in the script — user decision 2026-10-03) |
| `LINT` | `wsl -e bash scripts/lint_manifests.sh` (`argo` lives only in WSL) |
| live drift (not a gate) | `wsl -e bash scripts/check_cluster_drift.sh` |
| `OPENSPEC` | true — global `openspec` CLI (not `npx`) |
| `REPO` | `gh repo view --json nameWithOwner -q .nameWithOwner`, at runtime |
| N/A | `DEV`, `BUILD`, `TYPECHECK`, `COVERAGE`, `FORMAT`, `FORMAT_CHECK`, `CI` |

## Dispositions

| Command | Disposition |
|---|---|
| `new-feature` | UPDATE — TDD restored (red-first against the check scripts; live behavior = recorded red baseline); `/review-openspec` is a numbered step; implement via `/openspec:apply` + `/tdd` with `tasks.md` as the plan; `lint_manifests.sh`; dry-run qualified (#21); `/pre-merge` |
| `review-openspec` | UPDATE — subagent 2 = TDD & Verification; `lint_manifests.sh`; dry-run qualified; Guard N |
| `pr-description` | UPDATE — verification rows = `check_all.sh` / `lint_manifests.sh` / red-first |
| `review-pr` | UPDATE — Guard N; TDD check in lens 5; `lint_manifests.sh`; `/pre-merge` |
| `ci-debug` | UPDATE (heavily customized — FLAG in skill terms; its GitHub-Actions half is N/A until CI exists) — Guard N in `gh run`; `lint_manifests.sh`; Argo section kept, its commands wrapped in WSL with the right kubeconfig |
| `copilot-review` | UPDATE — Guard N; `/pre-merge` |
| `docs-review` | UPDATE — `lint_manifests.sh` + `check_docs.py` |
| `update-changelog` | UPDATE — Guard N in compare links |
| `cleanup-merged` | UPDATE (minimal) — `/pre-merge` in Related; `openspec list --specs` |
| `tdd`, `test`, `lint`, `pre-merge`, `validate-env` | ADD |
| `dev`, `coverage`, `fix-formatting`, `run-ci-locally` | SKIP — primary action N/A |
| `openspec/*` | KEEP — CLI-generated |

The seven UPDATEs are targeted patches over the A0 rendering, not full re-renders; universal
template content found missing in review (pr-description's `[!]` rationale, update-changelog's
Release Checklist and tips 6–7, review-openspec subagent 1's split/commit-boundary checks) was
restored.

Also:
- `openspec/project.md` Testing Strategy names the check scripts as the test harness, states
  the single live-acceptance rule, and adds red-first **`tasks.md` conventions** (overriding
  `openspec/AGENTS.md`'s CLI-managed "Write tests" last example, which seeded #117's ordering).
- `.claude/skills/runai/SKILL.md` §1a: the "commands invoke `argo lint`" sentence and the bare
  `argo lint --offline` example are corrected; the troubleshooting row's "Bloom's dispatch
  depends on" the namespace line is corrected (Bloom forces its own namespace).
- `README.md`: the Local Testing section is marked broken (#21) with runnable validation
  commands; the same Bloom-namespace claim in the offline-lint note is corrected.

**Live-acceptance rule** (stated identically in `/tdd`, `/pre-merge`, `/review-openspec`,
`/pr-description`, `project.md`): record the red baseline first; a pre-merge probe uses a
throwaway Workflow with the edited template inlined; never register a template from an unmerged
branch (`runai-busch-lab` is shared by Bloom staging and production); after merge, register from
`main` with a rollback copy and drift check, and re-run the same observation.

**Deferred to #117** (`fix-predictor-gpu-container-target`, in flight): the GPU-claim lines in
`review-pr`, `review-openspec` and `ci-debug`'s "no GPU" row (incl. its hardcoded issue link).

## OpenSpec scope

No change proposal. No living spec text changes — `cluster-access-docs` and
`per-batch-pipeline` name the check scripts as tools, which stays true; `project.md` is context,
not a spec; and `openspec validate --strict` rejects a delta-less change. The approved plan
table is the design.
