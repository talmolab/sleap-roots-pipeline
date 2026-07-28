# A4 — wire batch stage-in + write-back into the Argo DAG (design)

**Date:** 2026-07-28 · **Owner:** eberrigan · **Tier:** A4 (roadmap `docs/bloom-integration/roadmap.md`)
**Status:** design (brainstormed 2026-07-28); pending review → implementation planning.

## 1. Goal

Turn `sleap-roots-pipeline.yaml`'s DAG from a hardcoded two-task PoC (`predictor`→`trait-extractor`
against one fixed scan directory) into a real four-task per-batch pipeline that stages scans in and
writes results back via `bloomctl`'s new batch commands
([bloom #532](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/532)):

```
images-downloader → predictor → trait-extractor → write-back
```

This is the next unblocked A4 deliverable per the roadmap's A4 change-breakdown table
(`images-downloader`/`workflow template`/`write-back` rows) and the
[2026-07-06 design doc](2026-07-06-a4-request-driven-pipeline-design.md) (component 2 of §11:
"the per-batch Argo `WorkflowTemplate`... this repo").

## 2. Context — what's already true

- **`predictor` and `trait-extractor` need no changes.** Both are already batch-capable
  (`sleap_roots_predict.run_batch`, `trait_extractor.extract_batch`) — they already discover and
  loop every scan under a directory. The gap is purely the two `bloomctl`-based stages.
- **The `bloomctl` image tag matters.** `ghcr.io/salk-harnessing-plants-initiative/bloomctl:0.1.0a2`
  (`sha-1bb03f6`, referenced elsewhere in the roadmap) predates
  [bloom #532](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/532) and lacks the
  batch commands. The correct tag is **`sha-61959bd`** (auto-built on #532's push to `staging`; no
  versioned release has been cut yet — see the roadmap's 2026-07-27 status-log entry).
- **`bloomctl` auth is email+password only**, stored as a dotenv file at `~/.bloom/credentials.txt`
  (`bloomcli/src/bloomctl/credentials.py`) — no service-role-key path exists. `load_credentials()`
  reads that file directly; it does not require the interactive `bloomctl login` command to have
  run in-process. This means a Kubernetes Secret mounted at that path works today, with zero
  `bloomctl` code changes (bloom #398, "non-interactive auth," is not a dependency of this change).
- **The actual credential (sleap-roots-pipeline#17) is being provisioned in a parallel session**
  (`salk-bloom`, see `C:\vaults\sleap-roots\bloom-pipeline-integration\handoff_prompts\
  new_session_prompt_a4_credential_provisioning.md`). All the DB-side grants `bloom_workflows`
  needs already exist (verified against the actual migrations); what's missing is the account
  itself. This change wires the *reference* to a Secret (name TBD, e.g.
  `bloom-pipeline-credentials`); it will not be live/functional until that other session's work
  lands, and that's expected — not a blocker for merging this change.

## 3. Architecture

**DAG:**
- `images-downloader` (new): `bloomctl cyl batch-download-for-predict <images-input-dir>
  --scan-ids {{workflow.parameters.scan-ids}}`. Writes into the same `images-input-dir` volume
  `predictor` already reads.
- `predictor` (unchanged).
- `trait-extractor` (unchanged).
- `write-back` (new): `bloomctl cyl batch-ingest-result <traits-output-dir> --predictions-dir
  <predictions-output-dir>`. Reads the same `traits-output-dir`/`predictions-output-dir` volumes
  `trait-extractor`/`predictor` already write.

```yaml
tasks:
  - name: images-downloader
    templateRef: {name: sleap-roots-images-downloader-template, template: images-downloader}
  - name: predictor
    templateRef: {name: sleap-roots-predictor-template, template: predictor}
    dependencies: [images-downloader]
  - name: trait-extractor
    templateRef: {name: sleap-roots-trait-extractor-template, template: trait-extractor}
    dependencies: [predictor]
  - name: write-back
    templateRef: {name: sleap-roots-write-back-template, template: write-back}
    dependencies: [trait-extractor]
```

**Workflow-level input:** `arguments.parameters: [{name: scan-ids, value: ""}]` — a caller (manual
`argo submit --parameter scan-ids=...` for now; Bloom's not-yet-built trigger route later) supplies
the batch. Volumes stay the existing fixed `a4_poc` hostPath paths — no per-run path isolation yet,
since nothing can submit concurrently regardless (no trigger route exists to do so). This is a
known, explicitly-deferred gap (§8).

**Deferred, not part of this change:** the Argo semaphore (design §9) for concurrent-batch
concurrency control — there is no caller yet that could submit more than one batch at a time, so
there's nothing to gate. Revisit alongside the Bloom trigger route/dispatch worker
(bloom #11/#404).

## 4. Task-level specs

Two new single-task `WorkflowTemplate` files, matching the existing one-file-per-task convention
(`sleap-roots-predictor-template.yaml`, `sleap-roots-trait-extractor-template.yaml`):

**`sleap-roots-images-downloader-template.yaml`:**
```yaml
container:
  image: ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd
  args: ["cyl", "batch-download-for-predict", "/workspace/images_input",
         "--scan-ids", "{{workflow.parameters.scan-ids}}"]
  env: [{name: HOME, value: /home/bloom}]
  volumeMounts:
    - {name: images-input-dir, mountPath: /workspace/images_input}
    - {name: bloom-credentials, mountPath: /home/bloom/.bloom/credentials.txt,
       subPath: credentials.txt, readOnly: true}
```

**`sleap-roots-write-back-template.yaml`:**
```yaml
container:
  image: ghcr.io/salk-harnessing-plants-initiative/bloomctl:sha-61959bd
  args: ["cyl", "batch-ingest-result", "/workspace/input",
         "--predictions-dir", "/workspace/predictions"]
  env: [{name: HOME, value: /home/bloom}]
  volumeMounts:
    - {name: traits-output-dir, mountPath: /workspace/input}
    - {name: predictions-output-dir, mountPath: /workspace/predictions}
    - {name: bloom-credentials, mountPath: /home/bloom/.bloom/credentials.txt,
       subPath: credentials.txt, readOnly: true}
```

Both: `priorityClassName: interactive-preemptible` + `retryStrategy` (limit 2), matching
`trait-extractor`'s CPU-task pattern (not `predictor`'s GPU one). Modest CPU/memory requests — both
are I/O-bound HTTPS calls, not compute. Neither sets `privileged: true`/`runAsUser: 0` — unlike
`predictor`/`trait-extractor`, this genuinely doesn't need it (non-root image, no GPU/device
access), and it would just be copying an already-flagged TODO debt forward without reason.

**Why `HOME=/home/bloom` is set explicitly:** `bloomcli`'s Dockerfile creates its runtime user via
`adduser --system` with no explicit home directory, so where Python's `Path.home()` resolves is
genuinely ambiguous without it. Setting `HOME` directly sidesteps that ambiguity — `bloomctl`'s
`load_credentials()` reads `Path.home()/.bloom/credentials.txt`, so this makes the mount path
deterministic.

**New Workflow-level volume:**
```yaml
- name: bloom-credentials
  secret:
    secretName: bloom-pipeline-credentials   # provisioned by the parallel #17 session
```

## 5. Error handling

- Both new commands already implement the design doc's §8 exit-code policy internally: non-zero
  exit if *any* item failed, exit 0 on empty input or all-ok/skipped. A whole-batch `retryStrategy`
  retry is safe and cheap here — neither task pays a model-reload cost, and both have their own
  skip-if-done (`batch-download-for-predict`) / idempotent-no-op (`batch-ingest-result`) logic
  internally. This differs from `predictor`, where a whole-batch retry is more expensive.
- Until the credential lands, both new tasks will fail with a clear `bloomctl` auth error, not a
  silent hang or a wiring bug — worth a manifest comment so a red `images-downloader` node reads
  correctly.
- To verify in testing, not assume: whether `batch-download-for-predict --scan-ids ""` (the
  parameter's empty default) exits 0 as "empty input," or errors as a CLI parse failure. This
  determines whether an unparameterized `argo lint`/dry-submit is a safe sanity check.

## 6. Validation plan

No app code, no pytest — this repo's validation is manifest-level:
1. `argo lint` on all 4 touched/new files.
2. **Real local WSL2 dry-run.** Sync `local-WSL2-sleap-roots-pipeline.yaml` to the same four-task
   DAG (dropping the stale leftover `models-downloader` task it still carries from before an
   earlier A4 change dropped it on the cluster side), add matching local template files. For
   credentials, skip the Kubernetes Secret — bind-mount the real local `~/.bloom/credentials.txt`
   as a `hostPath` volume, so this genuinely exercises both new `bloomctl` commands against real
   Bloom data.
3. Live cluster E2E is **not** a validation target for this change — it's blocked on the credential
   regardless of how well this is built. `argo lint` clean + a successful local WSL2 run are the
   bar to merge; cluster testing happens once the credential lands.

## 7. OpenSpec capability delta

The existing `per-scan-pipeline` capability asserts a two-task DAG against one hardcoded scan. This
change doesn't remove single-scan support — a single scan is just a batch of size 1 through the new
pipeline — but it does mean there's no longer a *separate* scan-only pathway, so keeping the
`per-scan-pipeline` id would actively mislead future readers into thinking one still exists.
**Decision: ADD a new `per-batch-pipeline` capability, REMOVE `per-scan-pipeline`.** The new
capability's requirements describe the four-task DAG, batch-size-agnostic (including N=1), the
`bloomctl` image pin, and the credential-mount shape.

## 8. Explicitly deferred (production follow-ups, not part of this change)

- **Argo semaphore** (design §9) — no caller can submit concurrent batches yet.
- **Per-run path isolation** — reusing one fixed `a4_poc` path is fine with zero concurrent
  callers, but will need a real per-`pipeline_run_id`/`batch_index` scheme before production
  traffic (ties into the not-yet-built `cyl_pipeline_runs` data model's `argo_workflow_name`/
  `batch_index` columns).
- **`sha-61959bd` image pin** — an interim commit-sha tag from an unreleased build. Move to a real
  version tag once `bloomcli` cuts one, and expect to keep bumping this pin as `bloomcli` evolves.
- **Dev-personal hostPath convention** — `images-input-dir` etc. still point at
  `/hpi/hpi_dev/users/eberrigan/...`, not a shared production path convention.
- **Bloom-side trigger route + `cyl_pipeline_runs` tables + dispatch worker** (bloom #11/#404) —
  today the batch is supplied via a manual `argo submit --parameter`.
- **Producer Argo-readiness reconciliation** (sleap-roots #259, predict #26) — a single failing
  scan still fails/retries the *whole* predict/traits batch, not isolated.
- **Notification** (sleap-roots-pipeline#18) — channel still undefined.
