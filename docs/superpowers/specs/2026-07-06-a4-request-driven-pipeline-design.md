# A4 — Request-driven per-scan phenotyping pipeline (design)

**Date:** 2026-07-06 · **Owner:** eberrigan · **Tier:** A4 (roadmap `docs/bloom-integration/roadmap.md`)
**Status:** design (brainstormed 2026-07-06). ⚠️ **§5/§6/§10 (the `cyl_pipeline_runs` runs-table + Supabase-Realtime approach) are SUPERSEDED for v1** — see the banner below.

> **⚠️ Superseded for v1 (decision reaffirmed 2026-07-08).** The **`cyl_pipeline_runs` / `cyl_pipeline_run_scans` runs-table + Supabase-Realtime subscription + queue** approach in **§5 (Data model)**, **§6 (Execution topology, status side)**, and **§10 (Bloom UI)** was **decided against for v1**. v1 is Bloom's `workflows` service submitting Workflow CRDs **directly**, with **Argo/RunAI owning run status + the GPU admission queue** (the write-back RPC already persists `pipeline_run_id` + provenance on `cyl_trait_sources`). Any Bloom-native runs/status/cancel UX — and any runs table — stays **out of scope → EPIC #15**. Reaffirms the 2026-07-01 roadmap decision ("No `cyl_pipeline_runs` table for v1"; the SKIP-LOCKED / pgmq queue options raised on bloom #404 were considered and declined for v1). **The rest of this doc stands:** stage-in (§3/§4), predict/traits compute, dedup/write-back (§7), resumability (§8), and RunAI-quota concurrency (§9, "no custom queue").

## 1. Goal

A Bloom user clicks **Run** on a scan or an experiment → the sleap-roots phenotyping pipeline
runs on the RunAI GPU cluster (predict → traits) → results are written back into Bloom with full
provenance → the user watches live status and sees results in Bloom's existing trait views.
Redundant work is skipped (already-computed scans are reused), GPU use is bounded, and a
crash/preemption resumes where it left off.

## 2. Context & constraints (grounded 2026-07-06)

