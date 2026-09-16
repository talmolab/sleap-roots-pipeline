# Tasks

## 1. Resolve and verify both digests against the registry

- [ ] 1.1 Resolve the **predictor** pin `ghcr.io/talmolab/sleap-roots-predict:sha-e025e309230de52cef0ccffa199048fe1dbd1b24`
  to its manifest digest. Expected
  `sha256:4d4064c6ac8dadc1bedcba594c74f0d7c4b9d907ee9001999d34e664317a4060` — already recorded in
  `openspec/changes/add-partial-success-exit-gate/tasks.md` task 1.2, so this is a re-confirmation,
  not a lookup. **Validate:** the resolved digest equals the recorded one.

- [ ] 1.2 Resolve the **trait-extractor** pin `ghcr.io/talmolab/sleap-roots-trait-extractor:sha-689cffb`.
  This digest is **not recorded anywhere in this repo** and must be looked up. Note predict tags the
  full 40-char sha while `bloomctl` tags 7 — do not pattern-match one pin from another.
  ⚠️ **Do not reuse `sha256:e39b4746…`**: that is `bloomctl`'s digest (images-downloader /
  write-back), and a comment on #70 misattributes it to the trait-extractor.
  **Validate:** the digest round-trips — requesting the manifest *by digest* returns HTTP 200 with a
  matching `Docker-Content-Digest`, and the image config's
  `org.opencontainers.image.revision` starts with `689cffb`.

## 2. Add the failing assertions first (TDD)

- [ ] 2.1 In `scripts/check_manifests.py`, add a `PRODUCER_DIGEST_ENV` mapping
  (`predictor` → `SRP_PREDICT_CONTAINER_DIGEST`, `trait-extractor` → `SRT_TRAITS_CONTAINER_DIGEST`)
  and a requirement block asserting, per producer stage: the `image:` reference is digest-pinned;
  the env var is present exactly once; its value matches `^sha256:[0-9a-f]{64}$`; and its value
  equals the digest **parsed from that template's own `image:` line**. No literal digest may appear
  in the checker. Also assert the trait-extractor declares no `SRP_PREDICT_CONTAINER_DIGEST`.
  **Validate:** `python scripts/check_manifests.py` now **fails**, reporting the new assertions
  against the not-yet-edited manifests, while the pre-existing 58 still pass.

## 3. Make the assertions pass

- [ ] 3.1 `sleap-roots-predictor-template.yaml`: append the verified digest to the `image:`
  reference as `:sha-e025e309…@sha256:4d4064c6…`, and add the `SRP_PREDICT_CONTAINER_DIGEST` env
  entry with that same digest. Leave the existing `ARGO_WORKFLOW_NAME` entry and its
  "inert today" comment untouched — that comment is accurate and belongs to sleap-roots#268.
  **Validate:** `python scripts/check_manifests.py` predictor digest assertions pass.

- [ ] 3.2 `sleap-roots-trait-extractor-template.yaml`: same two edits with the trait-extractor's
  verified digest from 1.2.
  **Validate:** `python scripts/check_manifests.py` reports **all** assertions passing (58 + the
  new ones).

- [ ] 3.3 Comment each new env entry with what it is for and the one rule that matters: the value
  must equal the digest in this file's own `image:` line, and `scripts/check_manifests.py` enforces
  that. Unlike `ARGO_WORKFLOW_NAME`, these are **not** inert — both producers read them today.
  **Validate:** each comment names the reading producer and source file
  (`output_contract.py:226` / `envelope.py:73`).

- [ ] 3.4 `bash scripts/lint_manifests.sh` from WSL (`argo lint` is not on the Windows PATH).
  **Validate:** both edited templates lint clean, and `argo lint` accepts the `tag@digest`
  reference form.

## 4. Correct the falsified documentation claim

- [ ] 4.1 In `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`, correct the
  **mechanism** of the "pinned container digest" claim at both sites (the resume list, and the
  "Required for correctness" list). No container digest is an input to `compute_idempotency_key`;
  the same file already says so, so the document currently contradicts itself. Keep the
  requirement — pinning does stabilise the key, via the `SRP_PREDICT_CODE_SHA` /
  `SRT_TRAITS_CODE_SHA` **baked into the image**, which *are* key inputs.
  **Validate:** the corrected text names the code SHA as the key input and the digest as
  provenance-only, consistent with the same file's existing statement.

