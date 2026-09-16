# Tasks

## 1. Resolve and verify both digests against the registry

Registry truth is established here, by hand, because the checker is deliberately offline. Both
GHCR packages are public, so an anonymous token works and no credential is needed:

```bash
TOK=$(curl -s "https://ghcr.io/token?scope=repository:talmolab/<img>:pull&service=ghcr.io" \
  | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')
ACC="Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
curl -sI -H "Authorization: Bearer $TOK" -H "$ACC" \
  "https://ghcr.io/v2/talmolab/<img>/manifests/<tag-or-digest>" | grep -i docker-content-digest
```

- [x] 1.1 Resolve the **predictor** pin `sha-e025e309230de52cef0ccffa199048fe1dbd1b24`.
  **Validate:** the tag resolves to a digest; requesting the manifest *by that digest* returns
  HTTP 200 with a matching `Docker-Content-Digest`; and the image config's
  `org.opencontainers.image.revision` starts with `e025e309`. The value recorded in
  `openspec/changes/add-partial-success-exit-gate/tasks.md:35` is a **cross-check, not the source
  of truth** — if the two disagree, the registry wins and the discrepancy gets recorded.

- [x] 1.2 Resolve the **trait-extractor** pin `sha-689cffb`, same three criteria, with
  `org.opencontainers.image.revision` starting with `689cffb`. This digest is **not recorded
  anywhere in this repo** and must be looked up. Note predict tags the full 40-char sha while
  `bloomctl` tags 7 — do not pattern-match one pin from another.
  ⚠️ **Do not reuse `sha256:e39b4746…`**: that is `bloomctl`'s digest, and a comment on #70
  misattributes it to the trait-extractor.

- [x] 1.3 **Pull both literal references locally, before any manifest edit or cluster write** —
  `docker pull ghcr.io/talmolab/sleap-roots-predict:sha-e025e309…@sha256:<d1>` and the
  trait-extractor equivalent. This is the step that retires the `ImagePullBackOff` risk without
  exposing production to it.
  **Validate:** both pulls succeed. If Docker is unavailable, substitute an equivalent resolution of
  the **combined** `tag@digest` string (not the digest alone — resolving by digest does not prove
  the combined form parses).

## 2. Add the failing assertions first (TDD)

- [x] 2.1 In `scripts/check_manifests.py`, add a `DIGEST_ENV_BY_STAGE` mapping
  (`predictor` → `SRP_PREDICT_CONTAINER_DIGEST`, `trait-extractor` → `SRT_TRAITS_CONTAINER_DIGEST`
  — deliberately **not** named `PRODUCER_*`, since `PRODUCERS` in the same file means three stages)
  and a requirement block asserting, per stage: the `image:` reference matches
  `@sha256:[0-9a-f]{64}` (a substring test for `@sha256:` would admit `@sha256:zzz`); the env var is
  present exactly once; its value matches `^sha256:[0-9a-f]{64}$`; and its value equals the digest
  **parsed from that template's own `image:` line**. Plus one assertion that the trait-extractor
  declares no `SRP_PREDICT_CONTAINER_DIGEST`. Nine assertions total. No literal digest may appear
  in the checker.

  Two implementation constraints, both load-bearing:
  - **No `None`-sentinel comparison.** An unparseable `image:` must yield a value that can never
    equal an env value (e.g. a sentinel string), or `None == None` makes the equality assertion
    print `PASS` against today's unedited manifests — #60's defect reproduced inside the guard
    written to prevent it.
  - **Every assertion runs unconditionally.** The existing `ARGO_WORKFLOW_NAME` loop guards its
    second check behind `if entry:`; copying that shape would make the assertion count differ
    between the red and green states, and task 5.1 unevaluable.

  **Validate:** `python scripts/check_manifests.py` exits non-zero with **62 passing and 9 failing**,
  and the equality assertions appear among the `FAIL` lines rather than passing vacuously. Note the
  negative assertion (no `SRP_` in trait-extractor) passes both before and after — fail-first cannot
  cover it; task 2.3 mutation 6 is what proves it wired.

- [x] 2.2 Add assertions that each producer's `image:` repository path equals its expected
  `ghcr.io/talmolab/<repo>`, and that the two producer digests differ from each other and from every
  `bloomctl` digest in the repo. Without these, a cross-wired reference
  (`sleap-roots-predict:…@sha256:<the traits digest>`) passes every consistency check — and pasting
  bloomctl's digest onto a producer is the exact error already made in #70's comment thread.
  **Validate:** swapping the two producers' digests makes the check fail.

