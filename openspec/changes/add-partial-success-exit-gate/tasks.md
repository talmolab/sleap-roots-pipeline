# Tasks

Ships as **one PR**. `argo` is in the **Ubuntu WSL distro** at `/usr/local/bin/argo` (v3.6.5 CLI
against a v3.6.7 cluster), not on the Windows PATH — run it as
`wsl -e bash /mnt/c/<repo>/scripts/lint_manifests.sh`.

> **Status:** everything local is done and verified (19/36). What remains is the live-cluster
> work (§7), the cross-repo lockstep (§8), the roadmap record (§9), and the two `argo lint`
> steps (3.4, 10.1) — `argo` is not installed on this machine, so those are the PR's own
> checklist. Digests for 1.1/1.2 were verified against the GHCR registry API rather than via
> `docker buildx`; same evidence.

`argo` is not on the Windows PATH — run every `argo` command from WSL
(cluster Argo is **v3.6.7**, read off the `argoexec` image tag on live Argo pods).

Tasks 1–4 and 6 are local and need no cluster and no secrets, except the GHCR digest checks in
1.1/1.2 which need `gh auth`. Section 7 is live-cluster and is called out separately.

## 1. Image pins (do first — the wiring is inert without them)

- [x] 1.1 Bump `sleap-roots-images-downloader-template.yaml` and
  `sleap-roots-write-back-template.yaml` from `bloomctl:sha-3659705` to `sha-0614889`, recording in
  each file's comment that this build carries **both** bloom#830's partial-success exit code and
  bloom#774's per-scan status marking (#774 changed `cyl/ingest.py`, i.e. the write-back stage —
  which is why write-back needs the bump too, not just for consistency).
  **Validate:** `grep -c 'bloomctl:sha-0614889' sleap-roots-{images-downloader,write-back}-template.yaml`
  → `1` each; and the tag resolves to the expected digest:
  `gh auth token | docker login ghcr.io -u "$(gh api user -q .login)" --password-stdin && docker buildx imagetools inspect ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-0614889 --format '{{.Manifest.Digest}}'`
  → `sha256:e39b4746e68b4405d1d91899e358aee5a2badf1a9b8f103cd6971d28881a7cc5`.
  Tags here are **7 chars** (`sha-0614889` resolves, `sha-06148896` 404s) — never derive one from a
  local `git rev-parse --short`, which abbreviates differently than the CI runner.
