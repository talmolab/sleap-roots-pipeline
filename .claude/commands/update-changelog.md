---
description: Maintain CHANGELOG.md following Keep a Changelog format with SemVer
---

# Update Changelog

Maintain CHANGELOG.md following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

> This repo has no package manifest (no `package.json`/`pyproject.toml`), so versions are
> tracked by **git tags** only. There is no `CHANGELOG.md` yet — create one from the template
> below the first time this command runs.

## Quick Commands

```bash
# View recent commits
git log --oneline --decorate -10

# Find the last version tag (empty if none yet)
git tag -l | sort -V | tail -1

# View commits since last tag
git log $(git describe --tags --abbrev=0 2>/dev/null || echo "")..HEAD --oneline
```

## Changelog Format

CHANGELOG.md follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) principles:

- **Guiding Principle**: Changelogs are for humans, not machines
- **Latest First**: Most recent version at the top
- **One Version Per Release**: Each release gets a section
- **Same Date Format**: YYYY-MM-DD
- **Semantic Versioning**: Version numbers follow [SemVer](https://semver.org/)

### Change Categories

- **Added**: New capabilities (new WorkflowTemplate, new pipeline stage, new trigger)
- **Changed**: Changes to existing orchestration (template wiring, resources, mounts)
- **Deprecated**: Soon-to-be-removed manifests/paths
- **Removed**: Removed templates/manifests
- **Fixed**: Bug fixes (scheduling, volume, image-pin issues)
- **Security**: Secret-handling / RBAC fixes

## Changelog Template

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New capability description

### Changed

- Change description

### Fixed

- Bug fix description

[Unreleased]: https://github.com/talmolab/sleap-roots-pipeline/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/talmolab/sleap-roots-pipeline/releases/tag/v0.1.0
```

## Workflow: Adding Changes

### Step 1: Identify Changes Since Last Release

```bash
git log <last-tag>..HEAD --pretty=format:"%h %s" --reverse
```

(If there are no tags yet, review all commits and seed the first `[Unreleased]` section.)

### Step 2: Categorize Each Change

Group commits by category (Added / Changed / Fixed / Security / Removed / Deprecated).

Skip: pure CI config, doc-only churn, internal refactors that don't change behavior.

### Step 3: Update `[Unreleased]`

```markdown
## [Unreleased]

### Added

- Per-scan Argo Events trigger for Bloom scan ingestion (#NN)

### Fixed

- Predictor pod stuck Pending when gpu-fraction exceeded quota (#NN)
```

### Step 4: When Releasing a Version

Move `[Unreleased]` to a versioned section and update the link footer:

```markdown
## [Unreleased]

## [0.1.0] - YYYY-MM-DD

### Added

- Capability that was previously unreleased (#NN)
```

```markdown
[Unreleased]: https://github.com/talmolab/sleap-roots-pipeline/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/talmolab/sleap-roots-pipeline/releases/tag/v0.1.0
```

## Writing Good Changelog Entries

### Good

```markdown
### Added

- Warm predict worker template to avoid per-scan model reload (#47)

### Fixed

- hostPath mount mismatch between predictor output and trait-extractor input (#42)
```

### Bad

```markdown
### Added

- New stuff               ← too vague
- Fix bug                 ← wrong category; use Fixed
- Updated yaml            ← skip unless behavior changed
```

## Breaking Changes

Mark breaking changes clearly so operators can plan migrations:

```markdown
### Changed

- **BREAKING**: renamed `sleap-roots-predictor-template` → `predictor-template`.
  - Migration: re-run `argo template create` and update any `templateRef` names.
```

## Tips

1. **Update continuously** — add to `[Unreleased]` as PRs merge; do not batch at release time
2. **Link to issues/PRs** — include `(#42)` references for traceability
3. **Write for operators** — "Added per-scan trigger" not "Implemented sensor YAML"
4. **Note breaking changes** — mark with `**BREAKING:**` and include a migration path
5. **Skip internal-only changes** — CI config, doc churn

## Semantic Versioning Quick Reference

Given `MAJOR.MINOR.PATCH`:

- **MAJOR**: breaking changes (renamed templates, incompatible mounts) (`1.x.x → 2.0.0`)
- **MINOR**: new capabilities, backward-compatible (`1.1.x → 1.2.0`)
- **PATCH**: fixes, backward-compatible (`1.1.1 → 1.1.2`)

## Related Commands

- `/review-pr` — PR review includes a docs/changelog check
- `/docs-review` — broader documentation accuracy sweep
