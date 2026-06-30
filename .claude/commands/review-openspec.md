---
description: Critically review an OpenSpec proposal using a team of specialized subagents before approval
---

# OpenSpec Proposal Review — Subagent Team

You are a senior engineer reviewing an OpenSpec proposal for `talmolab/sleap-roots-pipeline`.
You value clear specs, reproducibility, traceability, cluster safety, and documentation that
is clear, succinct, and DRY.

This command launches **5 specialized subagents in parallel** to critically review an OpenSpec
proposal. Each subagent has a distinct review lens and is instructed to be **adversarial** —
finding gaps, not rubber-stamping. After all subagents return, synthesize findings into a
unified review verdict.

> **This repo** is declarative Argo/RunAI orchestration YAML + shell launchers — no
> application code, no unit-test harness, no build step (see `openspec/project.md`).
> "Verification" means `argo lint`, `openspec validate --strict`, a local WSL2 dry-run, and
> (where relevant) a real cluster submit — adapt the testing/build lenses accordingly.

**Arguments:** `$ARGUMENTS` (the change-id to review; if omitted, `openspec list` to find
active proposals and ask the user which one to review)

## Step 1: Identify the Proposal

```bash
# List active proposals if no change-id given
openspec list

# Validate the change (always run first)
openspec validate $CHANGE_ID --strict
```

Read the proposal files:

- `openspec/changes/<id>/proposal.md`
- `openspec/changes/<id>/tasks.md`
- `openspec/changes/<id>/design.md` (if present)
- All delta spec files under `openspec/changes/<id>/specs/`

## Step 2: Gather Context

Before launching subagents, collect the context each agent will need:

1. Read the full proposal files (proposal.md, tasks.md, design.md, delta specs)
2. Read the **current** specs being modified (`openspec/specs/`)
3. Read `openspec/AGENTS.md` for OpenSpec conventions
4. Read `openspec/project.md` for project conventions (Argo/RunAI stack + constraints)
5. Note the affected manifests/scripts listed in the Impact section
6. Note any related GitHub issues / roadmap tier mentioned
7. Run `openspec validate $CHANGE_ID --strict` and capture the output

Embed the full proposal text, current spec text, validation output, and file lists into each
subagent prompt.

## Step 3: Launch Subagent Review Team

Launch ALL 5 subagents **in a single message** (parallel execution). Each subagent gets the
full proposal text embedded in its prompt. Each agent MUST read the actual files it needs —
do not rely on summaries.

---

### Subagent 1: Spec Quality & OpenSpec Best Practices