- [x] 2.3 **Mutation matrix** — run after task 3 is green, against a scratch copy of the two
  templates, reverting after each. This is what proves the new assertions *can* fail; fail-first
  alone does not, and the delta spec's central scenario ("a one-sided bump fails the check") is
  otherwise never observed. Each mutation must make `check_manifests.py` exit non-zero and name the
  offending stage:
  1. predictor `image:` digest altered by one hex character, env untouched;
  2. predictor env value altered by one hex character, `image:` untouched;
  3. and 4. the same two for the trait-extractor;
  5. predictor `image:` reverted to tag-only while its env var stays (the vacuous-equality case);
  6. predictor env value set to `""`;
  7. `SRP_PREDICT_CONTAINER_DIGEST` **added** to the trait-extractor (the only way that assertion is
     ever observed red);
  8. the two producers' digests swapped (covers 2.2).

  **Validate:** all eight mutations fail the checker; the tree is byte-identical to `HEAD`
  afterwards (`git status --porcelain` empty).

- [x] 2.4 **Validate:** `grep -cE 'sha256:[0-9a-f]{64}' scripts/check_manifests.py` returns 0 — the
  "no literal digest in the checker" claim, made runnable.

## 3. Make the assertions pass

- [x] 3.1 `sleap-roots-predictor-template.yaml`: append the verified digest to the `image:`
  reference as `:sha-e025e309…@sha256:4d4064c6…`, and add the `SRP_PREDICT_CONTAINER_DIGEST` env
  entry with that same digest. Leave the existing `ARGO_WORKFLOW_NAME` entry and its
  "inert today" comment untouched — that comment is accurate and belongs to sleap-roots#268.

- [x] 3.2 `sleap-roots-trait-extractor-template.yaml`: same two edits with the digest from 1.2.
  **Validate:** `python scripts/check_manifests.py` prints `=== ALL 71 ASSERTIONS PASS ===`
  (58 + 9 from 2.1 + 4 from 2.2). State the literal total, so a silently-skipped assertion cannot
  satisfy the check.

- [x] 3.3 Comment both the new `image:` digest and the new env entry. Both templates carry dense
  pin-history comment blocks; a digest appearing with no note breaks that convention. The `image:`
  comment records the digest-pin date and #70; the env comment records that the value must equal the
  digest in this file's own `image:` line, that `check_manifests.py` enforces it, that **the
  registry round-trip (task 1.x) is mandatory at every future bump** — with the command — and that,
  unlike `ARGO_WORKFLOW_NAME`, these are **not** inert.
  **Validate:** the claim inside the comment, not the presence of the string — confirm each producer
  still reads its variable at the pinned commit:
  `git -C C:\repos\sleap-roots-predict grep -n SRP_PREDICT_CONTAINER_DIGEST e025e309230de52cef0ccffa199048fe1dbd1b24 -- sleap_roots_predict/`
  and the `689cffb` equivalent in `C:\repos\sleap-roots`. Line numbers will move at the next bump;
  the command is what stays true.

- [x] 3.4 `bash scripts/lint_manifests.sh` from WSL (`argo lint` is not on the Windows PATH).
  **Validate:** both edited templates lint clean — i.e. the manifests still parse against the
  Workflow schema and `templateRef`s still resolve. This is **not** a check on the reference form or
  the digest: `argo lint` treats `image` as an opaque string and accepts both `tag@digest` and a
  syntactically-valid but nonexistent digest. Reference validity is proven by 1.3 and §7, nowhere
  else.

- [x] 3.5 Re-resolve the reference **exactly as written in each file** after the edits, closing the
  transcription gap between §1 and §3.
  **Validate:** both succeed against the registry.

## 4. Correct the falsified documentation claim

- [x] 4.1 Rewrite the mechanism at `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md:190`,
  the only site that states the wrong mechanism explicitly. Keep the requirement; correct why. The
  digest is not hashed; the image bakes `SRP_PREDICT_CODE_SHA`/`SRT_TRAITS_CODE_SHA`, which *are*
  key inputs, and a `sha-<gitsha>` tag can be silently overwritten by a rebuild of the same commit —
  so a digest, not a tag, is what keeps a retry's key identical.
  **Validate:** the corrected text names the code SHA as the key input and the digest as
  provenance-only, and cites lines 30-33 and 155-156 of the same file, which already state the
  correct position.