- [ ] 4.2 Grep the claim tree-wide, not just in the file where it was noticed — this repo has
  repeatedly shipped a fix to one site of a claim that lived in several (#62, #67, and one claim
  found in nine places in #60; tracked as #68).
  **Validate:** a search for digest-in-the-idempotency-key wording returns no remaining
  uncorrected site outside `openspec/changes/archive/`.

## 5. Pre-merge verification

- [ ] 5.1 `python scripts/check_manifests.py` — all assertions pass, count increased from 58.
  **Validate:** the printed total matches 58 plus the number of assertions added in 2.1.

- [ ] 5.2 `openspec validate add-container-digest-provenance --strict` passes.

- [ ] 5.3 Confirm no recompute is implied: re-read `compute_idempotency_key`'s signature in
  `sleap-roots-contracts` and confirm no container digest is among its inputs.
  **Validate:** the signature is unchanged from what `proposal.md` states.

- [ ] 5.4 Open the PR with `/pr-description`, referencing this change-id and `Closes #70`, and
  noting that `ARGO_WORKFLOW_UID` / `ARGO_NODE_ID` are deliberately excluded (nothing reads them;
  they belong with sleap-roots#268).

## 6. Apply to the cluster — do not leave this parked

A merged-but-unapplied template change is the #51/#53 pattern where repo and cluster diverged for
weeks. ⚠️ `runai-busch-lab` is shared by Bloom staging **and** production; every
`argo template update` is production-visible.

- [ ] 6.1 Confirm the target context before any write: `kubectl config current-context`.
  **Validate:** the context is the `runai-busch-lab` argo-user kubeconfig, not another cluster.

- [ ] 6.2 `argo template update` both edited templates in `runai-busch-lab`.
  **Validate:** each command reports the template updated.

- [ ] 6.3 `bash scripts/check_cluster_drift.sh`.
  **Validate:** reports in-sync for both templates. Note this script was hardened in #73 — it now
  fails loudly rather than printing `IN SYNC` when its own normaliser breaks.

## 7. Prove it on a real run

Static assertions cannot show that a real run records a real digest.

⚠️ Use a **scratch path tree**, not the default `a4_poc` paths: those are production's working
directory (#63), the `run_manifest.json` there accumulates across runs (#71), and recomputing an
already-ingested scan currently fails at write-back (#76). Create
`/hpi/hpi_dev/users/eberrigan/pipeline_orchestration_tests/a4_scratch_<name>/{input,predictions,traits}`
**beforehand** — `hostPath type: Directory` requires the path to pre-exist, and a missing one leaves
the pod `Pending` forever rather than failing.

- [ ] 7.1 Submit one workflow against the scratch tree.
  **Validate:** the predictor and trait-extractor pods **pull successfully** under the new
  `tag@digest` reference — this is the one new failure mode the pin introduces, and it surfaces as
  `ImagePullBackOff` at first submit if the form is mishandled. Note there is currently no route to
  Argo pod logs (`pods/log` is not granted to `argo-user`, and `argo logs` exits 0 while writing its
  error only to stderr), so node status is the evidence.

- [ ] 7.2 Read `provenance.predict_container_digest` and `provenance.traits_container_digest` from
  the resulting `{scan_key}.result.json` (NFS is mounted read-write on Windows at `Z:` =
  `\\multilab-na.ad.salk.edu\hpi_dev`).
  **Validate:** each is **equal to the digest pinned by its deployed template** — not merely
  non-empty. All 12 pre-existing envelopes read empty, so non-empty is the signal that something
  changed, but non-blank-but-wrong is exactly the failure this change could introduce, so equality
  is the acceptance criterion.

- [ ] 7.3 Record the observed result in `docs/bloom-integration/roadmap.md`'s status log, per this
  repo's convention that the log records **what was observed, after the fact**, not what was
  expected at merge.

## 8. Correct the misattributed digest on the issue

- [ ] 8.1 Comment on #70 noting that its second comment cites `sha256:e39b4746…` as the
  trait-extractor's digest, but that is `bloomctl`'s; record the verified trait-extractor digest so
  the next reader does not inherit the error.
