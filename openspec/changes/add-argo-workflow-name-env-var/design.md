## Context

Issue #38 explicitly scopes out "deciding the copy-forward-vs-mount question definitively,"
leaving it to whoever implements the env var change. This document records that decision.

## Decision: copy-forward, not a new mount

`write-back`'s template mounts only `traits-output-dir` (as `/workspace/input`) and
`predictions-output-dir` — never `images-input-dir`, where `run_manifest.json` will live once
`bloomctl` (`salk-bloom` #653) starts writing it. Two options existed:

1. **Copy-forward** — matches the established pattern for the per-scan sidecar
   (`sleap-roots-predict`'s D1, [design doc](https://github.com/talmolab/sleap-roots-predict/blob/main/docs/superpowers/specs/2026-07-06-predict-container-cli-design.md)):
   `predictor` already mounts `images-input-dir` (to read staged images) and
   `predictions-output-dir` (to write results), and copies the sidecar it read forward into its
   output dir. `trait-extractor` only mounts `predictions-output-dir` + `traits-output-dir` and
   relies on that forwarded copy. `write-back` already mounts `traits-output-dir`, so once
   `trait-extractor` forwards `run_manifest.json` the same way it (would) forward the sidecar,
   `write-back` sees it with **no template change**.
2. **New mount** — add `images-input-dir` to `write-back`'s template now, even though nothing
   reads it there yet and no manifest exists yet.

Chosen: **(1) copy-forward**. It matches the existing precedent exactly (this pipeline already
solved "how does a downstream, non-adjacent stage see an upstream-only file" once, for the scan
sidecar, and copy-forward was that answer), keeps `write-back`'s mount set minimal, and avoids
carrying a mount whose only purpose is a file that isn't forwarded to it yet. Confirmed with the
user during this change's brainstorming (2026-08-12). This is a recorded recommendation for
whoever implements `predictor`'s and `trait-extractor`'s manifest-consuming code, not an
implementation delivered by this change — it can still be revisited there if it turns out wrong
in practice.

## Non-goals

- Implementing the copy-forward logic itself. That code lives in `sleap-roots-predict`
  (`predictor`) and `sleap-roots`/traits (`trait-extractor`), neither of which has started
  consuming `RunManifest` yet — tracked as unstarted items 3–4 on
  [#37](https://github.com/talmolab/sleap-roots-pipeline/issues/37)'s checklist. Until that
  lands, `write-back` has no manifest to read regardless of this decision.
- Any `bloomctl`/`salk-bloom` changes (`RunManifest` writing, locking) — tracked separately as
  [bloom #653](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/653).
- Adding the `images-input-dir` mount option to `write-back`'s template — considered above and
  explicitly rejected, not merely deferred.
- Fixing `write-back`'s unscoped-glob vulnerability (the identical issue `discover_scans` had) —
  a separate, still fully open gap; this change doesn't touch it.
