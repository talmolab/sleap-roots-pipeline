---
description: Review and update project documentation for accuracy, completeness, and consistency
---

# Review & Update Documentation

Systematic workflow for reviewing and updating this repo's documentation to ensure it stays
accurate against the actual Argo/RunAI manifests and run scripts.

> This repo has no install/build/test commands (declarative YAML + shell). Documentation
> accuracy is checked against the **manifests, run scripts, and cluster commands** themselves
> (`argo lint`, `argo submit`, `kubectl`), not a build/test run. On Windows, prefer the
> Claude Code Grep/Glob tools over the POSIX `find`/`grep` snippets below.

## Quick Commands

```bash
# Find all documentation files
find . -name "*.md" -not -path "*/.git/*" | sort

# Search for TODO/FIXME/TBD in docs
grep -r "TODO\|FIXME\|TBD" --include="*.md" .

# Check for broken internal markdown links
grep -rh "\[.*\](.*\.md)" --include="*.md" . | grep -oP '\(.*?\.md\)' | sort -u

# View recently modified docs
find . -name "*.md" -mtime -7 | sort
```

## Documentation Review Checklist

### 1. Core Documentation Files

Check each of the following if it exists in the repo:

- [ ] **README.md** — project overview, cluster setup, Argo/RunAI configuration, run instructions
- [ ] **CLAUDE.md** — Claude-specific project instructions (OpenSpec managed block)
- [ ] **CHANGELOG.md** — release history, if present (see `/update-changelog`)
- [ ] **docs/bloom-integration/roadmap.md** — program scope / tier sequencing (canonical for scope)

### 2. OpenSpec Documentation

- [ ] **openspec/project.md** — purpose, stack (Argo/RunAI), conventions, constraints
- [ ] **openspec/changes/\*/proposal.md** — all active proposals
- [ ] **openspec/changes/\*/design.md** — implementation documentation

## Documentation Update Workflow

### Step 1: Identify What Changed

```bash
# Recent commits
git log --oneline -10

# What changed since the base branch
git diff main...HEAD --stat

# Find docs that mention a changed manifest, template name, or mount path
grep -r "sleap-roots-predictor-template\|hostPath\|runai-talmo-lab" --include="*.md" .
```

### Step 2: Update Affected Documentation

For each change, update the relevant docs:

1. **README.md** — if setup steps, cluster/Argo config, template names, or run commands changed
2. **openspec/project.md** — if stack, conventions, or constraints changed
3. **docs/bloom-integration/roadmap.md** — if a tier's status/scope advanced (tick the row)

### Step 3: Check for Accuracy

Verify documentation matches the current manifests and scripts:

- [ ] Documented `argo` / `kubectl` / `runai` commands still match the real flow
- [ ] `argo lint` passes on every manifest the docs reference
- [ ] WorkflowTemplate names in the README match the actual `*.yaml` `metadata.name`
- [ ] Mount paths / volume names in the docs match the manifests
- [ ] Image references are current and pinned
- [ ] Links work (no 404s)

### Step 4: Check for Completeness

Ensure documentation covers:

- [ ] Cluster access / RunAI login + `ARGO_TOKEN` setup
- [ ] How to create WorkflowTemplates and submit the workflow
- [ ] Local WSL2 testing path and its limitations (CPU-only)
- [ ] Volume-path configuration and the `hostPath type: Directory` pre-existence requirement
- [ ] Troubleshooting (`argo get`/`argo logs`/`kubectl describe`)

### Step 5: Verify Consistency

- [ ] Terminology uniform across files (scan / stage / template / workflow)
- [ ] Cluster vs. local-WSL2 instructions don't contradict each other
- [ ] Tone is consistent (technical, concise, helpful)

## Common Documentation Issues

### Issue 1: Outdated Setup / Run Instructions

**Symptom**: README references old template names, namespaces, or `argo`/`runai` commands.

**Fix**: re-trace the real flow (`runai login` → template create → `argo submit`), update the
step-by-step instructions, update prerequisites and namespace, add a troubleshooting note.

### Issue 2: Cluster ↔ Local Drift

**Symptom**: README documents one manifest set but the `local-WSL2-*` variants diverged.

**Fix**: reconcile the two; document which is canonical (cluster) and what differs locally.

### Issue 3: Dead Links

**Symptom**: links to moved/deleted files or stale external (Argo/RunAI/K8s) docs.

**Fix**: find broken links with grep; update or remove; use relative paths internally.

## Feature Documentation Template

```markdown
## Feature Name

Brief description of the orchestration change and why it exists.

### Setup

Prerequisites (cluster access, volumes, images) and setup steps.

### Usage

How to run it (`argo submit ...`) with an example.

### Configuration

Available parameters, annotations (`gpu-fraction`, `preemptible`), and env vars (`ARGO_TOKEN`).

### Troubleshooting

Common failures and how to diagnose them (`argo logs`, `kubectl describe`).
```

## What to Document

**Do document:** cluster/RunAI setup, run commands, volume configuration, parameters &
annotations, breaking changes (renamed templates, changed mounts) with migration notes,
troubleshooting.

**Do not document:** stage-internal logic (lives in the sibling service repos), temporary
workarounds (fix the manifest instead), self-evident YAML.

## Documentation Completeness Criteria

- [ ] A new operator can run the pipeline using only the docs (no undocumented steps)
- [ ] All documented commands work when copy-pasted
- [ ] Breaking changes are clearly noted with migration paths
- [ ] All links work
- [ ] No `TODO`/`TBD`/`FIXME` remain in docs

## Related Commands

- `/review-pr` — PR review includes a docs-accuracy lens
- `/update-changelog` — maintain the changelog
- `/openspec:proposal` — create formal specs for new capabilities