- [x] 4.2 Apply the **terminology-only** correction at the other four sites — they list the
  requirement without asserting a mechanism, so they need a different edit from 4.1, not a
  find-and-replace:
  - same file:76 (resume list)
  - same file:89 (component list — also false *today*, and still false for the bloomctl stages
    after this change; note that explicitly, cross-referencing #72)
  - `docs/bloom-integration/roadmap.md:1278` — **a different file**, which is precisely how this
    class of claim has survived past fixes (#62, #67, #68)
  - `docs/superpowers/plans/2026-07-06-a4-argo-workflow-poc.md:15` (historical plan doc)

  **Validate:** re-run the sweep
  (`grep -rn -i 'pinned container digest\|pinned image digest\|pinned digest\|per-run pin' --include='*.md' .`,
  excluding `openspec/changes/archive/`) and confirm every remaining hit either carries the corrected
  mechanism or is one of the two counter-sites.

- [x] 4.3 Correct the **registry** claim, which is false in three ways: it names GitLab when all
  five cluster templates pull from GHCR; it says GHCR migration is "not yet done"; and it lists a
  `models-downloader` stage the cluster DAG no longer has (plus `sleap-roots-traits` rather than its
  replacement `sleap-roots-trait-extractor`). Sites:
  - `openspec/project.md:43-45` (Docker stack) and `:172-174` (External Dependencies)
  - `.claude/skills/runai/SKILL.md` §5 — the registry statement, the stage table, and the
    "use the GitLab refs until then" instruction, which would actively mislead anyone following it
  - `.claude/skills/runai/SKILL.md` §6 example `--image` flag, and the `ImagePullBackOff`
    troubleshooting row
  - `.claude/commands/ci-debug.md:40` — same `ImagePullBackOff` row
  Leave the three `local-WSL2-*` templates' GitLab pins alone: they are *accurate* — those files
  really do reference GitLab — and re-pointing them is a functional change to a dry-run path that is
  already known broken (#21). The defect is describing them as the *current* registry, not their
  existence.
  **Validate:** `grep -rn -i 'registry.gitlab.com' --include='*.md' .` (excluding
  `openspec/changes/archive/` and `docs/bloom-integration/roadmap.md`, whose mentions are historical
  narrative about the A3-traits port and are accurate) returns no site that asserts GitLab is
  current. Cross-check against the live templates:
  `for f in sleap-roots-*-template.yaml; do grep -m1 -E '^\s+image:' $f; done` shows `ghcr.io` for
  all five.

- [x] 4.4 Also correct `openspec/project.md:64-65`, whose "Pin images by tag/digest … (full
  provenance/idempotency is A4, not yet implemented)" becomes strictly weaker than the rule this
  change makes normative for the two producers.
  **Validate:** the revised text requires `@sha256:` for the producers and records that the
  `bloomctl` stages stay tag-pinned (#72).

## 5. Pre-merge verification

- [x] 5.1 `python scripts/check_manifests.py` → `=== ALL 71 ASSERTIONS PASS ===`.

- [x] 5.2 `openspec validate add-container-digest-provenance --strict` passes.

- [x] 5.3 Re-read `compute_idempotency_key`'s signature in `sleap-roots-contracts` and confirm no
  container digest is among its inputs.
  **Validate:** the signature matches what `proposal.md` states (note it is keyword-only).

- [ ] 5.4 Open the PR with `/pr-description`, referencing this change-id and `Closes #70`.
  Per `.claude/commands/pr-description.md`'s three-state convention, anything not yet run is `[~]`,
  never `[x]`.

## 6. Apply to the cluster — do not leave this parked

A merged-but-unapplied template change is the #51/#53 pattern where repo and cluster diverged for
weeks. ⚠️ `runai-busch-lab` is shared by Bloom staging **and** production; every
`argo template update` is production-visible.

- [ ] 6.1 **Apply from a checkout refreshed to the merged SHA.** The shared `main` checkout on this
  machine sits at `3cf4b4f`, which still pins the **pre-#56** predictor image
  (`sha-f974632…`) — verified. Applying from it would silently revert #56's pin bump in production.
  **Validate:** `git rev-parse HEAD` equals this PR's squash-merge SHA on `origin/main`,
  `git status --porcelain` is empty, and `kubectl config current-context` is the
  `runai-busch-lab` argo-user context.

- [ ] 6.2 **Capture the rollback pre-image before any write** — `check_cluster_drift.sh`'s own
  header says to run it before as well as after, precisely because it doubles as that pre-image.
  Dump both live templates to the scratchpad (**not** the repo root, which does not ignore `*.yaml`):
  `argo template get <name> -n runai-busch-lab -o yaml > <scratch>/pre-<name>.yaml`.
  **Validate:** `bash scripts/check_cluster_drift.sh` reports drift on **exactly** the two producer
  templates and IN SYNC on the other three. Anything else means something drifted independently and
  this apply would erase it — stop and investigate.

- [ ] 6.3 `argo template update` both edited templates in `runai-busch-lab`.
  **Validate:** each command reports the template updated.

- [ ] 6.4 `bash scripts/check_cluster_drift.sh`.
  **Validate:** reports in-sync for all five templates. Hardened in #73 — it now fails loudly rather
  than printing `IN SYNC` when its own normaliser breaks.

- [ ] 6.5 Record the rollback procedure in the PR: `argo template update` from the
  `<scratch>/pre-*.yaml` dumps, or from the pre-merge SHA (`561d057` unless `main` moves first —
  record it at apply time, never assume it later; #56 had to correct exactly this claim after the
  fact). Trigger: any `ImagePullBackOff` or unexplained `Pending` in §7. Note the repo revert alone
  changes nothing on the cluster — with no CI, repo and cluster are independent states.

## 7. Prove it on a real run

Static assertions cannot show that a real run records a real digest.

⚠️ Use a **scratch path tree**, not the default `a4_poc` paths: those are production's working
directory (#63), the `run_manifest.json` there accumulates across runs (#71), and recomputing an
already-ingested scan currently fails at write-back (#76). Create
`/hpi/hpi_dev/users/eberrigan/pipeline_orchestration_tests/a4_scratch_<name>/{input,predictions,traits}`
**beforehand** — `hostPath type: Directory` requires the path to pre-exist, and a missing one leaves
the pod `Pending` forever rather than failing.

The scan must be **new to that tree**, or both stages skip on an unchanged idempotency key and the
envelope is never rewritten — the "skipped scans" scenario in the delta spec. A skipped scan proves
nothing here.

- [ ] 7.1 Submit one workflow against the scratch tree. The hostPaths are **hardcoded** in
  `sleap-roots-pipeline.yaml`, not parameterized, so this requires a locally-modified working copy.
  **That edit must not be committed** — the file is the one `salk-bloom` vendors byte-exact.
  **Validate:** both producer pods **pull successfully** — the one new failure mode this change
  introduces. Note a bad reference surfaces as a pod that hangs `Pending`, not one that fails, and
  there is no route to Argo pod logs (`pods/log` is not granted to `argo-user`; `kubectl auth can-i
  get pods/log` misleadingly answers `yes` because it parses as a resource name — `--subresource=log`
  correctly answers `no`, and a real fetch is Forbidden). Node status is the evidence.

- [ ] 7.2 **While the pods still exist** (Argo podGC/TTL will remove them), capture the kubelet's
  own view: `kubectl get pod <pod> -n runai-busch-lab -o jsonpath='{.status.containerStatuses[*].imageID}'`
  for both producers.
  **Validate:** each `imageID` digest equals the digest pinned in the corresponding deployed
  template. This is the **only** independent witness in the whole plan that the recorded digest is
  the image that actually ran; without it, 7.3 merely round-trips a human-typed string.

- [ ] 7.3 Read `provenance.predict_container_digest` and `provenance.traits_container_digest` from
  the resulting `{scan_key}.result.json` (NFS is mounted read-write on Windows at `Z:` =
  `\\multilab-na.ad.salk.edu\hpi_dev`), and also predict's own `{scan}.predictions.json`.
  **Validate:** each is **equal to the digest pinned by its deployed template** — not merely
  non-empty. Reading predict's manifest as well localizes a failure: the traits envelope's
  `predict_container_digest` arrives threaded from that manifest, so an empty value there
  distinguishes "the predictor's env var never landed" from "the threading dropped it".

- [ ] 7.4 **If §7 cannot run** (no cluster access, no suitable new scan), record it as
  `BLOCKED — <reason>, unblocked by <who/what>` rather than `[x]`, and do **not** run §6 either: the
  apply is justified only by the verification that follows it. The PR keeps `[~]` on both sections.

## 8. Record what was observed

- [ ] 8.1 Add a `docs/bloom-integration/roadmap.md` status-log entry recording **both** the
  2026-09-16 baseline (12 envelopes, six empty provenance fields) — which otherwise survives only in
  this proposal and is lost when the change is archived — and the digests read back in 7.3. Per
  convention the log records what was **observed, after the fact**, not what was expected at merge.
  This is a post-merge repo edit, so it is a second, small PR (the #60 → #75 shape).

- [ ] 8.2 Comment on #70 correcting its second comment, which cites `sha256:e39b4746…` as the
  trait-extractor's digest when that is `bloomctl`'s.
  **Validate:** the digest recorded in the comment is byte-identical to the one verified in 1.2.

- [ ] 8.3 Archive the change (`/cleanup-merged`) **after** §6 and §7, never before — the spec delta
  describes deployed reality, so archiving earlier records an aspiration. Verify every item above is
  `- [x]` or explicitly `BLOCKED` first.
