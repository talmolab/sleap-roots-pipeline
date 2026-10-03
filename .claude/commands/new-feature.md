---
description: End-to-end workflow for scoping, proposing, and implementing a new orchestration change using superpowers brainstorming, OpenSpec, and TDD.
---

You are starting a new feature workflow. The user's feature request is: $ARGUMENTS

This repo uses **two complementary planning systems** — they layer, they don't compete:

- **superpowers** (`brainstorming`, `subagent-driven-development`, `test-driven-development`) — drive the conversational design and implementation discipline
- **OpenSpec** (`openspec/`, `openspec` CLI) — produces durable spec deltas for any change that adds capabilities, modifies orchestration behavior, or affects architecture

For non-trivial changes, use BOTH. For tiny changes (typo, comment, image-tag bump), skip OpenSpec but still brainstorm intent first and still follow TDD.

> **Note on this repo:** `sleap-roots-pipeline` is a declarative **Argo/RunAI orchestration**
> repo — Argo `Workflow`/`WorkflowTemplate` YAML + shell launchers, no application code.
> "Implementation" means editing manifests/scripts/docs. The **test harness** is
> `scripts/check_manifests.py` (manifest conventions) + `scripts/check_docs.py` (doc claims),
> run together by `/test`; `/lint` runs `scripts/lint_manifests.sh` (Argo schema +
> `templateRef` resolution). Behavior only the live cluster can show (GPU allocation,
> scheduling, quota) is an **acceptance test** on a real `argo submit`. See `openspec/project.md`.

## Guardrails

- Do NOT write any manifest/script changes until the OpenSpec proposal is approved by the user.
- Follow OpenSpec conventions strictly — see `openspec/AGENTS.md` for the authoritative rules.
- **Use TDD.** Write the failing assertion first, run it, and see it fail *for the right
  reason* before editing any manifest or doc. A test written after the fix proves nothing.
- Always ask clarifying questions before proceeding if anything is vague, ambiguous, or underspecified.
- Keep changes within this repo's scope (orchestration). Stage-internal logic belongs in the
  sibling service repos (`sleap-roots-predict`, `sleap-roots`, `models-downloader`).

## Steps

1. **Ensure feature branch.** Check the current branch (`git branch --show-current`). If on `main`, ask the user what branch name to create — suggest a kebab-case, verb-led name based on the feature (e.g., `add-event-trigger`, `fix-gpu-fraction`). Create and switch to it before proceeding.

2. **Invoke `superpowers:brainstorming`.** This is mandatory in this workflow — even for changes that seem simple. The brainstorming skill explores user intent, requirements, and design through clarifying questions, then produces a design doc at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. Do not skip.

3. **Explore the repo.** Use subagents (Explore agent type) to understand current state relevant to this change. Investigate:
   - Existing Argo manifests (`sleap-roots-pipeline.yaml`, `*-template.yaml`) and the `local-WSL2-*` variants
   - The run scripts (`runai_run_pipeline.sh`; `local_run_pipeline_first_time.sh` is **broken for the current DAG** — see its header and #21)
   - The assertions that already cover the area: `scripts/check_manifests.py`, `scripts/check_docs.py`
   - Existing OpenSpec specs: `openspec spec list --long`
   - Existing OpenSpec changes: `openspec list`
   - The bloom-integration roadmap (`docs/bloom-integration/roadmap.md`) for where this change sits

4. **Decide OpenSpec scope.** Based on brainstorming + exploration, decide:
   - Is this a **new capability** (new spec) or a **modification to an existing capability** (delta on existing spec)?
   - What are the affected capabilities? (Each affected capability gets its own delta.)
   - Pick a unique, kebab-case, verb-led `change-id` (e.g., `add-scan-event-trigger`, `update-predict-template`).

5. **Create the OpenSpec proposal.** Invoke `/openspec:proposal` with the change-id and grounding context from steps 2–3. The proposal scaffolds:
   - `openspec/changes/<change-id>/proposal.md` — what and why
   - `openspec/changes/<change-id>/tasks.md` — ordered, verifiable work items. **Tasks MUST explicitly outline a TDD approach:** for each behavior, the task that writes the failing assertion (in `check_manifests.py` or `check_docs.py`) comes *before* the task that edits the manifest/doc, and names the red it expects. For live-cluster behavior, the first task records the **red baseline** (e.g. the live pod spec, `kubectl describe` events, or a pod log showing the bug) before the fix, and the acceptance task re-runs the same observation green.
   - `openspec/changes/<change-id>/design.md` — only if the change spans multiple manifests/systems, introduces a new pattern, or has trade-offs worth documenting
   - `openspec/changes/<change-id>/specs/<capability>/spec.md` — one folder per affected capability, using `## ADDED|MODIFIED|REMOVED Requirements` with at least one `#### Scenario:` per requirement

6. **Validate strictly.** Run `openspec validate <change-id> --strict` and fix every issue.

7. **Review the proposal.** Run `/review-openspec <change-id>`. If the verdict is **BLOCKED**, fix the issues raised (proposal, tasks, deltas), re-validate, and re-run the review. Repeat until the verdict is not BLOCKED. Take reviewer-named mechanisms literally — don't swap in a convenient approximation.

8. **Get user approval.** Present the validated, reviewed proposal to the user and wait for explicit approval before proceeding to implementation. Surface:
   - The change-id and one-line summary
   - The list of affected capabilities and their delta types (ADDED / MODIFIED / REMOVED)
   - The review verdict and any IMPORTANT findings carried as tasks
   - Any open questions or trade-offs from `design.md`

9. **Implement with `/openspec:apply` and TDD.** Once approved, invoke `/openspec:apply <change-id>`; **`tasks.md` is the plan**, so do not also invoke `superpowers:writing-plans`. Implement directly, or for a large change dispatch `tasks.md` sections to subagents with `superpowers:subagent-driven-development`. For each task, follow `/tdd`:
   - Write the failing assertion first and run `/test` — confirm it is red for the right reason
   - Make the minimum manifest/script/doc change to turn it green
   - Run `/lint` if a manifest changed; keep cluster (`*.yaml`) and local (`local-WSL2-*.yaml`) variants in sync
   - Mark the task complete (`- [x]`) in `tasks.md`
   - Commit — `/test` must be green after every commit

10. **Pre-merge sweep.** Before opening a PR, run `/pre-merge` (`check_all.sh` + `lint_manifests.sh` + `openspec validate --strict` + docs).

11. **Open a PR.** Use `/pr-description` for the template. Reference the OpenSpec change-id in the description.

12. **After merge: clean up** on `main`. See `/cleanup-merged`. Verify all `tasks.md` items are `- [x]` first.

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
