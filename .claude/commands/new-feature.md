---
description: End-to-end workflow for scoping, proposing, and implementing a new orchestration change using superpowers brainstorming and OpenSpec.
---

You are starting a new feature workflow. The user's feature request is: $ARGUMENTS

This repo uses **two complementary planning systems** — they layer, they don't compete:

- **superpowers** (`brainstorming`, `writing-plans`, `subagent-driven-development`) — drive the conversational design, planning, and implementation discipline
- **OpenSpec** (`openspec/`, `openspec` CLI) — produces durable spec deltas for any change that adds capabilities, modifies orchestration behavior, or affects architecture

For non-trivial changes, use BOTH. For tiny changes (typo, comment, image-tag bump), skip OpenSpec but still brainstorm intent first.

> **Note on this repo:** `sleap-roots-pipeline` is a declarative **Argo/RunAI orchestration**
> repo — Argo `Workflow`/`WorkflowTemplate` YAML + shell launchers, no application code and no
> unit-test harness. "Implementation" here means editing manifests/scripts; "verification"
> means `argo lint`, a local WSL2 dry-run, and (where it applies) a real cluster submit — not
> a `pytest`/`build` step. See `openspec/project.md`.

## Guardrails

- Do NOT write any manifest/script changes until the OpenSpec proposal is approved by the user.
- Follow OpenSpec conventions strictly — see `openspec/AGENTS.md` for the authoritative rules.
- Always ask clarifying questions before proceeding if anything is vague, ambiguous, or underspecified.
- Keep changes within this repo's scope (orchestration). Stage-internal logic belongs in the
  sibling service repos (`sleap-roots-predict`, `sleap-roots`, `models-downloader`).

## Steps

1. **Ensure feature branch.** Check the current branch (`git branch --show-current`). If on `main`, ask the user what branch name to create — suggest a kebab-case, verb-led name based on the feature (e.g., `add-event-trigger`, `fix-gpu-fraction`). Create and switch to it before proceeding.

2. **Invoke `superpowers:brainstorming`.** This is mandatory in this workflow — even for changes that seem simple. The brainstorming skill explores user intent, requirements, and design through clarifying questions, then produces a design doc at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. Do not skip.

3. **Explore the repo.** Use subagents (Explore agent type) to understand current state relevant to this change. Investigate:
   - Existing Argo manifests (`sleap-roots-pipeline.yaml`, `*-template.yaml`) and the `local-WSL2-*` variants
   - The run scripts (`runai_run_pipeline.sh`, `local_run_pipeline_first_time.sh`)
   - Existing OpenSpec specs: `openspec spec list --long`
   - Existing OpenSpec changes: `openspec list`
   - The bloom-integration roadmap (`docs/bloom-integration/roadmap.md`) for where this change sits

4. **Decide OpenSpec scope.** Based on brainstorming + exploration, decide:
   - Is this a **new capability** (new spec) or a **modification to an existing capability** (delta on existing spec)?
   - What are the affected capabilities? (Each affected capability gets its own delta.)
   - Pick a unique, kebab-case, verb-led `change-id` (e.g., `add-scan-event-trigger`, `update-predict-template`).

5. **Create the OpenSpec proposal.** Invoke `/openspec:proposal` with the change-id and grounding context from steps 2–3. The proposal scaffolds:
   - `openspec/changes/<change-id>/proposal.md` — what and why
   - `openspec/changes/<change-id>/tasks.md` — ordered, verifiable work items, each with a concrete validation step (e.g. `argo lint`, dry-run, manifest field assertion)
   - `openspec/changes/<change-id>/design.md` — only if the change spans multiple manifests/systems, introduces a new pattern, or has trade-offs worth documenting
   - `openspec/changes/<change-id>/specs/<capability>/spec.md` — one folder per affected capability, using `## ADDED|MODIFIED|REMOVED Requirements` with at least one `#### Scenario:` per requirement

6. **Validate strictly.** Run `openspec validate <change-id> --strict` and fix every issue before sharing the proposal.

7. **Get user approval.** Present the validated proposal to the user and wait for explicit approval before proceeding to implementation. Surface:
   - The change-id and one-line summary
   - The list of affected capabilities and their delta types (ADDED / MODIFIED / REMOVED)
   - Any open questions or trade-offs from `design.md`

8. **Implement.** Once approved, invoke `superpowers:writing-plans` to create the implementation plan, then implement the manifest/script changes. For each task:
   - Make the change, then validate it — `argo lint <file>.yaml` for manifests; run a local WSL2 dry-run (`local_run_pipeline_first_time.sh`) where feasible
   - Keep cluster (`*.yaml`) and local (`local-WSL2-*.yaml`) variants in sync
   - Mark the task complete (`- [x]`) in `tasks.md`

9. **Pre-merge sweep.** Before opening a PR, validate every changed manifest (`argo lint`) and re-run `openspec validate <change-id> --strict`.

10. **Open a PR.** Use `/pr-description` for the template. Reference the OpenSpec change-id in the description.

11. **After merge: clean up** on `main`. See `/cleanup-merged`. Verify all `tasks.md` items are `- [x]` first.

## Reference

- **superpowers skills**: invoke via the `Skill` tool; `using-superpowers` describes the meta-process
- **Project context**: `CLAUDE.md` + `openspec/project.md` at repo root
- **OpenSpec rules**: `openspec/AGENTS.md` (canonical) and `openspec/project.md` (this project's stack and conventions)
- **OpenSpec sub-commands**: `/openspec:proposal`, `/openspec:apply`, `/openspec:archive`

## Related Commands

- `/openspec:proposal` — scaffold the OpenSpec proposal (step 5)
- `/openspec:apply` — implement an approved proposal (alternative to step 8)
- `/openspec:archive` — archive after merge (called from `/cleanup-merged`)
- `/review-openspec` — adversarial review of the proposal before approval
- `/pr-description` — generate the PR body
- `/cleanup-merged` — post-merge cleanup
