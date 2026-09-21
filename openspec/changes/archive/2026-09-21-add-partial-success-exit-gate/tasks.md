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
  of it; and that breaking that ancestry is rejected by Argo's own
  `validateDAGTaskArgumentDependency` at both `argo lint` and submission, while the gate's allowlist
  covers the narrower case the validator cannot see — a valid ancestor that produced no
  `outputs.exitCode`. Also correct `serviceAccountName`'s comment: "four stage templates" → five.
  **Corrected after 7.3's non-ancestor probe:** an earlier version of this instruction said a broken
  reference "arrives as a literal string rather than failing", which is false — see 7.3's result.
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
- [x] 6.2 Confirm the gate's references are ancestors — the earliest of the three layers enforcing
  it (Argo's validator rejects a non-ancestor at lint and submit; the gate's allowlist covers a
  valid ancestor with no `outputs.exitCode`):
  ```bash
  yq -r '.spec.templates[0].dag.tasks[] | select(.name=="exit-gate") | .arguments.parameters[].value' $P
  ```
  **Validate:** each named task is reachable from `exit-gate` by walking `dependencies` backwards.

## 7. Live verification (staging, `A4-PIPELINE-E2E-TEST`)

Announce before starting — this shares the 2-GPU `busch-lab` quota, the `A4-PIPELINE-E2E-TEST`
scans and the `a4_poc` NFS paths. **prod and staging share the `runai-busch-lab` namespace**, so
`argo template update` affects production dispatches too.

