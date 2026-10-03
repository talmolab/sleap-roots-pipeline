---
description: End-to-end workflow for scoping, proposing, and implementing a new orchestration change using superpowers brainstorming, OpenSpec, and TDD.
---

You are starting a new feature workflow. The user's feature request is: $ARGUMENTS

This repo uses **two complementary planning systems** — they layer, they don't compete:

- **superpowers** (`brainstorming`, `subagent-driven-development`, `test-driven-development`) — drive the conversational design and implementation discipline
- **OpenSpec** (`openspec/`, `openspec` CLI) — produces durable spec deltas for any change that adds capabilities, modifies orchestration behavior, or affects architecture

For non-trivial changes, use BOTH. For tiny changes (typo, comment, image-tag bump), skip OpenSpec but still brainstorm intent first and still follow TDD — see **Tiny-change path** below.

> **Note on this repo:** `sleap-roots-pipeline` is a declarative **Argo/RunAI orchestration**
> repo — Argo `Workflow`/`WorkflowTemplate` YAML + shell launchers, no application code.
> "Implementation" means editing manifests/scripts/docs. The **test harness** is
> `scripts/check_manifests.py` (manifest conventions) + `scripts/check_docs.py` (doc claims),
> run together by `/test`; `/lint` runs `scripts/lint_manifests.sh` (Argo schema +
> `templateRef` resolution). Run `/test` from **Git Bash**, not PowerShell (see `/test`).
> Behavior only the live cluster can show (GPU allocation, scheduling, quota) is an
> **acceptance test** — red baseline first, never a template registered from an unmerged
> branch; `/tdd` has the rule. See `openspec/project.md`.

## Guardrails

- Do NOT write any manifest/script changes until the OpenSpec proposal (or, on the tiny-change path, the intended diff) is approved by the user.
- Follow OpenSpec conventions strictly — see `openspec/AGENTS.md` for the authoritative rules.
- **Use TDD.** Write the failing assertion first, run it, and see it fail *for the right
  reason* before editing any manifest or doc. A test written after the fix proves nothing.
- Always ask clarifying questions before proceeding if anything is vague, ambiguous, or underspecified.
- Keep changes within this repo's scope (orchestration). Stage-internal logic belongs in the
  sibling service repos (`sleap-roots-predict`, `sleap-roots`, `models-downloader`).

## Steps

1. **Ensure feature branch.** Check the current branch (`git branch --show-current`). If on `main`, ask the user what branch name to create — suggest a kebab-case, verb-led name based on the feature (e.g., `add-event-trigger`, `fix-gpu-fraction`). Create and switch to it before proceeding.

2. **Invoke `superpowers:brainstorming`.** This is mandatory in this workflow — even for changes that seem simple. The brainstorming skill explores user intent, requirements, and design through clarifying questions, then produces a design doc at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. Do not skip. **Stop when brainstorming offers to hand off to `superpowers:writing-plans`** — in this workflow the OpenSpec `tasks.md` (step 5) is the plan, and the design doc feeds `proposal.md`/`design.md`.

