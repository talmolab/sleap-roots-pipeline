---
name: roadmap-status-dashboard
description: Use when asked to refresh, publish, or share the sleap-roots ↔ Bloom program's status dashboard for Elizabeth's subgroup — e.g. "update the roadmap artifact", "share the status page", "what's the state of the program for the meeting". Sweeps live state across all program repos before touching the page, since the roadmap doc drifts from reality between sessions faster than it gets corrected.
---

# Roadmap status dashboard

Refreshes the published subgroup-status Artifact for the sleap-roots ↔ Bloom A4 integration
program. This is **not** a template-fill exercise — the roadmap doc and the artifact both drift
from live GitHub/cluster state constantly (parallel sessions merge things, secrets go missing,
dates get mis-recorded), so every refresh re-verifies before republishing.

## When to use
- User asks to update/refresh/republish the roadmap status artifact.
- User is about to share program status with their subgroup and wants it current.
- **Not** for day-to-day roadmap.md edits after a single PR merges — that's the
  `roadmap-driven-pipeline` skill's "close the loop" step. This skill is for the **dashboard
  artifact** specifically, and does a full live-state sweep as part of refreshing it.

## Program repos (check all of these, not just this one)
| Repo | Local path | What lives here |
|---|---|---|
| `sleap-roots-pipeline` | `c:\repos\sleap-roots-pipeline` | Canonical roadmap (`docs/bloom-integration/roadmap.md`), Argo orchestration |
| `salk-bloom` | `c:\repos\salk-bloom` | Bloom backend, `bloomctl`, `services/workflows` |
| `sleap-roots-predict` | `c:\repos\sleap-roots-predict` | A3-predict producer |
| `sleap-roots` | `c:\repos\sleap-roots` | A3-traits producer (`trait_extractor/`) |
| `sleap-roots-contracts` | (check `gh release list`) | Shared cross-repo shapes |

Parallel sessions run in `.worktrees/<name>` inside each repo — `git worktree list` in each repo
shows what's currently active. **Never touch a worktree with uncommitted changes**; read-only
`git status`/`git log` checks are always safe.

## Steps

1. **Read the canonical roadmap** — `sleap-roots-pipeline/docs/bloom-integration/roadmap.md`. Note
   every item marked in-progress, every referenced issue/PR number, and the "Status log"'s most
   recent entries.
2. **Verify against live state, not the doc's own prose.** For every open item found in step 1:
   - `gh issue view <n> --repo <owner/repo> --json state,updatedAt`
   - `gh pr list --repo <owner/repo> --state open --json number,title,createdAt` (don't rely on
     `--search "<n> in:body"` alone — it's unreliable for short numbers; cross-check with
     `git worktree list` in the relevant local repo for sessions that haven't opened a PR yet)
   - `gh secret list --repo <owner/repo>` if the roadmap claims something is "deployable," not just
     "merged" — this program has been burned once by that exact gap (bloom #677 merged but
     undeployable, five missing secrets, found 2026-08-19).
   - On Windows Git Bash, any `git show <ref>:<path>` where `<path>` starts with a dot
     (`.github/...`) can silently mangle into a broken command — prefix with `MSYS_NO_PATHCONV=1`
     and use an explicit `C:/...`-style `-C` path if a check on a dotfile/dotdir returns
     suspiciously empty.
3. **Reconcile any drift found, directly in `roadmap.md`.** Small, targeted edits (not a rewrite):
   correct the status, add a dated `Status log` entry describing what was found and fixed. Commit
   and push to `main`. This mirrors the `roadmap-driven-pipeline` skill's roadmap-review-gate
   discipline — verify against live state before writing anything down as fact.
4. **Update the dashboard source.** Edit
   `sleap-roots-pipeline/docs/bloom-integration/dashboard/roadmap-status.html` (the persisted
   source — do **not** recreate it in a scratchpad, it won't survive to the next session):
   - Header sub-line and footer "Last swept" date → today.
   - Tier table (A0–B2) and A4-detail table → reflect corrected statuses from step 3.
   - "Right now" cards → one per genuinely in-flight task, noting PR number if one exists
     (`bloom #123 · PR #456 open`) or its current stage if not (`· scoping`, `· in progress`,
     `· just started`).
   - "Open & blocked" → live blockers vs. decisions-needed-from-Elizabeth, kept visually distinct
     (see the file's existing `.blocker` vs `.blocker.decision` classes).
   - Reuse the existing design tokens/type scale as-is (Spectral/IBM Plex Sans/IBM Plex Mono,
     the `--done`/`--progress`/`--blocked`/`--notstarted` pill palette) — this is a status board,
     not a redesign; consistency across refreshes matters more than novelty each time.
5. **Republish to the same URL** — pass `url:
   https://claude.ai/code/artifact/6f85b79d-d886-437f-88d0-6ca2fbbf3270` to the `Artifact` tool
   along with the updated file path, so it updates in place rather than creating a new page. Keep
   `favicon: 🌱` unchanged (only earns a new emoji on a hard topic pivot, per the artifact tool's
   own convention).
6. **Report back**: what changed since the last sweep, in 3–5 bullets — not a re-narration of the
   whole page.

## Common mistakes
- Trusting `roadmap.md`'s prose without a live `gh`/`git worktree` check — this program has
  repeatedly found "merged" claims that were true in code but false in deployment (bloom #677),
  and status-log entries mis-dated by other sessions (twice, both self-corrected the same way:
  verify the referenced PR/issue's actual timestamp).
- Editing the dashboard HTML in a scratchpad path — it must live in the repo
  (`docs/bloom-integration/dashboard/roadmap-status.html`) to survive across sessions.
- Publishing without `url:` — creates a duplicate artifact instead of updating the one the
  subgroup already has bookmarked.
- Redesigning the page each refresh instead of updating data in the existing structure.

## Cross-refs
`roadmap-driven-pipeline` skill (the per-tier "close the loop" discipline this reuses at the
program level); `artifact-design` skill (load before any structural/visual change to the
dashboard, not needed for a pure data refresh).