- **Producers already exist:** A3-predict (warm `WarmModelWorker`, load-once, wandb registry) and
  A3-traits (`trait_extractor` service, emits per-scan `ResultEnvelope`, sleap-roots #254 **merged**)
  and A3-params (`resolve_params`, predict #18 **merged**). A2 write-back RPC
  `insert_cyl_result_envelope(jsonb)` is merged (idempotent, first-writer-wins).
- **Two network planes:**
  - **Control plane (submit):** `bloom-dev → cluster` Argo/k8s — **firewall-blocked** today.
  - **Data plane (stage-in + write-back):** `cluster → bloom.salk.edu:443` — **works**.
- **Bloom has a `workflows` FastAPI service** (Benfica, `services/workflows/`, on bloom-dev behind
  Caddy `/workflows/*`, JWT + `bloom_workflows` least-privilege role) + a `video_jobs`
  LISTEN/NOTIFY + Realtime queue pattern. **Reuse both.** (On `staging`; #391 open. Coordinate.)
- **Cyl access model is SHARED:** every authenticated `bloom_user` sees all cyl scans / experiments
  / traits / blobs (`USING (true)`); writes are role-gated / RPC-only (post change E). anon: none.
- **Cluster storage** is a **file mount shared across the GPU nodes** (not node-local hostPath) —
  intermediates are durable + node-independent.
- **Idempotency key** (contract `compute_idempotency_key`, verified) hashes
  `scan_key + images_checksum + models[(registry_id,version,weights_checksum)] + param_hash +
  predict_code_sha + traits_code_sha (+ predict_output_params)`. **Model version is included** →
  "done for latest models + params" works with no contract change.

## 3. Architecture

**Trigger = PUSH.** Bloom's `workflows` service submits directly to the cluster Argo. The
bloom→cluster hop uses **Tailscale now / the firewall rule later** — a pure transport swap: no app
change when ITS opens the firewall. No cluster-side connector (no CronWorkflow, no listener). The
control-plane direction is the *only* thing Tailscale/firewall affects; the data plane
(stage-in + write-back over 443) is untouched.

**End-to-end flow:**

1. User clicks **Run** (scan|experiment) in Bloom web → `POST bloom.salk.edu/workflows/pipeline`
   with the user's Supabase JWT + `{target_level, target_id, params}`.
2. `workflows` service: authenticate (JWT) + rate-limit → resolve params (defaults from Bloom
   metadata via A3-params, user overrides win) → **enumerate scans** (experiment → its scan list) →
   **dedup pre-check** (skip scans already computed for these models+params — §7) → write
   `cyl_pipeline_runs` parent + per-scan children (`queued`/`reused`) → **chunk the to-run scans
   into batches** (≤ `BATCH_SIZE`) → **submit one Argo workflow per batch** (push) → return
   `pipeline_run_id`.
3. Each Argo workflow (one per batch), **staged**:
   - `download-all` — stage-in one batch's scans via bloomcli over 443, as a **nested tree** on the
     shared mount: `{scan_key}/<frames>` + `{scan_key}.scan_metadata.json` (the `ScanMetadata` sidecar
     — `image_ids` / `images_checksum` / normalized `{species,mode,age}` params — is **authored here**,
     not by predict).
   - `predict-all` — **one warm GPU pod**: load models once, loop the batch's scans (skip any with a
     valid prediction on the shared mount *or* an existing Bloom source), write predictions **and copy
     each scan's sidecar verbatim forward** into `out/{scan_key}/` (**D1** — makes predict's output a
     self-contained trait-extractor input tree; predict never authors the sidecar), then exit → **GPU
     released**. *(Closes the sidecar-bridge gap: the sidecar is authored into predict's input mount but
     traits reads from predict's output mount — predict bridges the two by copy-through.)*
   - `traits+writeback` — per scan (loop/fan-out, CPU): compute traits → `insert_cyl_result_envelope`
     RPC over 443 (idempotent), update the scan's child row `written` + `source_id`.
   - `notify`.
4. Status: workflows service **polls Argo** → updates `cyl_pipeline_runs.status`; per-scan progress
   ("12/40") is a **count of done children / source rows** for the `pipeline_run_id`. Browser watches
   `cyl_pipeline_runs` via **Supabase Realtime**.
5. Resume (crash/preemption): each stage is a **skip-if-done loop** over a durable checkpoint —
   predictions on the shared mount (predict), source rows in Bloom (write-back) — plus Argo
   `retryStrategy`, atomic writes, and a pinned container digest per run.

## 4. Components (by repo)

**Bloom (`services/workflows/` + migrations — coordinate with Benfica):**
- New route `POST /workflows/pipeline` (+ `GET /workflows/runs/{id}` if needed): auth, rate-limit,
  param-resolve, enumerate, dedup pre-check, insert run rows, chunk, submit to Argo, poll Argo →
  update status.
- New tables `cyl_pipeline_runs` + `cyl_pipeline_run_scans` (§5) with shared RLS + Realtime.
- Extend/confirm the `bloom_workflows` role grants (**see risk R1**).

**sleap-roots-pipeline (this repo — Argo):**
- Per-batch `WorkflowTemplate`: `download-all → predict-all(warm) → traits+writeback → notify`, with
  `retryStrategy`, an **Argo semaphore** for GPU-batch concurrency (§9), a pinned image digest, and
  the shared-mount volume.
- The submit contract the workflows service targets (workflow name = `pipeline_run_id`+batch,
  labels `pipeline_run_id`/`scan set`).

**Producers (predict / sleap-roots trait_extractor):** already built; A4 wires them into the
template. Add the per-scan **skip-if-done** check (mount + Bloom source) to the predict loop.

**Transport:** Tailscale (temporary) or the firewall rule (permanent) — bloom-dev ↔ cluster Argo.

## 5. Data model

> **⚠️ SUPERSEDED for v1** — the `cyl_pipeline_runs` / `cyl_pipeline_run_scans` tables below were **decided against**; run status lives on Argo/RunAI + `cyl_trait_sources.pipeline_run_id`. See the top banner (→ EPIC #15).

**`cyl_pipeline_runs`** (one per request; the Realtime subscription target):

| column | notes |
|---|---|
| `pipeline_run_id` uuid PK | batch key; rides into provenance via the write-back RPC |
| `target_level` ('scan'|'experiment'), `target_id` bigint | request target |
| `params` jsonb | resolved `{species, mode, age}` + which were overrides |
| `requested_by` uuid | **attribution only** (not a visibility filter) |
| `status` | `queued → submitted → running → complete | partial | failed` |
| `scan_count`, `done_count`, `reused_count`, `failed_count` | for "N/M" (trigger/view-maintained) |
| `created_at`, `submitted_at`, `completed_at`, `error_message` | timeline |

**`cyl_pipeline_run_scans`** (one per scan; per-scan ledger + resume state):

| column | notes |
|---|---|
| `id` PK, `pipeline_run_id` FK, `scan_id` FK, `UNIQUE(pipeline_run_id, scan_id)` | |
| `batch_index`, `argo_workflow_name` | which batch/Argo workflow — Bloom↔Argo traceability |
| `status` | `queued → predicted → written | reused | failed` |
| `attempts` int | drives retry-then-isolate |
| `source_id` FK → cyl_trait_sources (null until done) | links request → result/provenance |
| `error_message`, timestamps | |

**Security (match cyl):** RLS on; `admin_all` (`FOR ALL TO bloom_admin`); `user_read`/`agent_read`
(`FOR SELECT … USING (true)`) — **shared reads for all members**; writes gated to the workflows
role + the scoped cluster credential (child status updates). anon: none. Both a table `GRANT` and a
matching RLS policy are required (PostgREST two-layer gate). Parent (and optionally children)
published to Supabase Realtime; Realtime honors RLS.

## 6. Execution topology

> **⚠️ Status-tracking via the runs table is SUPERSEDED for v1** (see top banner); the `download → predict → traits → write-back` topology itself stands.

- **One Argo workflow per *batch*** (not per scan). Scan run = 1 batch; experiment = ⌈N/BATCH_SIZE⌉
  batches, all sharing `pipeline_run_id`. Batches parallelize across GPUs via RunAI.
- **predict-all is ONE warm GPU pod per batch** — loads models once, loops the batch's scans. This
  is *not* an Argo per-scan fan-out (that would reload models per scan). Only the cheap CPU stages
  (traits+writeback) may fan out per scan.
- **GPU held only for the predict phase** of a batch; released before traits+writeback.
- `BATCH_SIZE` is a config knob (default ~25–50; tune so model-load is a small fraction of batch
  runtime). `MAX_SCAN_ATTEMPTS` config (e.g. 3).

## 7. Deduplication — defining "done"

A scan is **done for (data, models, params, code)** iff a `cyl_trait_sources` row exists whose
`idempotency_key` == the identity of what would be computed now. The key **includes model version**
(verified), so a production-model bump invalidates "done" and forces recompute; identical inputs
reuse.

**Requirement — bake the traits code sha (`SRT_TRAITS_CODE_SHA`).** The key hashes `traits_code_sha`,
which the emitter (`build_provenance`) reads from the **`SRT_TRAITS_CODE_SHA`** env, falling back to
`""` if unset. The **trait-extractor image MUST bake `SRT_TRAITS_CODE_SHA` = its build git sha**
(workflow build-arg → `ENV`), or `traits_code_sha` stays empty and a **traits-code change would not
invalidate "done"** (a re-run would collide with the stale result via first-writer-wins). Predict's
`predict_code_sha` + resolved model versions ride in via its manifest; the **traits side must supply
its own code sha**. (Not required for the bare PoC, which doesn't exercise dedup; land it with the
trait-extractor image change `add-trait-extractor-image` or the dedup slice.) `SRT_TRAITS_CONTAINER_DIGEST`
is only *recorded* in provenance, not hashed, so baking it is optional.

- **Cluster-side per-scan skip (the reliable layer):** the predict loop, per scan, checks Bloom for a
  matching source (exact `idempotency_key`) and skips inference — the same skip-if-done used for
  resume, extended to cross-run dedup. This is always correct because the pipeline *knows* the current
  models (it resolves them) and its own code_sha. Cost when a whole batch is already done: a GPU pod
  is still scheduled and loads models once, then skips every scan and exits (no inference).
- **Bloom-side pre-check (optional optimization — avoids scheduling the pod at all):** at submit,
  compare the request's `params` + **current production model versions** against the recorded
  Provenance (`models` + `params`) in the latest `cyl_trait_sources.metadata`. Params are computable
  Bloom-side (import the contract's `compute_param_hash`); the recorded result's models are in
  `metadata`. **The catch:** Bloom must also know what models *would* run now — that's a wandb
  **registry lookup** (or a "current production models" manifest the pipeline publishes for Bloom to
  cache). **Decision for implementation:** if that current-models signal is cheaply available to the
  workflows service, do the full short-circuit (fully-done request → `complete`, submit nothing);
  otherwise rely on the cluster-side skip above and skip the Bloom-side pre-check for v1. Either way
  reused scans are marked `reused` and the model-version-aware `idempotency_key` guarantees
  correctness — the pre-check is purely a "don't even schedule the pod" optimization.

## 8. Resumability & error handling

**Principle:** each stage is an idempotent skip-if-done loop over a *durable* checkpoint; Argo
retries the *step*, the loop fast-forwards past finished work. Two checkpoints (both node-independent
via the shared mount + Bloom):
- predict done = valid prediction on the shared mount (existence **and** manifest checksum/size).
- write-back done = Bloom source row (`idempotency_key`).

**Predict pod crash / preemption (worked example, dies at scan 25/40):** scans 1–24 predictions are
on the shared mount (atomic temp→rename); scan 25 at most a temp file (not valid); Bloom empty
(write-back is later). Argo `retryStrategy` schedules a fresh pod (any node), loads models **once**,
skips 1–24 (checksum-verified), re-predicts 25, finishes 26–40. Net cost: one reload + the tail,
never the batch.

**Required for correctness:** atomic temp→rename writes; **checksum-verified** skip (not
existence-only); shared mount; **pinned container digest** per run (so a retry recomputes an
identical key and recognizes done work); Argo `retryStrategy` (crash/OOM/preempt).

**Scan-level failure — retry-then-isolate:** retry a failing scan up to `MAX_SCAN_ATTEMPTS`
(attempt count next to the checkpoint / on the child row); if it still fails (or repeatedly kills the
pod), mark that scan `failed` and continue the batch → run ends `partial` (e.g. 39/40 + 1 failed)
rather than blocking. Distinguish **scan-level error** (mark failed, continue) from **pod-level
death** (Argo retry + resume-skip).

**Producer Argo-readiness — reconcile *both* producers uniformly.** The predict batch runner and the
traits driver share the same three behaviours that need one A4-wiring decision: (a) **empty input →
exit 0** (a silent-green node if stage-in produced nothing), (b) **exit non-zero if *any* scan fails →
`retryStrategy` retries the whole batch** (not a partial run), and (c) **no init / SIGTERM handler** for
graceful preemption. Tracked for traits as [sleap-roots #259](https://github.com/talmolab/sleap-roots/issues/259);
**predict has the identical behaviour** (`run_batch` returns `ok=True` on empty input, exits non-zero on
any failed scan). Resolve the exit-code / empty-input / SIGTERM policy the *same way for both* at wiring
time — else you fix traits and leave predict silently green on an empty stage-in. (Also: the PoC's
**existence-only** skip is only safe once writes are **atomic** (temp→rename) — land those two together,
or a truncated manifest is skipped as done.)

## 9. Concurrency & resource control (no custom queue)

- **RunAI project quota = the GPU admission queue.** GPU pods beyond the quota are **queued
  (pending)** by RunAI until GPUs free; fair-share + preemption handle contention. Set the
  `talmo-lab` quota to the intended max concurrent GPU jobs.
- **Argo semaphore (ConfigMap-backed)** = app-level gate: every GPU batch acquires `pipeline-gpu: K`
  (K ≤ quota) → at most K pipeline batches active at once; the rest wait in Argo. Protects other
  RunAI users and the write-back rate. (A `mutex` would serialize to 1.)
- **Batching** inherently bounds pod count (experiment = ⌈N/BATCH_SIZE⌉ GPU pods, not N).
- Optional: workflow `parallelism` (CPU fan-out per run), workflow **priorities** (manual > backfill).

## 10. Bloom UI integration (mirrors the video-jobs pattern)

> **⚠️ SUPERSEDED for v1** — no `cyl_pipeline_runs` runs-table / Realtime UI in v1 (see top banner). → EPIC #15.

- **Trigger:** "Run pipeline" button on scan/experiment pages + a params panel (species/mode/age
  prefilled from metadata, overridable) → `POST /workflows/pipeline` with JWT.
- **Pre-check preview:** "38/40 already have results for these params — 2 will run" (from §7).
- **Live status:** a shared "Pipeline runs" panel (all members; `requested_by` shows who launched)
  reading `cyl_pipeline_runs` via **Realtime** (status + "N/M", no polling); per-scan drill-down from
  children.
- **Results:** no new results UI — results land in the **existing** trait tables/views; the run panel
  links to them (+ `.slp`/Box blob links).

## 11. Cross-repo decomposition (one design → per-repo OpenSpec changes)

1. **bloom** (coordinate w/ Benfica): `cyl_pipeline_runs`/children migration + RLS + Realtime;
   `POST /workflows/pipeline` route (auth, resolve, enumerate, dedup pre-check, submit, poll);
   `bloom_workflows` role grants.
2. **sleap-roots-pipeline** (this repo): the per-batch Argo `WorkflowTemplate` + semaphore +
   retryStrategy + shared-mount + submit contract.
3. **producers**: predict-loop **skip-if-done** (mount + Bloom source) for dedup/resume.
4. **infra**: Tailscale (temporary) / firewall rule (permanent); RunAI quota; scoped Supabase
   credential (roadmap #17) extended to update child status.

## 12. Open coordination items & risks

- **R1 — `bloom_workflows` grants gap:** the role has **no cyl RLS/GRANTs in any migration** (only
  the staging JWT branch). Confirm with Benfica how it gets cyl read access before relying on it to
  read scans / write `pipeline_runs`. **Tracked: salk-bloom #404** (for the Benfica discussion).
- **R2 — main vs staging — NOT a blocker (per eberrigan):** the A2 lockdown is staging-only and
  production (`main`) is behind, but staging→main promotion is handled separately; this design
  targets the staging end-state and does not gate on it.
- **R3 — Tailscale needs an internal-side presence.** For the **PoC**, the simplest option is a
  **Tailscale subnet router on an on-campus machine the requester controls** (already on the internal
  `10.x` net and able to reach the cluster Argo/`:6443`, like the internal workstation in the firewall
  probe) — advertise the cluster route, run Tailscale on bloom-dev, done; **no cluster-admin needed**.
  Subnet-router mode keeps the real cluster IP so the Argo/k8s TLS cert still matches. Caveats: that
  machine must stay up/connected (single point of failure — PoC-grade, not prod), Tailscale gives
  network reachability only (still need the `bloom-pipeline` SA token for Argo submission), and it's a
  VPN bypass of a security boundary so loop in ITS even temporarily. (A pure *pipeline-execution* PoC
  needs no Tailscale at all — submit directly from that internal machine.)
- **R4 — firewall pending:** if ITS grants the rule, drop Tailscale (no app change).

## 13. Out of scope (v1)

- Event-driven auto-on-ingest (this is manual/request-first, EPIC #11).
- Cancel semantics (retry = resubmit, idempotent; cancel is a later add).
- Slack/email notifications (Realtime status is v1; channel TBD, roadmap #18).
- Experiment-level `analyze` trigger (deps B2).
- Multi-GPU sharding beyond RunAI's own scheduling (batching already enables it).

## 14. Validation

- Idempotency: same envelope twice → 1 source, no dup traits (RPC already covers).
- Dedup: re-run an already-done experiment → 0 GPU pods, run `complete`, all `reused`.
- Resume: kill the predict pod mid-batch → resumes, re-does only the tail (one reload).
- Retry-then-isolate: inject a poison scan → run ends `partial`, others succeed.
- Concurrency: submit > quota batches → excess pending in RunAI/Argo, none dropped.
- End-to-end: a reference scan set (shared with the A3-predict parity gate) → results + status in UI.