3. **Explore the repo.** Use subagents (Explore agent type) to understand current state relevant to this change. Investigate:
   - Existing Argo manifests (`sleap-roots-pipeline.yaml`, `*-template.yaml`) and the `local-WSL2-*` variants
   - The run scripts (`runai_run_pipeline.sh`; `local_run_pipeline_first_time.sh` is **broken for the current DAG** — see its header and #21)
   - The assertions that already cover the area: `scripts/check_manifests.py`, `scripts/check_docs.py`
   - Existing OpenSpec specs: `openspec list --specs`
   - Existing OpenSpec changes: `openspec list`
   - The bloom-integration roadmap (`docs/bloom-integration/roadmap.md`) for where this change sits

4. **Decide OpenSpec scope.** Based on brainstorming + exploration, decide:
   - Is this a **new capability** (new spec) or a **modification to an existing capability** (delta on existing spec)?
   - What are the affected capabilities? (Each affected capability gets its own delta.)
   - Pick a unique, kebab-case, verb-led `change-id` (e.g., `add-scan-event-trigger`, `update-predict-template`).

5. **Create the OpenSpec proposal.** Invoke `/openspec:proposal` with the change-id and grounding context from steps 2–3. The proposal scaffolds:
   - `openspec/changes/<change-id>/proposal.md` — what and why
   - `openspec/changes/<change-id>/tasks.md` — ordered, verifiable work items. **Tasks MUST explicitly outline a TDD approach** (the `tasks.md` conventions in `openspec/project.md` override the generic "Write tests" last example in `openspec/AGENTS.md`):
     - For each behavior, the task that writes the failing assertion (in `check_manifests.py` or `check_docs.py`) comes *before* the task that edits the manifest/doc, and quotes the FAIL line it expects. One task never does both.
     - For live-cluster behavior, the first task records the **red baseline** (live pod spec, `kubectl describe` events, or a pod log showing the bug) — or, if none is observable yet, says why and names the observation that will go red → green. The acceptance tasks follow `/tdd`'s live-acceptance rule: an optional pre-merge probe with the template inlined, then register from `main` after merge and re-run the same observation.
   - `openspec/changes/<change-id>/design.md` — only if the change spans multiple manifests/systems, introduces a new pattern, or has trade-offs worth documenting
   - `openspec/changes/<change-id>/specs/<capability>/spec.md` — one folder per affected capability, using `## ADDED|MODIFIED|REMOVED Requirements` with at least one `#### Scenario:` per requirement

6. **Validate strictly.** Run `openspec validate <change-id> --strict` and fix every issue.

7. **Review the proposal.** Run `/review-openspec <change-id>`. If the verdict is **BLOCKED**, fix the issues raised (proposal, tasks, deltas), re-validate, and re-run the review. Repeat until the verdict is not BLOCKED. On NEEDS REVISION, turn each IMPORTANT finding into a task (or a stated decision not to) before step 8. Take reviewer-named mechanisms literally — don't swap in a convenient approximation.

8. **Get user approval.** Present the validated, reviewed proposal to the user and wait for explicit approval before proceeding to implementation. Surface:
   - The change-id and one-line summary
   - The list of affected capabilities and their delta types (ADDED / MODIFIED / REMOVED)
   - The review verdict and any IMPORTANT findings carried as tasks
   - Any open questions or trade-offs from `design.md`

9. **Implement with `/openspec:apply` and TDD.** Once approved, invoke `/openspec:apply <change-id>`; **`tasks.md` is the plan**, so do not also invoke `superpowers:writing-plans`. Implement directly, or for a large change dispatch `tasks.md` sections to subagents with `superpowers:subagent-driven-development`. For each task, follow `/tdd`:
   - Write the failing assertion first and run `/test` — confirm it is red for the right reason
   - Make the minimum manifest/script/doc change to turn it green
   - Run `/lint` if a manifest changed; check the `local-WSL2-*.yaml` variant for mount/path parity (not GPU/scheduling — see `/tdd`)
   - Commit the assertion and the change together, with the red FAIL line in the commit body — never commit a red suite
   - Tick the task (`- [x]`) in `tasks.md` as its commit lands (this overrides `/openspec:apply`'s "tick after all work is done")

   **Tiny-change path** (no OpenSpec): steps 1–2, then show the user the intended diff and get an OK, then `/tdd` directly (assertion red → edit → green → commit), then steps 10–11.

10. **Pre-merge sweep.** Before opening a PR, run `/pre-merge` (`/test` + `/lint` + `openspec validate --strict` + docs).

11. **Open a PR.** Use `/pr-description` for the template. Reference the OpenSpec change-id in the description.

12. **After merge: register, accept, clean up** on `main`. If templates changed, register them from `main` and run the post-merge acceptance steps in `/tdd` (drift check before/after, same observation re-run green). Then `/cleanup-merged`; verify all `tasks.md` items are `- [x]` first.

## Reference

- **superpowers skills**: invoke via the `Skill` tool; `using-superpowers` describes the meta-process
- **Project context**: `CLAUDE.md` + `openspec/project.md` at repo root
- **OpenSpec rules**: `openspec/AGENTS.md` (canonical) and `openspec/project.md` (this project's stack and conventions)
- **OpenSpec sub-commands**: `/openspec:proposal`, `/openspec:apply`, `/openspec:archive`

## Related Commands

- `/openspec:proposal` — scaffold the OpenSpec proposal (step 5)
- `/review-openspec` — adversarial review of the proposal (step 7)
- `/openspec:apply` — implement the approved proposal (step 9)
- `/openspec:archive` — archive after merge (called from `/cleanup-merged`)
- `/tdd` — the red → green loop over the check scripts (step 9)
- `/test` — run the assertion suites
- `/lint` — lint the manifests
- `/pre-merge` — final gate before opening a PR (step 10)
- `/pr-description` — generate the PR body
- `/cleanup-merged` — post-merge cleanup