- [x] 1.2 Bump `sleap-roots-predictor-template.yaml` to
  `sha-e025e309230de52cef0ccffa199048fe1dbd1b24` (predict#42's `run_manifest.json` forward-copy).
  **Validate:** `docker buildx imagetools inspect ghcr.io/talmolab/sleap-roots-predict:sha-e025e309230de52cef0ccffa199048fe1dbd1b24 --format '{{.Manifest.Digest}}'`
  → `sha256:4d4064c6ac8dadc1bedcba594c74f0d7c4b9d907ee9001999d34e664317a4060`. predict tags the
  **full 40-char** sha — do not pattern-match bloomctl's 7.
- [x] 1.3 Leave `sleap-roots-trait-extractor-template.yaml`'s `sha-689cffb` pin unchanged, and
  rewrite its stale `retryStrategy` comment: sleap-roots#259 is now resolved on both sides, and the
  claim that an empty `/in` exits `0` (a "silent-green node") is false since sleap-roots#266 —
  it exits `1` with no manifest, `3` with one. Record that the limits are deliberately unchanged
  and carry no `expression`.
  **Validate:** `git -C ../../../sleap-roots diff --stat 689cffb 094992d` shows OpenSpec docs only
  (no code, no `Dockerfile`, no dependency files), confirming the built image is unchanged; and
  `grep -c 'silent-green' sleap-roots-trait-extractor-template.yaml` → `0`.

## 2. The exit-gate template

- [x] 2.1 Add `sleap-roots-exit-gate-template.yaml` declaring **three separately-named**
  `inputs.parameters` (one per producer), reusing the already-pinned `bloomctl` image purely for
  its shell, and comparing each code against an explicit `0|3` allowlist.
  Must include, each of which is a spec requirement and none of which `argo lint` will catch:
  `command: ["/bin/sh","-c"]` (the image's `ENTRYPOINT` is `["bloomctl"]` with no `CMD`, so an
  args-only template would run `bloomctl <script>` and fail **every** workflow); an explicit
  `priorityClassName`; a `retryStrategy` with `retryPolicy: Always`; `resources.requests`; a
  `project` label; **no** `volumeMounts`; **no** `HOME`; **no** `serviceAccountName`.
  Pass the codes via `env` rather than interpolating them into the script body, so a substituted
  value cannot break out of the shell.
  **Validate:** the field assertions in task 6.1.
- [x] 2.2 Verify the gate's comparison logic by executing **the shipped artifact**, not a retyped
  copy of it:
  ```bash
  IMG=$(yq -r '.spec.templates[0].container.image' sleap-roots-exit-gate-template.yaml)
  SCRIPT=$(yq -r '.spec.templates[0].container.args[0]' sleap-roots-exit-gate-template.yaml)
  run() { docker run --rm --entrypoint /bin/sh \
    -e CODE_IMAGES_DOWNLOADER="$1" -e CODE_PREDICTOR="$2" -e CODE_TRAIT_EXTRACTOR="$3" \
    "$IMG" -c "$SCRIPT" >/dev/null 2>&1; echo "[$1|$2|$3] -> $?"; }
  ```
  **Validate:** expect exit `0` for `(0,0,0)`, `(0,3,0)`, `(3,3,3)`; and non-zero for `(0,1,0)`,
  `(0,2,0)`, `(0,143,0)`, `(0,"",0)` (empty), `(0,"{{tasks.predictor.exitCode}}",0)` (the literal
  unsubstituted placeholder — the realistic corruption, see 2.3), and `(0,-1,0)`.
  Decide and record the `(0,03,0)` case — it forces the string-vs-numeric question explicit.
- [x] 2.3 Record in the template's header comment **why** the allowlist must stay an allowlist:
  at v3.6.7, `workflow/controller/dag.go` substitutes task arguments with
  `template.Replace(..., allowUnresolved=true)` and contains no requeue path, so an unresolvable
  `{{tasks.<name>.exitCode}}` arrives as a **literal string** rather than failing or hanging. A
  denylist (`fail if in {1,2,143}`) would pass it silently.
  **Validate:** `grep -q 'allowUnresolved' sleap-roots-exit-gate-template.yaml`.

## 3. DAG wiring

- [x] 3.1 Add `continueOn: {failed: true}` to `images-downloader`, `predictor` and
  `trait-extractor` in `sleap-roots-pipeline.yaml`. Not to `write-back`. Not `error: true`.
- [x] 3.2 Add the `exit-gate` task depending on `write-back`, passing three named
  `arguments.parameters` carrying `{{tasks.<producer>.exitCode}}`.
  **3.1, 3.2 and 3.3 must land in one commit.** 3.1 alone is `continueOn` with no gate — the state
  the design doc calls "strictly worse than today", since it reports exhausted-retry crashes as
  `Succeeded`. Do not split them.
- [x] 3.3 Extend the file's header comments: that the gate is the DAG's only leaf and therefore
  determines the Workflow phase; that every producer the gate references must remain an *ancestor*
  of it; and that a broken reference arrives as a literal string rather than failing, so the gate's
  allowlist is what makes it visible. Also correct `serviceAccountName`'s comment: "four stage
  templates" → five.
  **Validate:** `grep -c 'four' sleap-roots-pipeline.yaml` → `0`.
- [x] 3.4 Lint the DAG together with every template it references — the **only** check that
  cross-resolves `templateRef`, i.e. the only one that proves 3.2 did not land without 2.1:
  ```bash
  bash scripts/lint_manifests.sh        # from WSL; see the header for why the wrapper exists
  ```
  ⚠️ **The bare command does not work on this repo's manifests**, and it is not the manifests' fault:
  `argo lint --offline` resolves a `templateRef` by *(namespace, name)*. `sleap-roots-pipeline.yaml`
  declares `namespace: runai-busch-lab`; the templates deliberately declare none (they are registered
  with an explicit `-n`). So the lookup searches `runai-busch-lab` while the supplied templates sit in
  `""` and never matches — it fails identically on a perfectly valid tree. `scripts/lint_manifests.sh`
  lints a temp copy with the Workflow's namespace stripped so both sides agree.
  **Validate:** exits 0 with "no linting errors found!" — done, 6 manifests.
  **Negative control also run:** renaming the gate's `templateRef` to a nonexistent template makes it
  exit 1 with `couldn't find workflow template`, proving the check can actually fail.

## 4. Launcher

- [x] 4.1 Register `sleap-roots-exit-gate-template.yaml` in `runai_run_pipeline.sh`'s `TEMPLATES`,
  and update the four-line `argo template update` recipe in its header comment to five. Note in the
  comment that the script's `NAMESPACE` is `runai-talmo-lab` while the Workflow and this change's
  deployment target are `runai-busch-lab` — left as-is here (pre-existing, out of scope), but it
  means running the launcher unmodified registers templates into the *wrong* namespace.
  **Validate:** `bash -n runai_run_pipeline.sh`; the `TEMPLATES` array lists five files; and the
  header comment contains five `argo template update` lines.

## 5. Documentation this change falsifies

- [x] 5.1 `README.md`: the stage list (`:6-11`), the folder-structure block (`:69-77`), and the
  `argo template create` block (`:166-169`) all say four.
  **Validate:** every `*-template.yaml` the DAG references appears in all three blocks.
- [x] 5.2 `README.md` "DAG Behavior and Step Failures" (`:281-292`): it states *"If a task fails and
  `retryStrategy` is exhausted: the **entire workflow fails**"*, which becomes false for three of
  five tasks. Rewrite: a producer's failure no longer terminates the DAG, the terminal `exit-gate`
  re-derives the phase from the producers' real exit codes, and `{0,3}` pass while anything else
  fails the Workflow. Keep the existing non-resumability note.
  **Validate:** the section names `continueOn`, `exit-gate` and the `{0,3}` convention, and no
  longer claims an exhausted retry fails the whole workflow.
- [x] 5.3 `openspec/project.md`: `:6`, `:22`, `:71`, `:124` all say four; `:71` carries the literal
  architecture-pattern name `**Four-stage per-batch DAG**` that this change's delta renames.
  **Validate:** `grep -ni "four" openspec/project.md` returns nothing about the DAG.
- [x] 5.4 Correct the same stale empty-input claim where it appears beyond the template comment:
  `docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md:149` and
  `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md:202-208`. Both assert
  "empty input → exit 0 (silent-green)" for traits **and** that predict behaves identically; both
  halves were closed 2026-08-21 (sleap-roots#266 / predict#36). Note in place that the "resolve at
  wiring time" instruction is discharged by this change, and that the stages deliberately
  *disagree* on empty input — which is why the gate reads each producer's own code.
  **Validate:** `grep -rn "silent-green" docs/ --include=*.md` returns only archived text.
  (Archived OpenSpec changes are historical record and are deliberately **not** edited.)

## 6. Static verification (local, no cluster, no secrets)

- [x] 6.0 Commit those assertions as `scripts/check_manifests.py` so they are re-runnable by the
  next person. This repo has no CI, so an un-runnable prose checklist is the same as no check.
  **Validate:** `python scripts/check_manifests.py` exits 0 and reports every assertion.
- [x] 6.1 Assert every manifest-inspectable scenario in one pass (now automated by 6.0):
  ```bash
  P=sleap-roots-pipeline.yaml; G=sleap-roots-exit-gate-template.yaml
  yq '.spec.templates[0].dag.tasks | length' $P                                     # 5
  yq '[.spec.templates[0].dag.tasks[] | select(has("depends"))] | length' $P         # 0
  yq '[.spec.templates[0].dag.tasks[] | select(.continueOn.failed == true)] | length' $P   # 3
  yq '[.spec.templates[0].dag.tasks[] | select(.continueOn.error)] | length' $P      # 0
  yq '.spec.templates[0].dag.tasks[] | select(.name=="write-back") | has("continueOn")' $P # false
  yq '.spec.templates[0].dag.tasks[] | select(.name=="exit-gate") | has("when")' $P  # false
  yq '[.spec.arguments.parameters[] | select(.name=="scan-ids")] | length' $P        # 1
  yq '.spec.serviceAccountName' $P                                                   # bloom-workflow
  yq '[.spec.volumes[] | select(has("hostPath")) | .hostPath.type] | unique' $P      # ["Directory"]
  # exit-gate is the ONLY leaf (no other task depends on it, and nothing else is undepended-on)
  yq -r '[.spec.templates[0].dag.tasks[].name] - [.spec.templates[0].dag.tasks[].dependencies[]]' $P  # ["exit-gate"]
  grep -c 'retryPolicy: Always' sleap-roots-{images-downloader,predictor,trait-extractor}-template.yaml
  grep -L 'expression:' sleap-roots-{images-downloader,predictor,trait-extractor}-template.yaml  # all three
  # gate template fields argo lint will not check
  yq '.spec.templates[0].container | has("command")' $G                              # true
  yq '.spec.templates[0].container | has("volumeMounts")' $G                         # false
  yq '.spec.templates[0] | has("serviceAccountName")' $G                             # false
  yq '.spec.templates[0].priorityClassName' $G                                       # non-null
  yq '.spec.templates[0].retryStrategy.retryPolicy' $G                               # Always
  yq '.spec.templates[0].container.resources.requests' $G                            # non-null
  yq '.metadata.labels.project' $G                                                    # busch-lab
  yq '[.spec.templates[0].inputs.parameters[].name] | length' $G                     # 3
  ```
  **Validate:** every assertion above matches its expected value. (Fall back to `python -c` +
  PyYAML if `yq` is unavailable.)
- [x] 6.2 Confirm the gate's references are ancestors — the constraint that, if broken, silently
  passes a literal string:
  ```bash
  yq -r '.spec.templates[0].dag.tasks[] | select(.name=="exit-gate") | .arguments.parameters[].value' $P
  ```
  **Validate:** each named task is reachable from `exit-gate` by walking `dependencies` backwards.

## 7. Live verification (staging, `A4-PIPELINE-E2E-TEST`)

Announce before starting — this shares the 2-GPU `busch-lab` quota, the `A4-PIPELINE-E2E-TEST`
scans and the `a4_poc` NFS paths. **prod and staging share the `runai-busch-lab` namespace**, so
`argo template update` affects production dispatches too.

- [ ] 7.1 **Capture a rollback pre-image first, before mutating anything.** There is no drift check
  (#58), so do not assume the registered copies match `main`:
  ```bash
  argo list -n runai-busch-lab --status Running     # must be empty before proceeding
  mkdir -p /tmp/tmpl-backup
  for t in images-downloader predictor trait-extractor write-back; do
    argo template get "sleap-roots-$t-template" -n runai-busch-lab -o yaml \
      > "/tmp/tmpl-backup/$t.pre.yaml"; done
  ```
  **Validate:** four files captured; diff each against `main`'s copy and understand any difference
  before overwriting it — a divergence here is a live #58 instance.
- [ ] 7.2 Register the gate **first**, then update the other four. `argo template create` for the
  new one (`update` errors on a nonexistent template); `argo template update` for the rest.
  Registering the gate first is safe on its own — an unreferenced WorkflowTemplate is inert — and
  is a hard prerequisite for anything that dispatches the five-task DAG.
  **Validate:** `argo template get` each; compare against the local file ignoring server-injected
  metadata (`resourceVersion`, `uid`, `creationTimestamp`, `generation`, `managedFields`).
- [ ] 7.3 **Gate truth-table probe** — proves the gate's semantics directly, without producers, GPU
  or NFS, in ~2 minutes. Submit a throwaway Workflow that calls only the gate template, once per
  vector: `(0,0,0)`, `(0,3,0)`, `(3,3,3)`, `(0,1,0)`, `(0,2,0)`, `(0,143,0)`, `(0,,0)`, `(0,-1,0)`.
  **Validate:** `Succeeded` for the first three, `Failed` for the rest. This is the cheapest proof
  of the gate's logic *as deployed*, and it is independent of any other repo's behaviour.
- [ ] 7.4 **Poison-scan scenario** — re-run 2026-09-01's scenario 3: one scan whose `cyl_images`
  row points at never-uploaded object-storage content, plus two good scans, one batch.
  **Validate:** the DAG reaches `write-back`; both good scans' `.result.json` land on the NFS mount
  with fresh mtimes and appear in `cyl_trait_sources`; the poison scan's `cyl_pipeline_run_scans`
  row is `failed`; `done_count=2`, `failed_count=1`; Workflow `Succeeded`. Verify by artifact, not
  by workflow phase alone.
- [ ] 7.5 **Crash-injection scenario — the load-bearing test**, since silently greening real crashes
  is this design's failure mode. Submit with `scan-ids=not-an-int`, which `parse_scan_ids_flag`
  surfaces as a `ClickException` → **exit 1**.
  ⚠️ **Run this against a scratch input directory, not the default `a4_poc` paths.** Production
  dispatches the vendored copy of this Workflow with the same `hostPath`s, so the default paths are
  production's own working directory. A crash exit happens *before* `write_run_manifest`, leaving
  the previous run's manifest in place — so downstream stages would be scoped by another run's scan
  set and write-back would record per-scan outcomes under this workflow's name. Either point the
  volumes at a scratch path for this run, or clear `run_manifest.json` first.
  **Do not use an empty or comma-only value**: `[p.strip() for p in value.split(",") if p.strip()]`
  yields `[]`, which hits "No scan_ids given; nothing to stage" and exits **0** — the test would
  pass while proving the opposite of what it claims.
  **Validate:** images-downloader's `Retry` node shows `outputs.exitCode: 1`; the gate's resolved
  `inputs.parameters` contain `1` (**not** an empty string — direct confirmation that exit codes
  survive retry nodes here, alongside the `sleap-roots-pipeline-p8j6c` evidence); the gate is
  `Failed`; the Workflow is `Failed`.
  **Also assert the Bloom-side effects nobody has looked at**, since `continueOn` makes them newly
  reachable: no unexpected `cyl_trait_sources` rows, and record exactly which
  `cyl_pipeline_run_scans` rows moved and what `failed_count` became. A `Failed` Workflow does not
  mean nothing was written — capture what was.
- [ ] 7.6 **Characterise the zero-scan case — a measurement, not a confirmation.** Submit with
  `scan-ids=""`. The outcome is input-directory-state-dependent and is deliberately *not* asserted
  anywhere: on a fresh directory predict discovers nothing and exits `1` (gate rejects → `Failed`);
  on the shared directory it scopes to the leftover `run_manifest.json`, skips everything and exits
  `0` (gate accepts → `Succeeded`). Run it **both** ways — scratch dir and shared dir.
  **Validate:** record the actual phase for each, then update the spec, README and design doc to
  state what was measured. Until then no document may claim either outcome as fact.
- [ ] 7.7 **Idempotent re-delivery:** re-submit 7.4's exact batch.
  **Validate:** Workflow `Succeeded`, 0 GPU pods scheduled, every `.result.json` mtime unchanged —
  confirming `continueOn` did not disturb skip-if-done. This is the standing A4 batch-oracle signal.
- [ ] 7.8 Confirm an unrelated leftover scan's `result.json` mtime is unchanged by any run above
  (the standing leftover-contamination signal from #54/#55, which also discharges the predictor-pin
  re-run the roadmap lists as outstanding).

## 8. Cross-repo lockstep (after this PR merges)

- [ ] 8.1 Open the companion `salk-bloom` PR: copy the merged file **byte-exact**
  (`git show main:sleap-roots-pipeline.yaml > services/workflows/vendored/sleap-roots-pipeline.yaml`
  — do not retype or reformat; the drift check compares bytes and `.gitattributes` forces LF) and
  set `services/workflows/vendored/SLEAP_ROOTS_PIPELINE_REF` to this PR's **40-char** merge SHA
  (the check's `_SHA_RE` requires 40 chars; the current pin is `9df1e52daf…`).
  Also update `k8s_client.py`'s `build_workflow_body` docstring, which says "the four
  already-registered WorkflowTemplates".
  **Validate:** `python3 scripts/check_vendored_workflow_drift.py` **and** the full
  `services/workflows` pytest suite — the drift check compares bytes and will pass green while
  `test_build_workflow_body_dag_references_all_four_templates_in_order` is red.
- [ ] 8.2 **Hard ordering constraint**, one-directional: the `exit-gate` WorkflowTemplate must be
  registered in `runai-busch-lab` (task 7.2) **before** any vendored five-task DAG is deployed. If
  the vendored copy ships first, every batch dispatch fails at submit time with an unresolvable
  `templateRef` — and since prod and staging share the namespace, that is a simultaneous prod and
  staging dispatch outage, not silent drift. Merging the bloom PR to `staging` *is* the deploy
  (`deploy.yml` triggers on push), so there is no window to correct it afterwards.
  Rollback rule: reverting this repo is safe; **deleting the gate template is not**, while any
  deployed vendored copy still references it.
  **Validate:** the bloom PR description states the prerequisite and links task 7.2.

## 9. Record

- [ ] 9.1 Add a roadmap status-log entry **for the day section 7 actually ran**, not at merge, in
  this repo's established shape: real workflow names and dates for both the poison-scan and
  crash-injection runs; artifact evidence rather than phase (which `.result.json` files landed with
  fresh mtimes, which `cyl_trait_sources` rows appeared, the poison scan's row reading `failed`,
  `done_count=2`/`failed_count=1`); that the crash-injection run ended `Failed`; and that merging
  does **not** change cluster behaviour until `argo template update` runs, stating whether it has.
  State as plainly as the 2026-09-15 entry does: **a green Workflow, or a `complete` run, does not
  mean no scans failed.** If 7.5 was not run, say so — do not record 7.4 alone as "#56 fixed".
- [ ] 9.2 Close out the roadmap statements this change falsifies: the 2026-09-15 entry's "#56
  remains open and is the actual blocker"; "none of the **4** registered WorkflowTemplates" (now
  five — #58's scope grew); the "Genuinely remaining, not yet done" predictor-pin bullet (task 1.2)
  and its dedup re-run (task 7.8); the "Next (true frontier, as of 2026-08-31)" section's frontier
  item 1; and the A4 workflow-template row's stage chain.
  **Validate:** `grep -n "four\|#56 remains open\|4 registered" docs/bloom-integration/roadmap.md`
  returns only historical status-log text that was true when written.
- [ ] 9.3 Record the three deferred follow-ups **with their limitation stated, not just the issue
  number**: bloom#857 (run status reads `complete`, not `partial`), bloom#859 (a partial
  predict/traits still fails the Workflow at write-back), predict#44 (forwarded manifest must
  narrow to `ok ∪ skipped`). Also record that the local dry-run path
  (`local_run_pipeline_first_time.sh`, which submits the *cluster* manifest with its own
  four-template list) will hard-fail on the unregistered `templateRef` — knowingly out of scope
  here, tracked by #21.
- [ ] 9.4 Note that bloom's `staging` → `main` promotion is the production cutover for this DAG, and
  that the gate template must be registered before it.

## 10. Final sweep

- [x] 10.1 `bash scripts/lint_manifests.sh` (from WSL) — 6 manifests, no linting errors.
- [x] 10.2 `bash -n runai_run_pipeline.sh`
- [x] 10.3 `openspec validate add-partial-success-exit-gate --strict`
- [x] 10.4 `python scripts/check_manifests.py` against the final tree.
- [ ] 10.5 Open the PR with `/pr-description`, referencing this change-id, `Closes #56`, and
  linking #58 (this adds a fifth un-drift-checked object), bloom#857, bloom#859 and predict#44.