- [x] 7.1 **Rollback pre-image captured and the drift question answered, 2026-09-15.**
  Read-only comparison of the four registered templates in `runai-busch-lab` against `main`, using
  the new `scripts/check_cluster_drift.sh`: **all four IN SYNC**, live pins matching `main` exactly
  (`bloomctl:sha-3659705` ×2, `sleap-roots-predict:sha-f974632…`, `trait-extractor:sha-689cffb`).
  So there is **no live #58 instance right now**, and the rollback pre-image is simply `main` itself:
  to revert, `git checkout main -- sleap-roots-*-template.yaml` and `argo template update` each.
  That is more durable than a tarball, and it is only valid because the sync was verified — do not
  assume it again later, re-run the script.
  ⚠️ **Superseded as a rollback instruction; kept only as the 2026-09-15 record.** "`main` is the
  pre-image" held only while cluster and `main` were in sync. It stopped being true when #60 merged,
  and again when the cluster was bumped to `bloomctl:sha-28034f6` ahead of the repo (see 7.2). Use
  7.2's re-derivation procedure instead of any ref recorded here.
  The checker is semantic, not textual: the API server defaults `arguments: {}`/`inputs: {}`/
  `outputs: {}`/`metadata: {}`, injects `namespace`, and rewrites `cpu: '0.5'` to `cpu: 500m`, all of
  which make a naive diff report all four as drifted. Validated both ways — from `main` it reports
  IN SYNC; from this branch it reports exactly the five pending changes and nothing else.
  Note the script globs five template files, so it additionally reports `NOT REGISTERED` for
  `sleap-roots-exit-gate-template` until 7.2 runs — that is the expected output, not drift.
  **Hardened 2026-09-16 (PR #60 review):** the script previously printed `IN SYNC` for every
  template if its own normaliser failed (`set -uo pipefail` with no `-e` → two empty files →
  `diff -q` identical → exit 0). It now asserts both normalised files are non-empty first, so a
  broken check fails loudly instead of reporting success. Re-run it after 7.2's apply; the
  pre-hardening "IN SYNC" above was a true result but was not a trustworthy *mechanism*.
  Original instructions follow. **Capture a rollback pre-image first, before mutating anything.**
  ```bash
  argo list -n runai-busch-lab --status Running     # must be empty before proceeding
  mkdir -p /tmp/tmpl-backup
  for t in images-downloader predictor trait-extractor write-back; do
    argo template get "sleap-roots-$t-template" -n runai-busch-lab -o yaml \
      > "/tmp/tmpl-backup/$t.pre.yaml"; done
  ```
  **Validate:** four files captured; diff each against `main`'s copy and understand any difference
  before overwriting it — a divergence here is a live #58 instance.
- [x] 7.2 **APPLIED 2026-09-16** from a clean `main` checkout at `310aae6` (the squash-merge of
  PR #60), not from the branch — per #53's precedent. Gate `argo template create`d first, then
  `argo template update` on the other four. Pre-flight: `argo list --status Running` empty.
  **Result:** all five registered; `check_cluster_drift.sh` reports all five **IN SYNC**, exit 0.
  Live pins confirmed: `bloomctl:sha-0614889` ×3 (gate, images-downloader, write-back),
  `sleap-roots-predict:sha-e025e309…`, `trait-extractor:sha-689cffb`. The gate's `timeout: 600s`,
  `priorityClassName: interactive-preemptible` and `retryStrategy{limit:2,Always}` all survived
  registration. Non-offline `argo lint` (which resolves `templateRef` against the *cluster*) now
  passes on the five-task DAG — independent confirmation of registration.
  **Rollback pre-image corrected.** An earlier note here said the pre-image "is simply `main`
  itself". That became WRONG the moment #60 merged, since `main` now carries the new pins. The
  rollback target is **`3cf4b4f`** (the pre-merge commit), verified before applying: the live cluster was
  **semantically** equal to `3cf4b4f` on all four templates — equal under
  `check_cluster_drift.sh`'s normalisation, not byte-for-byte. The raw objects differ by
  API-server defaulting (`arguments: {}`, `inputs: {}`, `outputs: {}`, `metadata: {}`, `name: ""`)
  and the cpu rewrite `0.5` → `500m`, which is exactly what that script strips. Live copies also captured to files.
  To roll back: `argo template delete sleap-roots-exit-gate-template`, then
  `git checkout 3cf4b4f -- sleap-roots-*-template.yaml` and `argo template update` each.
  ⚠️ **RE-DERIVE THIS TARGET BEFORE USING IT — it is a snapshot of the pre-image as of this apply,
  not a standing instruction, and as of 2026-09-17 it is already stale.** `3cf4b4f` pins
  `bloomctl:sha-3659705`; the cluster now runs `sha-28034f6` (bumped live 2026-09-17, reconciled
  into the repo by #79). Running the line above verbatim today would downgrade bloomctl by **two**
  bumps and silently revert three separate fixes this change depends on: salk-bloom #871 (reopening
  srp#76 — re-delivery fails at blob upload), bloom#830 (`ctx.exit(0 if result.ok else 3)`, the
  partial-success code the whole gate reads) and bloom#774 (per-scan status marking). Note this is
  the *second* time this exact instruction has gone stale — 7.1 recorded the pre-image as "simply
  `main` itself" and that became wrong the moment #60 merged. Treat any recorded rollback ref here
  as evidence of what was live on the stated date only. Before rolling back: read the live pins
  (`kubectl get workflowtemplate <name> -n runai-busch-lab -o jsonpath='{.spec.templates[0].container.image}'`),
  find the commit that actually matches them, and roll back to that — not to a ref named in a note.
  **This apply exposed a real defect in the drift checker**, fixed in PR #73: `argo template
  create` stamps `workflows.argoproj.io/creator` into `metadata.LABELS` (not annotations, and only
  on `create` — `update` does not), which the checker did not strip, so the freshly created gate
  reported DRIFT against an identical file while the four updated ones read IN SYNC. PR #60's
  review predicted this failure but placed the key in annotations; running it settled where it
  actually lives. The all-five-IN-SYNC result above is from the fixed checker, and the fix was
  negative-controlled (from `3cf4b4f` it still reports real drift on all four).
  **Production effect, measured not assumed.** `salk-bloom` still pins the vendored **four**-task
  DAG (`SLEAP_ROOTS_PIPELINE_REF=9df1e52…`), so production does not run the gate yet — but its
  vendored DAG uses `templateRef`, so it picked up all three new pins immediately. Read-only NFS
  inspection beforehand established this is a net improvement, not a risk: `predictions/` and
  `traits/` had **no** `run_manifest.json` (predict did not forward it pre-#42), so write-back was
  discovering **unscoped** and re-ingesting 12 `result.json` files — 4 of them foreign leftovers —
  on every run. predict#42 narrows that to the manifest's 8. All 8 manifest keys had results, so
  bloom#859's latch was not armed.
- [x] 7.3 **Gate truth-table probe** — RUN 2026-09-15 in `runai-talmo-lab`. Scratch template name,
  no producers, no GPU, no volumes, no credentials; all objects deleted afterwards.
  **Correction to an earlier note here:** this was first recorded as safe "by construction" because
  the credentials could not reach `runai-busch-lab`. That overstated it. The *talmo-lab* kubeconfig
  genuinely cannot write to busch-lab — but this workstation does hold a busch-lab credential
  (`~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml`, in **WSL**, per the runai skill §1). The probe
  was safe because of which kubeconfig was loaded, not because production was unreachable. Anyone
  re-running it must check `kubectl config current-context` first.
  **Result — 7/7 vectors matched:** `(0,0,0)`, `(0,3,0)`, `(3,3,3)` → `Succeeded`; `(0,1,0)`,
  `(0,2,0)`, `(0,143,0)`, `(0,"",0)` → `Failed`. The partial-success row is the one #56 exists for,
  and it now holds on the real controller. Gate stderr confirmed the operator warning prints.
  **Non-ancestor case, tested separately and the result corrected the design:** a DAG whose gate
  references a non-ancestor task is *rejected by Argo* at both `argo lint` and submission
  (`missing dependency '<task>' for parameter '<name>'`) — it does **not** silently pass a literal
  through, as an earlier draft claimed. Docs updated accordingly.
  Original instructions follow. **Gate truth-table probe** — proves the gate's semantics directly, without producers, GPU
  or NFS, in ~2 minutes. Submit a throwaway Workflow that calls only the gate template, once per
  vector: `(0,0,0)`, `(0,3,0)`, `(3,3,3)`, `(0,1,0)`, `(0,2,0)`, `(0,143,0)`, `(0,,0)`, `(0,-1,0)`.
  **Validate:** `Succeeded` for the first three, `Failed` for the rest. This is the cheapest proof
  of the gate's logic *as deployed*, and it is independent of any other repo's behaviour.
- [x] 7.4 **DONE via the split — both halves now pass.** 7.4a passed 2026-09-16 (every filesystem criterion) and 7.4b passed 2026-09-21 (all six criteria, Bloom-dispatched, `done_count=2`/`failed_count=1`). Kept below as the record of why it had to be split.
  Original assessment: **BLOCKED as written (assessed 2026-09-16) — must be split. Two independent reasons.**
  1. **Its Bloom-side criteria are unreachable until §8 lands.** `done_count=2`/`failed_count=1`
     and the poison scan's `cyl_pipeline_run_scans` row require rows that Bloom's
     `POST /workflows/pipeline` route creates at *enumerate* time. A hand `argo submit` creates
     none, so those assertions have nothing to attach to. But dispatching *through* Bloom would run
     the vendored **four**-task DAG (`SLEAP_ROOTS_PIPELINE_REF=9df1e52…`, no gate, no
     `continueOn`) — i.e. it would exercise the old code and prove nothing about this change.
     So the Bloom half of 7.4 is only meaningful **after** §8 re-vendors and bumps the pin.
  2. ~~The poison scan's identity is not recorded anywhere in this repo.~~ **RESOLVED 2026-09-16 —
     the poison scan is `scan_id = 12894751`.** Identified empirically with `bloomctl`, no DB query
     needed, and controlled against a known-good scan with the identical invocation:

     ```
     bloomctl cyl download-for-predict 12894751 <tmp> -p pipeline-staging
       → Error: 1 of 1 frames failed to download ... no sidecar written        [POISON]
     bloomctl cyl download-for-predict 12894745 <tmp> -p pipeline-staging
       → Staged 1/1 frames -> .../scan_12894745 (sidecar: ...scan_metadata.json)   [GOOD]
     ```

     One `cyl_images` row whose object was never uploaded, and **no sidecar written** — so predict
     can never discover it, which is exactly why it is absent from the 8-key manifest while
     `…745`–`…750`/`…752`/`…753` are present.

     **7.4's batch, verified rather than inferred:** poison `12894751` + good `12894745`,
     `12894746`.

     **Why this had to be re-derived at all — worth not repeating.** The 2026-09-01 run that first
     demonstrated the poison-scan failure (`sleap-roots-pipeline-jqsf9`) recorded its *outcome* in
     the roadmap (`0/3`, `Failed`, two good scans stranded) and its *diagnosis* (#56), but never
     its **inputs**. The only machine-readable copy of the scan ids lived in the Workflow object's
     `spec.arguments.parameters`, and that object is now `NotFound`: it was dispatched through
     Bloom's automated path, which stamps a `ttlStrategy`, so it was garbage-collected — while the
     older hand-submitted runs (`l2247` 2026-08-13, `mtbv5`/`q62vv` 2026-08-10) survive precisely
     because they carry no TTL. **Record the scan ids of any diagnostic run in the repo, not only
     the conclusion; a TTL'd Workflow is not a record.**

  **Split it:**
  - **7.4a — RUN 2026-09-16 (`srp-t74a-poison-gfzp6`). Every **filesystem** artifact criterion PASSES; the
    Workflow-phase criterion and the `cyl_trait_sources` check are blocked, by a newly-found bug (#76), not by anything in #60.**

    | node | phase | exitCode |
    |---|---|---|
    | `images-downloader` (3 attempts) | Failed | **3** ← partial success in a real DAG, first time |
    | `predictor` | Succeeded | 0 |
    | `trait-extractor` | Succeeded | 0 |
    | `write-back` (3 attempts) | **Failed** | 1 |
    | `exit-gate` | **Omitted** | — ("omitted: depends condition not met") |
    | Workflow | **Failed** | — |

    **What passed is the substance of #56.** `images-downloader` exited **3** and **`continueOn`
    let the DAG advance past a `Failed` producer** — on 2026-09-01 this identical scenario ended
    `Failed` at 0/3 with both good scans stranded and never reaching the predictor; here the
    predictor ran and succeeded. Poison scan `scan_12894751` was isolated (no staged dir, no
    prediction, no result). Both good scans produced `.result.json` with fresh mtimes.
    `input/run_manifest.json` scoped correctly to `["scan_12894745","scan_12894746"]` with the
    poison excluded, stamped with **this** run's `pipeline_run_id` — unlike the zero-scan case,
    which leaves a stale one.
    The gate's **backward** path also worked exactly as designed: write-back carries no
    `continueOn`, so the gate was `Omitted`; `Omitted` is `Fulfilled` but not `Completed`, so it
    did not overwrite `branchPhase` and the Workflow correctly inherited `Failed`. Forward path
    (7.5, 7.6) and backward path are now both verified live.

    **Why write-back failed — #76.** predict's `.slp` output is not byte-reproducible: two runs of
    the same scan with identical inputs give the *same* `idempotency_key` (`86573f05b6b34dbf…`) but
    *different* `.slp` bytes (`8776CDD8…` vs `E8535461…`, identical file sizes). The blob address
    embeds the idempotency key, so a recompute writes different bytes to the same address and
    bloomctl refuses to overwrite. Worse, the strict blob upload happens *before* the RPC's
    `ON CONFLICT (idempotency_key) DO NOTHING` gate, which would have made the re-delivery a
    harmless no-op — `Ingested 0/2` confirms nothing reached the RPC.
    Diagnosed by reproducing outside Argo with bloomctl built at the deployed commit `06148896`.
    That was necessary because **`pods/log` is not granted** to the `argo-user` ServiceAccount
    (the Role grants `pods`, but Kubernetes treats subresources as separate resource strings), so
    the cause is invisible from the cluster side. Note `kubectl auth can-i get pods/log` answers
    "yes" misleadingly — it parses as a pod *named* `log`; use `--subresource=log`, which says no.

    **Ordering caveat, owned:** running 7.4a against a *fresh* scratch tree guaranteed a recompute
    of scans that 7.6's shared half had ingested under the same key an hour earlier. Had 7.4a run
    first it would have been the first writer and would likely have passed. The ordering surfaced
    the bug; it did not cause it.

    **To close 7.4a's Workflow-phase criterion:** either #76 lands, or re-run against scans whose
    idempotency keys have never been ingested.
  - **7.4b — RE-RUN 2026-09-21: PASSES, all six criteria. #56 is now verified end to end.**
    `POST /workflows/pipeline` as `bloom-pipeline-workflows` with
    `scan_ids=[12894760, 12894758, 12894759]` — the poison plus two good **new** synthetic scans
    (salk-bloom PR #884's `create-test-scan`), none with a prior envelope, so bloom#875 cannot
    confound the result this time. → `pipeline_run_id=10`, Argo `sleap-roots-pipeline-p6lz2`,
    19:30:52Z→19:34:40Z, `Succeeded`.

    | criterion | expected | observed |
    |---|---|---|
    | DAG reaches `write-back` | yes | **PASS** |
    | poison isolated at download | exit 3 | **PASS** — `FAILED scan_12894760: 1 of 1 frames failed to download`, exit `3` ×3 attempts; retries correctly re-skipped the two good scans (`Staged 0/3 (2 skipped) (1 failed)`) |
    | `continueOn` advances the DAG | yes | **PASS** — predictor/trait-extractor/write-back/exit-gate all exit `0` |
    | both good scans land | fresh `.result.json` | **PASS** — mtimes 19:33:58Z against a 19:30:52Z start, and each `predict_container_digest` equals its deployed template's pin |
    | poison's per-scan row | `failed` | **PASS** — `failed`, `source_id=None`, and it produced **no** staged input dir, **no** predictions dir and **no** envelope |
    | `done_count`/`failed_count` | `2`/`1` | **PASS — `2`/`1`**, with `12894758`→`written`/`source_id=145` and `12894759`→`written`/`source_id=146` |

    Verified by artifact, not by the API's own fields alone — the distinction this change exists to
    enforce, since a green Workflow proves nothing about per-scan outcomes.
    ⚠️ **Read `write-back`'s summary line with care.** It printed `Ingested 2/12 envelopes
    (10 failed)`. The **2** are this run's good scans. The **10** are srp#71 noise: the shared
    manifest unions and never prunes, so a 3-scan request carried 12 keys, and the 10 outside this
    run have no `cyl_pipeline_run_scans` row under `p6lz2` to mark. They cannot affect run 10's
    counts, which derive only from rows carrying this workflow name — which is exactly why the
    counts came out clean while the headline reads alarming.

    **Superseded record — the 2026-09-17 first attempt: four of six, the two counts FAIL.**

    **The invocation, recorded because the previous dispatches never were** (see the 2026-09-01
    note below — only outcomes were kept, so the call had to be reconstructed from scratch):
    `POST https://staging.bloom.salk.edu:8443/workflows/pipeline` as `bloom-pipeline-workflows`,
    body `{"target_level":"scan_ids","target_id":null,"scan_ids":[12894751,12894745,12894746]}`.
    → `pipeline_run_id=9`, Argo `sleap-roots-pipeline-fkfkz`, 20:27:02Z→20:30:09Z.
    Wrapped as `scripts/dispatch_bloom_run.sh`; two base-URL traps are documented in its header
    and cost real time to find:
    - **`:8443` is not optional.** Staging and production share `staging.bloom.salk.edu`; without
      the port you reach *production's* Caddy and the TLS handshake still succeeds against prod's
      wildcard cert, so you dispatch against prod believing it is staging.
    - **`/workflows` is NOT behind `/api`.** `/api` is self-hosted Supabase behind Kong (that is
      what `BLOOM_API_URL` in the credentials profile holds); `/api/workflows/pipeline` returns
      Kong's `{"message":"Unauthorized"}`, while `/workflows/pipeline` returns
      `{"detail":"Authorization Bearer token required"}` — `auth.py`'s own wording, which is how
      to tell the two apart. `api_url`/`anon_key` bootstrap from the PUBLIC
      `…:8443/api/client-info`, so only `BLOOM_EMAIL`/`BLOOM_PASSWORD` are secret.

    | criterion | expected | observed |
    |---|---|---|
    | DAG reaches `write-back` | yes | **PASS** |
    | poison isolated at download | exit 3 | **PASS** — `FAILED scan_12894751: 1 of 1 frames failed to download`, exit `3` on all three attempts |
    | `continueOn` advances the DAG | yes | **PASS** — predictor/trait-extractor/write-back/exit-gate all exit `0` |
    | Workflow phase | `Succeeded` | **PASS** |
    | poison's `cyl_pipeline_run_scans` row | `failed` | **PASS** |
    | `done_count`/`failed_count` | `2`/`1` | **FAIL — `0`/`3`** |

    **The failure is bloom#875, a gap salk-bloom #871 filed against itself.** Its
    `fix-cyl-redelivery-blob-collision/design.md` Risks section predicted every step before it had
    ever been observed: the no-op branch keys its `cyl_pipeline_run_scans` UPDATE on
    `(argo_workflow_name, source_id)`, a freshly dispatched row has `source_id IS NULL`, the UPDATE
    matches zero rows, the envelope is reported `failed` with `retriable=False`, the non-zero exit
    is therefore suppressed, and end-of-batch reconciliation closes the scan `failed` — so
    `failed_count` counts scans whose traits and blobs are complete. All three rows came back
    `source_id=None`; `source_id=83`/`84` (the good scans' real, correct envelopes) appear only in
    write-back's stderr. **This run is the first live reproduction**; recorded as a comment on
    bloom#875 rather than a new issue.
    ⚠️ **Worse than the design's phrasing implies.** It says `failed_count` counts *a* complete
    scan; live, **every** scan reads `failed` — including the genuinely-failed poison — so
    `failed_count=3` on `scan_count=3` is indistinguishable from "all three failed". That matters
    because the exit-gate this change added prints `Check cyl_pipeline_runs.failed_count` on every
    partial-success run: it points operators at the one field that is wrong on this path, so both
    signals a reader is told to trust disagree with the data.

    **Precondition, stated so the result is not over-read:** the two good scans had already been
    ingested earlier the same day by two hand-submitted re-delivery runs
    (`sleap-roots-pipeline-7wxm2`, `-bxpmt`), so this was a re-delivery at unchanged idempotency
    keys — exactly bloom#875's trigger. Running those first consumed the clean DB state a 2/1
    result needed. A clean re-test requires scan_ids with no prior envelope, i.e. **new** synthetic
    scans in `A4-PIPELINE-E2E-TEST` (`experiment_id 12880747`); all nine existing ones are either
    ingested or the poison. Reachable without that confound, though: any re-run of a completed
    batch under a fresh `pipeline_run_id` does it, which is ordinary retry behaviour.

    **Also confirmed live by this run**, both orthogonal to #56:
    - **#71's manifest leak, now on the real dispatch path.** Three scans requested; the manifest
      written under `run_id=sleap-roots-pipeline-fkfkz` holds **8** keys, and write-back delivered
      all eight — six outside the request.
    - **bloom#864.** `provenance.pipeline_run_id` is still `None` in both good scans'
      `result.json` after a Bloom-dispatched run, not merely after hand-submitted ones.
    ⚠️ Note for whoever runs it: `sleap-roots-pipeline.yaml` **hardcodes** the `a4_poc` NFS paths
    in `spec.volumes` (deliberately shared, so cluster-side skip-if-done works). Only `scan-ids` is
    a parameter. So a run cannot be pointed at a fresh output directory to force recomputation —
    making predict recompute requires choosing scan_ids with no existing predictions under
    `a4_poc/predictions`, which needs the DB to enumerate.
    ⚠️ **`cyl_trait_sources` is NOT in that category** (corrected in the pre-merge audit): those rows
    are written by **write-back** via `insert_cyl_result_envelope` on *any* dispatch path — this
    repo's roadmap records a hand-submitted run creating `source_id` 6/7/8 back on 2026-07-30. The
    reason 7.4a could not check it is simply that write-back Failed all three attempts (#76), not
    that it requires Bloom dispatch.

  Original instructions follow. Re-run 2026-09-01's scenario 3: one scan whose `cyl_images`
  row points at never-uploaded object-storage content, plus two good scans, one batch.
  **Validate:** the DAG reaches `write-back`; both good scans' `.result.json` land on the NFS mount
  with fresh mtimes and appear in `cyl_trait_sources`; the poison scan's `cyl_pipeline_run_scans`
  row is `failed`; `done_count=2`, `failed_count=1`; Workflow `Succeeded`. Verify by artifact, not
  by workflow phase alone.
- [x] 7.5 **RUN 2026-09-16 — PASSED, and it produced the strongest evidence in this change.**
  Workflow `srp-t75-crash-4qd66`, submitted with `scan-ids=not-an-int` against a **scratch** path
  tree (`a4_scratch_56/{input,predictions,traits}`, created empty), never the `a4_poc` paths.
  Terminal after **1908 s (31.8 min)** — `startedAt 2026-09-16T02:44:44Z` → `finishedAt 03:16:32Z`.

  | node | type | phase | `outputs.exitCode` |
  |---|---|---|---|
  | `images-downloader` (3 attempts) | Retry | Failed | **1** ("No more retries left") |
  | `predictor` (4 attempts) | Retry | Failed | **1** |
  | `trait-extractor` (3 attempts) | Retry | Failed | **1** |
  | **`write-back`** | Retry | **Succeeded** | **0** |
  | `exit-gate` (3 attempts) | Retry | Failed | 1 |
  | Workflow | — | **Failed** | — |

  Gate's resolved `inputs.parameters`: `images-downloader-code='1'`, `predictor-code='1'`,
  `trait-extractor-code='1'` — real values, **not** empty strings. That is direct live
  confirmation that `{{tasks.X.exitCode}}` resolves *through* Retry nodes on this controller,
  which until now was only verified in v3.6.7 source.

  ⚠️ **`write-back` SUCCEEDED while all three producers crashed — so this run is the empirical
  proof that the gate is load-bearing.** Without it, write-back would have been the DAG's only
  leaf, it exited 0, and `assessDAGPhase` would have reported the Workflow **`Succeeded`** for a
  run in which every producer crashed and zero scans were processed. The design doc's claim that a
  `continueOn`-only change is "strictly worse than today" is no longer an argument from Argo
  semantics — it is a measurement. The gate received `{1,1,1}`, rejected it, and failed the
  Workflow correctly.
  Why write-back exits 0 here: the scratch `traits/` dir is empty and no `run_manifest.json` was
  written (the crash precedes `write_run_manifest`), so `discover_envelopes` falls back to
  **unscoped** discovery, finds zero envelopes, and reports success. Worth recording rather than
  filing: this is exactly the path that makes a total crash greenable, and it is why the gate reads
  producer exit codes instead of trusting the terminal stage.

  **Isolation held.** All 12 production `a4_poc/traits/*.result.json` mtimes unchanged against the
  pre-run baseline, and `a4_poc/input/run_manifest.json` untouched (still 2026-09-10). The scratch
  tree was left **completely empty** with no `run_manifest.json` — independently confirming that a
  crash exit happens before `write_run_manifest`, which is the reason this test needed a scratch
  path at all.

  **Not verified:** the gate's stderr diagnostic. `pods/log` is Forbidden to the `argo-user`
  ServiceAccount in `runai-busch-lab`, so container logs are unreadable with these credentials and
  the operator-facing message could not be confirmed. Everything above is from node status, not
  logs.

  **Cost measured:** a crash-class run burns the full retry budget at every stage before the gate
  can reject — **31.8 min** wall clock and 4 GPU predictor pod schedules on input that cannot succeed.
  #60 fixed the DAG-killing consequence, not the retry storm; this is the number.

  **Bloom-side assertions NOT done** (see 7.4): a hand `argo submit` creates no
  `cyl_pipeline_runs`/`cyl_pipeline_run_scans` rows, so `failed_count` and per-scan status have
  nothing to attach to. Deferred to after §8.

  Original instructions follow. Submit with `scan-ids=not-an-int`, which `parse_scan_ids_flag`
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
- [x] 7.6 **MEASURED 2026-09-16, both ways. The prediction held exactly, and the outcome is
  directory-state-dependent as suspected — same submission, opposite verdict.**

  | run | paths | phase | gate params | duration |
  |---|---|---|---|---|
  | `srp-t76-zero-scratch-vdkr5` | scratch (the tree 7.5 left empty) | **`Failed`** | `{'0','1','1'}` | 1269 s |
  | `srp-t76-zero-shared-hrrkz` | real `a4_poc` | **`Succeeded`** 5/5 | `{'0','0','0'}` | 199 s |

  > ⚠️ **Durations corrected before merge.** Earlier drafts of this record read 7.5 as "1290 s
  > (21.5 min)" and 7.6-scratch as "1290 s". Both came from a background poller's
  > `TERMINAL after NNNNs` line, which reports the **poller's own** elapsed time (iterations x
  > sleep), not the Workflow's. For 7.5 the poller was started ~10 min after submission, so it
  > under-reported by that much. Always take durations from `status.startedAt` /
  > `status.finishedAt` on the Workflow object. Corrected values above are from those fields.

  **Fresh directory → `Failed`.** `images-downloader` **Succeeded, exit 0** (zero *requested*
  scans → "nothing to stage"), then `predictor` exit 1 and `trait-extractor` exit 1 (zero
  *discovered*), `write-back` **Succeeded exit 0**, gate rejected the mixed vector. So the stages
  genuinely disagree about what "empty" means — the downloader treats zero requested as success,
  predict and traits treat zero discovered as failure — and the gate converts that disagreement
  into a definite verdict instead of a silent green.
  This run is also the **second** independent demonstration that the gate is load-bearing:
  `write-back` Succeeded again, so without the gate this would have reported `Succeeded` too.
  And it exercises a vector 7.3 and 7.5 did not — a **mixed** `{0,1,1}` — proving the gate
  evaluates each producer independently rather than keying off the last or worst one.

  **Shared directory → `Succeeded`.** predict scoped to the leftover `run_manifest.json` (8 keys)
  rather than discovering nothing, recomputed all 8, traits followed, write-back **exited 0**,
  gate `{0,0,0}` passed. (Stated as exit 0, not "ingested": 7.5 in this same record is the
  demonstration that write-back exits 0 having ingested *zero* envelopes. Bloom-side ingestion for
  this run was not verified — no DB read, and pod logs are unreadable.) **A zero-scan submission therefore reports a fully green Workflow while
  doing substantial real work on someone else's scan set** — which is #37/#71, measured.

  **Docs to update from this (7.6's own follow-through):** README currently says the zero-scan
  outcome is "not yet characterised — do not rely on it either way". It is now characterised: both
  outcomes above, with the mechanism. The spec and design doc carry the same hedge.

- [x] 7.8 **MEASURED 2026-09-16 via `srp-t76-zero-shared-hrrkz` (the first post-bump recompute).
  PASSES.** Against the pre-run baseline:

  | group | mtime changed | `idempotency_key` changed | `predict_code_sha` after |
  |---|---|---|---|
  | the **8 in-manifest** scans | **yes** | **yes** | `e025e309…` (the new pin) |
  | the **4 out-of-manifest** leftovers (`scan_1009`, `scan_289`, `scan_577`, `scan_6791737`) | **no** | **no** | `4a70e59978cf` (unchanged) |

  So every changed mtime has a changed key explained solely by `predict_code_sha`, and **nothing
  outside the manifest's `scan_keys` was touched**. No leftover contamination — the #54/#55 signal
  is clean, and manifest scoping demonstrably bounds the blast radius.

  ⚠️ **Correction to this section's own restatement rationale.** The note below claims 7.8's
  original criterion ("an unrelated leftover scan's `result.json` mtime is unchanged") was
  "guaranteed to be violated" by the pin bump. **That was wrong.** The leftovers sit *outside*
  predict's manifest scope, so they were never candidates for recomputation and the original
  criterion would have passed. What the pin bump genuinely invalidates is **7.7**'s "every
  `.result.json` mtime unchanged", which cannot hold on a first post-bump run. The restatement is
  still the better test — it asserts *which* keys changed and why — but its justification
  over-generalised from 7.7 to 7.8.

  **Bonus finding: predict#42's manifest forward-copy works, first time ever.**
  `predictions/run_manifest.json` and `traits/run_manifest.json` were **absent** before this run
  and are now present, so write-back is manifest-scoped for the first time rather than falling
  back to unscoped discovery over the whole shared directory.
  **But both forwarded copies carry `pipeline_run_id: sleap-roots-pipeline-hjg62`** — the *old*
  run's id, not `srp-t76-zero-shared-hrrkz`. A zero-scan run exits before `write_run_manifest`, so
  the id was never refreshed, and predict/traits copy it forward verbatim. The 8 results this run
  rewrote are therefore associated with a manifest naming a different run: #71/bloom#703, observed
  directly rather than reasoned about.
> ⚠️ **7.7/7.8 were restated 2026-09-16 (PR #60's review). Their previous pass criteria could not
> hold, and running them as written would have produced a result that proves nothing.**
>
> Both keyed on "`.result.json` mtimes unchanged". That is invalid **across a pin bump**. predict's
> skip-if-done compares an idempotency key (`_previous_identity_key`, predict #35 — *not* the
> existence check this change's docs wrongly claimed until now), and that key includes
> `predict_code_sha`, which is baked into the image as `SRP_PREDICT_CODE_SHA`. Traits feeds
> `manifest.predict_code_sha` into its own key via `trait_extractor/envelope.py`. This change bumps
> the predictor pin — so **every** accumulated scan's key changes in both stages at once, and the
> first post-bump run legitimately recomputes and rewrites all of them.
>
> So on the first run mtimes *will* move, for a correct reason, and the old criteria could not
> distinguish that from the leftover-contamination bug they exist to detect. The fix is to make the
> **second** post-bump run the idempotency oracle (by then `predict_code_sha` is stable), and to
> turn the first run into a measurement of *which* keys changed and why.

- [x] 7.7 **RUN 2026-09-16 (`srp-t77-redeliver-t82vr`) — PASSES as an idempotency measurement.**
  ⚠️ **It is NOT the A4 batch-oracle as originally specified, and an earlier version of this note
  overstated it** (caught in the pre-merge audit). 7.7 as written says "re-submit **7.4's exact
  batch**". What actually ran was a **second zero-scan submission** — live
  `spec.arguments.parameters` shows `scan-ids=` empty, identical in shape to
  `srp-t76-zero-shared-hrrkz`. So the skip path it exercised depends on predict falling back to the
  **leftover** `run_manifest.json`, which is the #37/#71 behaviour this very change documents as a
  defect — not on an explicit batch re-request through the normal path. Every artifact fact below is
  correct; the claim "the batch-oracle signal is now met" was not. A true batch-oracle run needs an
  explicit `--parameter scan-ids=…` re-request, and 7.4a's batch is the natural candidate once #76
  is fixed.
  Measured with `predict_code_sha` stable (7.6's shared half was the first post-bump recompute; this
  is the second delivery over the same scan set).
  Workflow **`Succeeded`** 5/5, gate `{0,0,0}`, 6m54s. Against the pre-run snapshot:

  | check | result |
  |---|---|
  | 12 `result.json` mtimes | **all frozen** |
  | 12 `provenance.idempotency_key`s | **all unchanged** |
  | 24 `.slp` blobs (SHA256) | **all byte-identical** |

  **The `.slp` blob check was added beyond the original criteria, and it turned out to be the
  load-bearing one** — it is what explains #76. predict *skipped*, so no new bytes were produced,
  so write-back's blob upload found identical checksums and succeeded. Contrast 7.4a, where predict
  *recomputed* at the same key and wrote different bytes to the same address, which collided. Same
  write-back code, same blob addresses, opposite outcomes, decided purely by skip-vs-recompute.
  **So re-delivery is idempotent on the skip path and broken on the recompute path** — the precise
  statement of #76, demonstrated by the pair of runs rather than argued.

  On "**0 GPU pods scheduled**": taken literally that criterion cannot hold, and should be reworded
  for future use. The `predictor` pod is a DAG task and is *always* scheduled; what the oracle
  means is that no GPU *inference* happens. Observed: `predictor` ran, exited 0, and performed no
  work (all 8 scans skipped on matching keys, all artifacts byte-frozen). Measure it as "no
  artifacts rewritten", not as "no pod scheduled".
  *(7.8's criteria and its measured result are recorded above, immediately after 7.6, because the
  run that satisfied it — `srp-t76-zero-shared-hrrkz` — was 7.6's shared half. The criteria were:
  every `result.json` whose mtime changed must have a changed `idempotency_key` whose only
  differing input is `predict_code_sha`, and no file outside the manifest's `scan_keys` may be
  touched at all. Both hold.)*

## 7b. Rebase onto PR #62 (merges FIRST — this PR rebases onto it)

Merge order was reversed: #62 (namespace drift) lands first. That is the safer direction for
OpenSpec — #62's `MODIFIED` applies while `Launcher registers all four templates` still exists, and
this change's `RENAMED` then finds its source name intact. The reverse would have orphaned #62's
delta.

- [x] 7b.1 **Fold #62's namespace rules into the renamed requirement.** A `RENAMED` delta carries the
  FULL replacement text, so a version of it written before #62 existed would silently delete #62's
  two namespace paragraphs at archive time — and `openspec validate --strict` cannot detect that,
  because renaming is a legal operation with no way to know content went missing. Done: the renamed
  `Launcher registers every workflow template` now carries the namespace-equality rule and the
  no-env-var-override rule, plus two scenarios (#62 is dropping its own).
- [x] 7b.2 **After #62 merges, diff its actual archived requirement text against what was folded in
  above.** The text used here came from the peer session's description, not from the merged file.
  **Validate:** every normative clause in #62's archived `Launcher registers…` requirement appears in
  this change's renamed version. Anything missing would be deleted by this archive.
  **DONE 2026-09-16.** Diffed clause-by-clause against the live archived text. Two clauses were
  absent from the replacement and would have been silently deleted: *"Targeting another project
  requires editing the manifest as well, and registering that project's templates and secrets
  first"*, and the negative assertion *"it references no models-downloader template"*. Both restored,
  plus the concrete `runai-busch-lab` value alongside the relational assertion. Verified with a
  whitespace-normalised clause check, since a naive substring match false-flags on line wrapping.
- [x] 7b.3 **Add the namespace assertions to `scripts/check_manifests.py`** — deferred deliberately:
  this branch still carries `NAMESPACE="runai-talmo-lab"` because the fix belongs to #62, so the
  assertion would fail until the rebase. After rebasing, assert (a) the launcher's `NAMESPACE` equals
  `sleap-roots-pipeline.yaml`'s `metadata.namespace`, and (b) it is a literal with no `${...}`
  expansion.
  **Validate:** `python scripts/check_manifests.py` passes with both new assertions.
  **DONE.** Four assertions added; 51 pass. Negative control confirmed: re-introducing
  `NAMESPACE="${NAMESPACE:-runai-busch-lab}"` makes the literal assertion fail, which is exactly the
  override #62's spec forbids.
- [x] 7b.4 **Re-apply README hunks over #62's sweep.** Three overlap (main lines 71-76, 167-174,
  285-291). #62 rewrites all 14 `runai-talmo-lab` references to `busch-lab`, so the five
  `argo template create` commands must name `runai-busch-lab` **directly** — drop the
  substitution blockquote added here, since the point of that sweep is that no copy-pasteable
  command names the wrong namespace.
  **Validate:** `grep -c "runai-talmo-lab" README.md` → 0.
  **DONE.** Both README conflicts resolved toward busch-lab; the five `argo template create`
  commands now name `runai-busch-lab` directly and the substitution blockquote is dropped, keeping
  only #56's ordering constraint. NOTE the stated criterion (`grep -c runai-talmo-lab` → 0) was
  wrong: two references remain and are #62's own, deliberately explaining that talmo-lab is still
  live but no longer this pipeline's target.
- [x] 7b.5 Confirm `runai_run_pipeline.sh` merged cleanly: #62 rewrote lines 26-38 (literal
  `NAMESPACE`, shared-namespace note) and deleted the ⚠️ mismatch comment added here; this change's
  `TEMPLATES` entry and five-line header recipe are a different hunk and should survive.
  **Validate:** `bash -n runai_run_pipeline.sh`; `TEMPLATES` lists five files; no ⚠️ mismatch comment
  remains; `NAMESPACE` is the literal `runai-busch-lab`.
  **DONE.** Resolved toward #62's rewrite (literal `NAMESPACE`, shared-namespace note); the ⚠️
  mismatch comment added here is gone, and the `TEMPLATES` entry plus the header recipe survived as
  a separate hunk, with the recipe now on busch-lab and `create` for the gate.
- [x] 7b.7 **After #67 merges, point its offline-lint paragraph at `scripts/lint_manifests.sh`.**
  #67 fixes the wrong "needs a cluster to resolve" explanation and carries the temp-copy recipe
  inline. It deliberately does *not* reference the script, because `scripts/` does not exist on
  `main` until this PR lands — documenting it earlier would repeat the very error being fixed. This
  PR introduces the script, so this PR is where the README should start pointing at it instead of
  restating the recipe.
  **Validate:** the README's offline-lint note names `scripts/lint_manifests.sh`, the inline recipe
  is not duplicated, and the file it names exists in the tree.
- [x] 7b.6 Re-run the full local gate after rebasing: `scripts/lint_manifests.sh`,
  `scripts/check_manifests.py`, `openspec validate --strict`.

## 8. Cross-repo lockstep (after this PR merges)

- [x] 8.1 **DONE — verified live 2026-09-17, not merely assumed.** `salk-bloom` `origin/staging`
  carries the vendored five-task DAG at
  `services/workflows/vendored/sleap-roots-pipeline.yaml` with **5 `templateRef`s**, and
  `SLEAP_ROOTS_PIPELINE_REF` = `310aae63c4db4cc1eb608a4d7801031f0061106d` (40 chars, this
  change's own merge SHA — no longer the `9df1e52daf…` the instruction below describes).
  Byte-equality checked both ways: the vendored copy is **identical** to
  `sleap-roots-pipeline.yaml` at the pinned `310aae6` *and* at `main` `9418941`. That second
  comparison is the load-bearing one — it says the vendored copy has not gone stale, because this
  file has not changed since #60 despite #74/#78/#79 landing on top of it. `salk-bloom`'s CI only
  ever diffs the vendored copy against the *pinned* commit, so it cannot tell you that; the
  check has to be made against upstream `main` by hand, as here.
  Original instructions: Open the companion `salk-bloom` PR: copy the merged file **byte-exact**
  (`git show main:sleap-roots-pipeline.yaml > services/workflows/vendored/sleap-roots-pipeline.yaml`
  — do not retype or reformat; the drift check compares bytes and `.gitattributes` forces LF) and
  set `services/workflows/vendored/SLEAP_ROOTS_PIPELINE_REF` to this PR's **40-char** merge SHA
  (the check's `_SHA_RE` requires 40 chars; the current pin is `9df1e52daf…`).
  Also update `k8s_client.py`'s `build_workflow_body` docstring, which says "the four
  already-registered WorkflowTemplates".
  **Validate:** `python3 scripts/check_vendored_workflow_drift.py` **and** the full
  `services/workflows` pytest suite — the drift check compares bytes and will pass green while
  `test_build_workflow_body_dag_references_all_four_templates_in_order` is red.
- [x] 8.2 **SATISFIED — the constraint held, verified 2026-09-17.** The `exit-gate`
  WorkflowTemplate is registered in `runai-busch-lab` and reads IN SYNC against `main`
  (`scripts/check_cluster_drift.sh`, all five templates), so the deployed vendored five-task DAG's
  `templateRef` resolves. Ordering was respected: the gate was registered under task 7.2
  (2026-09-16) *before* the vendored copy shipped. Note the rollback rule below is still live —
  deleting the gate template would break every dispatch on both staging and production while the
  vendored copy references it.
  Original instructions: **Hard ordering constraint**, one-directional: the `exit-gate` WorkflowTemplate must be
  registered in `runai-busch-lab` (task 7.2) **before** any vendored five-task DAG is deployed. If
  the vendored copy ships first, every batch dispatch fails at submit time with an unresolvable
  `templateRef` — and since prod and staging share the namespace, that is a simultaneous prod and
  staging dispatch outage, not silent drift. Merging the bloom PR to `staging` *is* the deploy
  (`deploy.yml` triggers on push), so there is no window to correct it afterwards.
  Rollback rule: reverting this repo is safe; **deleting the gate template is not**, while any
  deployed vendored copy still references it.
  **Validate:** the bloom PR description states the prerequisite and links task 7.2.

## 9. Record

- [x] 9.1 **DONE 2026-09-16.** Roadmap status-log entry added for the day §7 ran, newest-first, with real workflow names, artifact evidence rather than phase, the crash run's `Failed`, what was NOT verified (7.4b's Bloom-side counts), and the restatement that a green Workflow does not mean no scans failed.
  Original instructions: Add a roadmap status-log entry **for the day section 7 actually ran**, not at merge, in
  this repo's established shape: real workflow names and dates for both the poison-scan and
  crash-injection runs; artifact evidence rather than phase (which `.result.json` files landed with
  fresh mtimes, which `cyl_trait_sources` rows appeared, the poison scan's row reading `failed`,
  `done_count=2`/`failed_count=1`); that the crash-injection run ended `Failed`; and that merging
  does **not** change cluster behaviour until `argo template update` runs, stating whether it has.
  State as plainly as the 2026-09-15 entry does: **a green Workflow, or a `complete` run, does not
  mean no scans failed.** If 7.5 was not run, say so — do not record 7.4 alone as "#56 fixed".
- [x] 9.2 **DONE 2026-09-16.** Closed out: the 2026-09-15 entry's "#56 remains open and is the actual blocker" (superseded block added, pointing at #76 as the moved blocker); my own earlier "count is still 4 and still accurate" note, which went stale the moment the gate was registered; the "Genuinely remaining" predictor-pin bullet and its dedup re-run (both done, with the caveat that the mtime-frozen signal is only valid within a fixed `predict_code_sha`); frontier item 1's #772/#56 bullet; and the A4 row's stage chain (now names `exit-gate` as the fifth task and only leaf). Also annotated the A4 row's status cell, which claimed write-back/notify/trigger were still remaining. **Corrected after the pre-merge audit:** an earlier version of this note claimed the grep
  returned "only dated status-log text". That was false. `roadmap.md:303` is the A4 breakdown
  sub-table's row literally titled `| **workflow template** |` — undated normative content, and the
  very row this task names. Its stage chain omitted `exit-gate` and its status still read
  "Two new DAG tasks needed, neither added yet"; I had updated line 138 (the A4 EPIC row) instead
  and not noticed. Both now fixed. This is the #62 pattern again — fixed where I looked rather than
  where the instruction pointed. Lines 188/558 are also non-status-log hits but are harmless prose.
  Original instructions: Close out the roadmap statements this change falsifies: the 2026-09-15 entry's "#56
  remains open and is the actual blocker"; "none of the **4** registered WorkflowTemplates" (now
  five — #58's scope grew); the "Genuinely remaining, not yet done" predictor-pin bullet (task 1.2)
  and its dedup re-run (task 7.8); the "Next (true frontier, as of 2026-08-31)" section's frontier
  item 1; and the A4 workflow-template row's stage chain.
  **Validate:** `grep -n "four\|#56 remains open\|4 registered" docs/bloom-integration/roadmap.md`
  returns only historical status-log text that was true when written.
- [x] 9.3 **DONE 2026-09-16.** All three recorded with the limitation stated, not just the number (bloom#857 counts-not-status; bloom#859 as a **latch** over never-pruned shared dirs, with the note that it is not armed today; predict#44, plus the observation that predict#42's forward-copy started working today). The local dry-run breakage is recorded with its real failure order — namespace first, then all four templateRefs, not just `exit-gate`.
  Original instructions: Record the three deferred follow-ups **with their limitation stated, not just the issue
  number**: bloom#857 (run status reads `complete`, not `partial`), bloom#859 (a partial
  predict/traits still fails the Workflow at write-back), predict#44 (forwarded manifest must
  narrow to `ok ∪ skipped`). Also record that the local dry-run path
  (`local_run_pipeline_first_time.sh`, which submits the *cluster* manifest with its own
  four-template list) will hard-fail on the unregistered `templateRef` — knowingly out of scope
  here, tracked by #21.
- [x] 9.4 **DONE 2026-09-16.** Recorded that `staging` → `main` is the production cutover, that merging the vendoring PR to `staging` *is* the staging deploy, that the gate template had to be registered first and now is, and that the ordering is one-directional. Also recorded the non-obvious part: production already runs the three new pins (the vendored DAG resolves stages via `templateRef`) while still dispatching the four-task DAG.
  Original instructions: Note that bloom's `staging` → `main` promotion is the production cutover for this DAG, and
  that the gate template must be registered before it.

## 10. Final sweep

- [x] 10.1 `bash scripts/lint_manifests.sh` (from WSL) — 6 manifests, no linting errors.
- [x] 10.2 `bash -n runai_run_pipeline.sh`
- [x] 10.3 `openspec validate add-partial-success-exit-gate --strict`
- [x] 10.4 `python scripts/check_manifests.py` against the final tree.
- [x] 10.5 **DONE.** Opened as PR #60, merged 2026-09-16 as `310aae6` (`Closes #56`), with the follow-up records landing as #75 and the 2026-09-17/09-21 direct-to-`main` commits.
  Original instructions: Open the PR with `/pr-description`, referencing this change-id, `Closes #56`, and
  linking #58 (this adds a fifth un-drift-checked object), bloom#857, bloom#859 and predict#44.