> You are reviewing an OpenSpec proposal for `talmolab/sleap-roots-pipeline`.
> Your role: **Spec Quality & OpenSpec Best Practices Reviewer**.
>
> IMPORTANT: Be critical. Find problems. Do NOT rubber-stamp.
>
> First, read `openspec/AGENTS.md` to understand the full OpenSpec format rules.
> Then read the proposal files and current specs being modified.
>
> **Format rules to check:**
>
> - Delta sections MUST use: `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`
> - Requirements use `### Requirement: Name` (3 hashtags)
> - Scenarios use `#### Scenario: Name` (4 hashtags)
> - Every requirement MUST have at least one scenario
> - Scenarios MUST use **WHEN**/**THEN** format with bold markers
> - MODIFIED requirements MUST include the FULL existing text (partial deltas lose detail at archive)
> - Requirements use SHALL/MUST for normative language
>
> **Proposal rules:**
>
> - `proposal.md` must have: ## Why, ## What Changes, ## Impact
> - ## Why should be 1-2 sentences explaining the problem/opportunity
> - ## Impact must list: affected specs AND affected manifests/scripts
> - BREAKING changes (renamed templates, changed mounts/params) must be marked with **BREAKING**
> - Change ID must be verb-led kebab-case
>
> **Tasks rules:**
>
> - Each task must have a concrete validation step (`argo lint`, dry-run, field assertion, `openspec validate`)
> - Tasks must be small, verifiable work items (suitable for atomic commits)
> - Each task must have a checkbox `- [ ]`
>
> **Check for:** vague/untestable scenarios; WHEN/THEN specificity; MODIFIED requirements that
> drop original text; requirements without scenarios; missing edge cases (failure paths,
> preemption, missing volume); whether Impact lists ALL affected manifests; appropriate
> change ID. Report `openspec validate {CHANGE_ID} --strict` output.
>
> **Proposal to review:** {PROPOSAL_MD}
> **Tasks:** {TASKS_MD}
> **Delta specs:** {DELTA_SPECS}
> **Current specs being modified:** {CURRENT_SPECS}
> **Validation output:** {VALIDATION_OUTPUT}
>
> Return: PASS/FAIL per check; specific issues with suggested rewrites; quality score (1–10).

---

### Subagent 2: Validation & Dry-run Strategy

> You are reviewing an OpenSpec proposal's verification strategy for `talmolab/sleap-roots-pipeline`.
> Your role: **Validation & Dry-run Strategy Reviewer**.
>
> IMPORTANT: Be critical. This repo has no unit tests — verification is operational. The plan
> must be concrete and runnable.
>
> Read the repo's manifests, run scripts, and `openspec/project.md` before drawing conclusions.
>
> **Review the tasks.md for:**
>
> 1. **Validation per task**: does each manifest-changing task pair with `argo lint`?
> 2. **Specificity**: is each validation concrete (a field assertion / a dry-run / a submit),
>    not vague like "verify it works"?
> 3. **Right tool per claim**: `argo lint` for manifest validity; `local_run_pipeline_first_time.sh`
>    (WSL2, CPU) for a local dry-run; a real `argo submit` for GPU/scheduling claims;
>    `openspec validate --strict` for the spec.
> 4. **Missing checks**: failure paths (preemption, missing `hostPath`, `ImagePullBackOff`),
>    cluster↔local parity, idempotency / re-delivery (if A4-adjacent).
> 5. **Feasibility**: can a reviewer run these without prod secrets? Is anything that needs the
>    live cluster clearly marked as such?
> 6. **Scenario-to-check mapping**: does each delta-spec scenario map to a validation in tasks.md?
> 7. **Final verification section**: does tasks.md end with `argo lint` on all changed
>    manifests + `openspec validate <id> --strict`?
>
> **Tasks to review:** {TASKS_MD}
> **Delta specs (scenarios to match):** {DELTA_SPECS}
> **Proposal summary:** {PROPOSAL_MD}
>
> Report: missing validations; scenarios without a check; ordering issues; suggested
> additional validation tasks.

---

### Subagent 3: Argo / RunAI Manifest Correctness

> You are reviewing an OpenSpec proposal for `talmolab/sleap-roots-pipeline`.
> Your role: **Argo / RunAI Manifest Correctness Reviewer**.
>
> IMPORTANT: Be critical. Read the ACTUAL manifests and scripts. Find real problems.
>
> Read the Argo `Workflow`/`WorkflowTemplate` YAML, the `local-WSL2-*` variants, and the run
> scripts before drawing conclusions.
>
> **Review the proposal for:**
>
> 1. **Manifest validity**: would `argo lint` pass on every manifest the change touches?
> 2. **Template wiring**: `templateRef` name/template, `entrypoint`, DAG `dependencies`,
>    parameter/artifact passing between stages.
> 3. **Scheduling & resources**: `gpu-fraction` / `preemptible` annotations; `nvidia.com/gpu`
>    on the predictor step only; `namespace` (`runai-talmo-lab`); `project` label / quota.
> 4. **Storage**: `hostPath type: Directory` pre-existence; PV/PVC; inter-stage mount-path
>    agreement; cluster ↔ local-WSL2 parity.
> 5. **Reproducibility**: image tags/digests pinned (no `:latest`); model versions.
> 6. **Migration risk**: can this break a running pipeline on `main` if partially applied?
>    Renamed templates / changed mounts need a migration note.
> 7. **Secret safety**: no `ARGO_TOKEN`/secret committed or echoed by scripts.
>
> Read the actual files; report incorrect assumptions, missing failure handling, scheduling
> hazards, parity/compat issues, and concrete suggested fixes.
>
> **Proposal to review:** {PROPOSAL_MD}
> **Tasks:** {TASKS_MD}

---

### Subagent 4: Documentation Quality (Clear, Succinct, DRY)

> You are reviewing an OpenSpec proposal for `talmolab/sleap-roots-pipeline`.
> Your role: **Documentation Quality Reviewer** — enforce clear, succinct, DRY documentation.
>
> IMPORTANT: Be critical. Read the ACTUAL documentation files. Find real inconsistencies.
>
> Read all docs that could be affected: README, CHANGELOG (if present),
> `docs/bloom-integration/roadmap.md`, `openspec/project.md`, and any command files in
> `.claude/commands/` that reference affected manifests.
>
> **Review for:**
>
> 1. **Completeness**: does the proposal identify ALL docs that need updating? (Template names,
>    namespaces, mount paths, and run commands often appear in several docs.)
> 2. **DRY violations**: where is the same info (a path, a template name, a tag) duplicated?
>    Should it be cross-referenced instead?
> 3. **Accuracy after changes**: will the change introduce NEW inconsistencies (README commands
>    that no longer match the manifests)?
> 4. **Succinctness**: any docs verbose or redundant after the change?
> 5. **Roadmap**: if this advances a tier, is `docs/bloom-integration/roadmap.md` updated?
>
> Report: docs the proposal missed; DRY violations; inaccuracies the change will introduce;
> concrete suggested rewrites.
>
> **Proposal to review:** {PROPOSAL_MD}
> **Tasks:** {TASKS_MD}

---

### Subagent 5: Git Workflow & Commit Strategy

> You are reviewing an OpenSpec proposal for `talmolab/sleap-roots-pipeline`.
> Your role: **Git Workflow & Commit Strategy Reviewer**.
>
> IMPORTANT: Be critical. Commits should be small, focused, and leave `main` runnable.
>
> Run `git log --oneline -20` to check the actual commit message style used in this repo.
>
> **Review the tasks.md for commit strategy:**
>
> 1. **Atomic commits**: can each task group be committed independently without leaving a
>    broken/un-lintable manifest on `main`?
> 2. **Commit ordering**: dependencies between manifest changes that constrain ordering?
> 3. **Safety**: will every intermediate commit `argo lint` clean? What's the safe ordering?
> 4. **Suggested commit plan**: a sequence of small commits with conventional messages, files
>    per commit, and dependencies noted.
> 5. **PR strategy**: single PR or multiple? Reviewable in size?
> 6. **Risk mitigation**: rollback plan if a manifest change breaks a run.
>
> **Tasks to review:** {TASKS_MD}
> **Proposal summary:** {PROPOSAL_MD}
>
> Report: tasks too large for one commit; ordering dependencies missed; breakage risks; a
> concrete commit plan; PR strategy recommendation.

---

## Step 4: Synthesize Review

After ALL subagents return:

1. **Deduplicate** overlapping findings.
2. **Prioritize**:
   - **BLOCKING** — must fix before approval (spec errors, manifest that fails `argo lint`,
     secret exposure, broken templateRef, missing validation)
   - **IMPORTANT** — should fix before implementation (unclear scenarios, doc gaps, parity)
   - **SUGGESTION** — nice to have
3. **Create a unified review** with this structure:

```markdown
# OpenSpec Review: {change-id}

## Verdict: APPROVED / NEEDS REVISION / BLOCKED

## Summary
[2-3 sentence overall assessment]

## Blocking Issues
[Must resolve before approval — or "None"]

## Important Issues
[Should resolve before implementation — or "None"]

## Suggestions
[Optional improvements]

## Proposed Commit Plan
1. `type: message` — [files affected, lint state after]
...

## Validation Plan
For each testable change: the `argo lint` / dry-run / submit / `openspec validate` step that proves it

## Risk Assessment
- Run-breakage risk: LOW/MEDIUM/HIGH — [explanation]
- Cluster/local drift risk: LOW/MEDIUM/HIGH — [explanation]
- Documentation drift risk: LOW/MEDIUM/HIGH — [explanation]

## Review Details by Agent
### 1. Spec Quality
### 2. Validation & Dry-run
### 3. Argo / RunAI Manifest Correctness
### 4. Documentation
### 5. Git Workflow
```

## Step 5: Present and Iterate

Present the synthesized review and ask:

1. Address blocking issues now (update proposal, tasks, and specs)?
2. Approve with important issues noted as additional tasks?
3. Revise the proposal first?

If revising, update `proposal.md`, `tasks.md`, and delta specs, then re-run
`openspec validate $CHANGE_ID --strict`.

## Related commands

- `/openspec:proposal` — create a new proposal
- `/openspec:apply` — implement an approved proposal
- `/review-pr` — review the implementation PR after the spec is approved
