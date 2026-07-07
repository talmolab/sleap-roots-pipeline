# sleap-roots ↔ Bloom integration — Roadmap

**Source of truth (scoped).** This roadmap is canonical for **program scope, tier sequencing,
and cross-repo dependencies**. **Bloom EPIC #9 + the PR bodies are canonical for Bloom-side
implementation detail and change lettering.** When they disagree on *scope/sequencing*, this
roadmap wins; on *Bloom impl detail*, EPIC #9 / the PR wins. **Reconcile owner:** eberrigan,
after each change merges (close-the-loop step 3). The Notion "Bloom Project Roadmap →
sleap-roots-pipeline integration" project mirrors this file.

**Program:** event-driven, per-scan phenotyping at Bloom ingestion time, with traceable
write-back. **Vocabulary:** a **tier** is decomposed into **changes**; **one OpenSpec PR per
change** (per repo). Built tier-by-tier per the `roadmap-driven-pipeline` workflow.

**Design docs:** vault `C:\vaults\sleap-roots\bloom-pipeline-integration\` (A1 design + plan);
copies in `sleap-roots-contracts/docs/`.

**Last sweep:** 2026-07-06. **Adversarial roadmap reviews:** 2026-06-10 + 2026-07-06 (4 lenses
each, verified against live repo/PR state; reconciliation logs at the bottom). Run under the
`roadmap-driven-pipeline` skill's roadmap-review gate.

## Goal

> A scan is ingested into Bloom (local server) → triggers a **per-scan** Argo workflow (Argo
> stays) → `predict` (rebuilt on sleap-nn, warm GPU worker) → `traits` (emits `ResultEnvelope`)
> → results written back into Bloom with full provenance + blob pointers (S3 + Box), traceably
> and idempotently → a notification fires. Params default from the scan's Bloom dataset metadata
> but stay overridable. `analyze` runs at the **experiment** level, on request. Each repo ships
> its own Dockerfile + GHCR CI (services) / PyPI (libraries), OpenSpec, the canonical Claude
> commands, and is built TDD.

## Progress — merged PRs (links)

The shared contract is released to PyPI and now sits at **`v0.1.0a3`** (chain
a0→a1→a2→a3, see the version-pinning constraint); Bloom pins it with a drift-CI gate. **Contract
(A1/B1):**

- **A1 — result + provenance contract** — [talmolab/sleap-roots-contracts #1](https://github.com/talmolab/sleap-roots-contracts/pull/1) ✅ (`v0.1.0a0`)
- **B1 — analysis-input contract** — [talmolab/sleap-roots-contracts #4](https://github.com/talmolab/sleap-roots-contracts/pull/4) ✅ (`v0.1.0a1`)

**A2 (salk-bloom write path):**

- **consume-pin** — pin contract + codegen TS + drift CI — [bloom #304](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/304) ✅
- **change A** — `cyl_trait_sources` provenance + idempotency — [bloom #290](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/290) ✅
- **change C** — `cyl_scan_intermediates` blob table (re-pin `v0.1.0a2`) — [bloom #357](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/357) ✅
- **changes D+E** — write-back RPC + RLS lockdown (co-landed) — [bloom #371](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/371) ✅
- **read-path** — source-aware `get_scan_traits` + latest-source view — [bloom #373](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/373) ✅ (OpenSpec archive [#376](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/376) still open)

**A3 (producers):**

- **A3-predict** — inference core [predict #6](https://github.com/talmolab/sleap-roots-predict/pull/6) · warm worker + model-mgmt [#9](https://github.com/talmolab/sleap-roots-predict/pull/9) · output contract [#16](https://github.com/talmolab/sleap-roots-predict/pull/16) · default→live registry [#17](https://github.com/talmolab/sleap-roots-predict/pull/17) ✅ (parity gate still open)
- **A3-training** — seed production model registry (`v0.1.0a3` `ModelCard`) — [training #4](https://github.com/talmolab/sleap-roots-training/pull/4) ✅ (archive [#5](https://github.com/talmolab/sleap-roots-training/pull/5))

> **OpenSpec-archive note:** early archive PRs #300 (change A) and #318 (consume-pin) were **closed
> unmerged** — the actual archiving was done by batch PR [#319](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/319) (merged 2026-06-23,
> archived 8 deployed changes). Later changes archived individually (#369 for C, #372 for D+E);
> read-path's archive #376 is still open.

Cross-linked (Track B — analyze/bloom-mcp): [bloom #310](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/310) ✅ · [bloom #339](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/339) (open).

> Note: bare `#NNN` elsewhere in this file are issues/PRs in **`salk-bloom`** (the bloom repo),
> not this repo — they don't auto-link from here.

## Hard constraints

- **Bloom DB safety** — schema changes via Supabase migrations only (forward-only + manual
  rollback under `supabase/rollbacks/`); **all** writes go through the sanctioned, idempotent
  **service-role RPC** (change D); **D and E co-land in the same migration/deploy** — never
  D-without-E (legacy `authenticated` INSERT still open → forgery hole) and never E-without-D
  (no write path → write-back broken). Develop/test against a **local Supabase** instance; zero
  prod connection strings in CI.
- **Contract version pinning** — the cross-language seam is the most failure-prone part: every
  consumer **pins an explicit `sleap-roots-contracts` version** (per-`$id` `vX.Y`). Bumping it
  is a tracked event that re-pins all consumers. **Head = `v0.1.0a3`** (published 2026-07-04, on
  PyPI). Cut `v0.1.0` once a consumer round-trips the shape end-to-end — **currently blocked by the
  a2↔a3 seam skew below**.
  - **Re-pin ledger** (each is a *tracked event*): **a0** (2026-06-08, initial `result_envelope`) →
    **a1** (2026-06-11, adds `analysis_input`; `result_envelope` unchanged) → **a2** (2026-06-29,
    **real revision**: `BlobRef.kind` narrowed to `predictions_slp` + required `root_type` — change
    C) → **a3** (2026-07-04, **real revision**: adds `ModelCard` + `Provenance.predict_inference_config`
    — A3-predict/training).
  - **Schema `$id` carries the package version**, so a re-pin **re-stamps every schema's `$id`** —
    including *unchanged* ones like `result_envelope` (`…/v0.1.0a0/…` → `…/a3/…`, no payload change).
    **Decision: consumers regenerate and accept an `$id`-only change as a structural no-op.** ⚠️ This
    no-op rule applies **only to schemas whose payload didn't change** — a2 and a3 were *genuine
    payload revisions*, not `$id`-only, and each forced consumers to re-pin.
  - **✅ Seam skew resolved (2026-07-06): the write-back RPC now accepts `0.1.0a3`.** The A3 producers
    emit `a3`; D's RPC previously gated `a2`. Fixed by **[bloom #399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399)** (closes salk-bloom #393): re-pinned the cyl contract to a3 + a
    **prefix-tolerant** `contract_version` match. Envelopes now round-trip once the ingest CLI (#397) lands.
- **Argo stays** — orchestration remains declarative YAML.
- **Warm predict worker + stateless traits jobs** — avoid per-scan model reload.

## Tracking-issue policy (hybrid, just-in-time)

- **One tracking issue/EPIC per tier** (the row links to it).
- **Per-change sub-issues created at tier-decomposition time** (not all upfront); each PR
  references + closes its sub-issue. A2 is decomposed, so its sub-issues are filed: #294
  (consume-pin), #295 (B), #296 (C), #297 (E), #298 (read-path) in `salk-bloom`; D/CLI/backfill
  stay in #13's checklist (just-in-time when reached).
- Every PR links to (a) its tracking issue and (b) the roadmap tier/change it advances.

## Repos

| Role | Repo | Host / flow |
|---|---|---|
| Contract (A1, B1) | `sleap-roots-contracts` | GitHub talmolab; PyPI; PR → main |
| **Bloom (A2, A4-trigger)** | `salk-bloom` = `Salk-harnessing-plants-initiative/bloom` | GitHub; **staging-first** (`staging` → `main`; EPIC #16 staging/prod CI ✅ **closed/landed**) |
| predict (A3) | `sleap-roots-predict` | GitHub talmolab; GHCR; fetches models from the wandb registry **in-process** (consolidates the legacy `models-downloader`) |
| **traits producer (A3)** | `sleap-roots` (traits lib) | GitHub talmolab; GHCR (trait-extractor — **port + redo of GitLab `salk-tm/sleap-roots-traits`**) |
| training (A3) | `sleap-roots-training` | GitHub **talmolab** (scaffolded under talmolab in A0; old `eberrigan` repo archival pending) |
| Orchestration (A4) | `sleap-roots-pipeline` | GitHub talmolab; Argo YAML |
| Analyze (B2, cross-linked) | `sleap-roots-analyze` | GitHub talmolab |

## Tiers

Status: ✅ done · 🔵 in progress · ⬜ not started.

### A0 — tooling baseline (NEW; the Goal promises it, nothing tracked it)

Bring the service repos to the standard: OpenSpec + canonical Claude commands + Dockerfile/GHCR
(services) and transfer `sleap-roots-training` to talmolab. Per-repo OpenSpec changes.

| Repo | Need | Validation target | Status |
|---|---|---|---|
| sleap-roots-predict | openspec init, canonical commands, Dockerfile, GHCR CI | `openspec validate` passes; commands present; GHCR image builds | 🔵 **Tooling merged** ([PR #4](https://github.com/talmolab/sleap-roots-predict/pull/4): openspec + 18 commands + Dockerfile + `docker-build.yml`). ⚠️ **GHCR build FAILING on `main`** (post-merge `docker-build.yml` run red 2026-06-30) — fix before ✅ (tracked: [predict #5](https://github.com/talmolab/sleap-roots-predict/issues/5)). |
| sleap-roots (traits) | already has openspec/.claude; baseline commands | commands present; `openspec` present | ✅ **commands** ([#249](https://github.com/talmolab/sleap-roots/pull/249) merged, closes #223). The GHCR **trait-extractor image is reclassified to A3-traits** (port + redo of GitLab `salk-tm/sleap-roots-traits` — the image today's Argo templates pull) — NOT a quick A0 add. |
| sleap-roots-training | transfer to talmolab; openspec + commands | repo under talmolab; openspec validates | ✅ **scaffolded under talmolab via the initial transfer commit** (openspec + canonical commands + CI); the `standardize-dev-commands` audit `fix-formatting` fix landed as **[PR #2](https://github.com/talmolab/sleap-roots-training/pull/2)** (merged 2026-06-30 — a single-file `fix-formatting.md` fix, *not* the scaffold; there is no PR #1). (Old `eberrigan` repo archival pending — not A0.) |
| sleap-roots-pipeline | openspec init + canonical commands | `openspec validate` passes | ✅ **PR #4 merged 2026-06-30** (openspec + 9 canonical commands; + RunAI skill + `talmo-lab` manifest fix) |

### Track A — per-scan Bloom pipeline

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **A1 — result+provenance contract** | sleap-roots-contracts | Pydantic models + JSON Schema artifact + trait registry | — | drift guard green; round-trip/hash/idempotency tests; on PyPI (shipped **`v0.1.0a0`**; contract has since advanced to **`v0.1.0a3`**) | ✅ **PR #1 merged 2026-06-06; `v0.1.0a0` released 2026-06-08** |
| **A2 — Bloom schema + write-back + CLI** | salk-bloom | provenance/idempotency schema; FK; blob table; idempotent service-role RPC; RLS lockdown; read-path; `bloom cyl` CLI; consume; Box backfill | **A1 @ v0.1.0a2 (pinned; re-pinned a1→a2 at change C — RPC validates a2)**; EPIC #16 ✅ (staging landed) | same envelope twice → 1 source row, no dup traits; direct write rejected, RPC succeeds; migration up/down; types-match-contract CI | 🔵 **In progress — consume-pin ✅ (#304) + change A ✅ (#290) + change C ✅ (#357) + changes D+E ✅ (#371); read-path ✅ ([#373](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/373) merged 2026-07-01; OpenSpec archive #376 still open). Remaining: `bloom cyl` CLI (critical path — A4 write-back rides it; [bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)) → Box backfill; **D re-pin ✅ ([bloom #399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399), closes #393 — RPC accepts a3)**; change B (#295) deferred (no image traits)** |
| **A3 — producers (predict / traits / training / params)** | predict, sleap-roots, training | see sub-table | A0 (predict GHCR [#5](https://github.com/talmolab/sleap-roots-predict/issues/5) still red); **A1 @ ≥ v0.1.0a2** (needs `BlobRef.root_type`; emitter's pin must reconcile with D's RPC gate — [#393](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/393)) | per sub-row | 🔵 **In progress — predict warm-worker/output-contract/registry-flip landed (#6/#9/#16/#17), training registry-seed landed (#4); **A3-params ✅ merged** ([predict #18](https://github.com/talmolab/sleap-roots-predict/pull/18), 2026-07-06 — Bloom metadata → `ResolvedParams`, age units confirmed days); **A3-traits emitter ✅ merged** ([sleap-roots #254](https://github.com/talmolab/sleap-roots/pull/254), 2026-07-06, closes #250); A3-predict parity gate unset** |
| **A4 — scan-level orchestration** | sleap-roots-pipeline | Per-scan Argo workflow: **images-downloader (Option A: bloomcli `--scan_id` stage-in **via the Supabase Storage API on 443** — MinIO:9000 is cluster-unreachable) → predict(warm) → traits (emit `ResultEnvelope`) → write-back **via bloomcli → the `insert_cyl_result_envelope` RPC** (with a scoped Supabase credential) → notification**. **Trigger = Bloom submits Workflow CRDs to the cluster k8s API (`:6443`, `argo` Kubernetes mode — NOT the Argo Server `:8888`, which is in-cluster-only)** (manual-first, EPIC #11; event-driven auto-on-ingest is a later phase — NOT Argo-Events ingress for v1). **⚠️ Connectivity (verified 2026-07-01 on the actual hosts):** control plane `bloom-dev → cluster:6443` is **firewall-blocked** → needs **one firewall rule** (draft: vault `a4-firewall-request.md`); data plane `cluster → bloom.salk.edu:443` **works** (confirmed from a cluster pod — no firewall; stage-in + write-back ride public HTTPS + a scoped Supabase credential). **Use hostname `bloom.salk.edu` (TLS/SNI), not `bloom-dev`.** **Storage = shared file storage mounted across the GPU nodes** (corrected 2026-07-06 — *not* node-local hostPath as earlier assumed): producers stay filesystem-only, but staged images + predictions are **durable and node-independent**, so stage handoff and crash/preemption **resume** survive a pod reschedule. (`cyl_pipeline_runs` table + trigger direction under active redesign — see the A4 request-driven-trigger design.) (Experiment-level `analyze` trigger is a later change, deps B2.) | A0, A2, A3 | end-to-end on a reference scan; idempotent re-delivery (D's `idempotency_key`); notification on success **and** failure | 🔵 **In progress — compute-path PoC ✅ green** (2026-07-07, wf `4m2zg`/`b7x7t`, [PR #23](https://github.com/talmolab/sleap-roots-pipeline/pull/23)): predict→traits→`ResultEnvelope 0.1.0a3` / 918 traits on a reference scan (**compute path only — no write-back yet**). Remaining = real stage-in + write-back + notify + the Bloom trigger; unblock = **1 firewall rule** (`bloom-dev`→cluster `:6443`) + **1 scoped Supabase credential** (design settled 2026-07-01; connectivity verified 2026-07-01) |

#### A2 change breakdown (consume-pin ✅ + A ✅ + C ✅ + D ✅ + E ✅ + read-path ✅ + **D re-pin ✅ (#399)**; B deferred; CLI + backfill remain)

| Change | What | Tracking | Status |
|---|---|---|---|
| **consume (pin)** | pinned `sleap-roots-contracts` **`v0.1.0a1`** (vendored under `contracts/` + `pin.json`); codegen TS (`json-schema-to-typescript` exact `15.0.4`) + byte-equal drift guard; **migration-matches-schema CI** (asserts `cyl_trait_sources.metadata` jsonb + `idempotency_key` text + UNIQUE/CHECK by `contype`; contract-side `contract_version` required + `idempotency_key.default == ""`). *Precedes A* — A's types-match-contract CI depends on it. **On any re-pin, `result_envelope`'s `$id` re-stamps with no content change → regenerate and accept the `$id`-only diff (structural no-op)** (see version-pinning constraint). **Codegen caveat:** json2ts drops `BlobRef.kind`/`scan_key`/enum (anyOf-over-properties) → **change C validates blobs against the schema directly** | #294 | ✅ **merged #304 (2026-06-16)**; OpenSpec `pin-sleap-roots-contract` → live spec `contract-pinning`, archived via batch **#319** (individual archive PR #318 was closed unmerged, superseded) |
| **A** | `cyl_trait_sources`: jsonb `metadata` (opaque Provenance) + `idempotency_key` UNIQUE + **non-empty CHECK** (empty string would satisfy UNIQUE once then collide, silently merging unrelated envelopes); manual rollback; regenerated TS types. **Do NOT add the `idempotency_key = metadata->>'idempotency_key'` CHECK here** (breaks nullable + opaque-jsonb) | EPIC #9 → **#12**; OpenSpec `add-cyl-trait-source-provenance` | ✅ **merged #290 (2026-06-11)** (TDD 10/10); archived via batch **#319** (individual archive PR #300 was closed unmerged, superseded) |
| **B** | `source_id` FK on `cyl_image_traits` (`cyl_scan_traits` **already has it**) → traceable to its run | #295 | ⬜ |
| **C** | ✅ **Done.** Per-scan intermediates/blob table `cyl_scan_intermediates` (`source_id→cyl_trait_sources, scan_id→cyl_scans, kind, root_type, s3_location, box_link, checksum, file_size`). **One row per `.slp` per root type per scan**; **dual pointer** (`s3_location` = Bloom MinIO canonical + `box_link` = human share; `checksum`/`file_size` tie them + detect partial uploads); at-least-one-location CHECK; `UNIQUE(source_id, scan_id, kind, root_type)`; role RLS (admin/agent/user + writer=ingest). **Contract revised + re-pinned `v0.1.0a2`** (contracts #5): `BlobRef.kind`={predictions_slp} (dropped `h5`/`labels`/`qc_image`); **added required `root_type`**={primary,lateral,crown}; `traits_csv` dropped (trait numbers → `cyl_scan_traits`, not blobs); `viewer_html` deferred. MinIO-upload of each blob (originally sketched as "change/flow step G"; today rclone→Box only) is **not a standalone A2 change** — it lands in **A4's write-back path** (see the A4 change breakdown, `write-back` row). Analyze outputs (`sleap-roots-analyze-output/`) are PER-EXPERIMENT → separate change (#28), NOT C. | #296 | ✅ **#357 merged 2026-06-30 (squash `1a89bb0`), archived #369** |
| **D** | idempotent **service-role write-back RPC** `insert_cyl_result_envelope(jsonb)` (SECURITY DEFINER, owned by `postgres`): validate `contract_version` `v0.1.0a2` / non-empty `idempotency_key` / envelope `scan_key` consistency; resolve scan via `inputs.image_ids → cyl_images.scan_id` (exactly one; gate-before-resolve); **first-writer-wins source gate** (`ON CONFLICT (idempotency_key) DO NOTHING`) → re-delivery = **pure no-op**; trait rows via the `cyl_traits` registry (auto-register `trait_id`), finite-or-null values; blob rows; intra-envelope duplicates rejected. `idempotency_key == metadata->>'idempotency_key'` holds by construction (RPC writes both from one field). | EPIC #9 → **#13** | ✅ **#371 merged 2026-06-30 (`8010357`), archived #372** |
| **E** | RLS lockdown — make the RPC the **sole writer**: DROP legacy `authenticated` INSERT on `cyl_trait_sources`/`cyl_scan_traits` **and** `bloom_writer` INSERT/UPDATE policies on all three tables (scope beyond #297's text). `bloom_writer` → SELECT-only there + EXECUTE on the RPC; `bloom_admin` keeps break-glass; Bloom Desktop scan/image writes untouched. **Co-landed with D in one migration.** | #297 | ✅ **#371 (co-landed with D)** |
| **read-path** | update `get_scan_traits` RPC + `cyl_scan_trait_names` view for the `source_id` dimension + latest-source selection (reprocessing mints new sources → reads must disambiguate) | #298 | ✅ **#373 merged 2026-07-01 (squash `03c4d02`)** — ⚠️ OpenSpec **archive PR #376 still OPEN** (close-the-loop step 7 pending). Shared substrate view `cyl_scan_traits_source` (`is_latest = max(source_id)/scan`) + `cyl_scan_traits_latest`; 4-arg `get_scan_traits(experiment_id_, trait_name_, source_id_, run_id_)` = latest-default / pin-source / group-by-run; capability spec `cyl-trait-read`. Follow-up: repoint source-blind readers (`cyl_trait_by_experiment_wave` double-counts) → salk-bloom #374. |
| **D re-pin** | bump the `insert_cyl_result_envelope` RPC's `contract_version` gate a2→a3 + re-vendor the contract. | **[#393](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/393)** | ✅ **[bloom #399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399)** (2026-07-06, closes #393): re-pinned cyl contract to a3 + **prefix-tolerant** `contract_version` match → RPC now accepts `0.1.0a3`. |
| **CLI** | `bloomctl` ingest command writing a `ResultEnvelope` via D (**critical path — A4's write-back rides this**). *New Python `bloomctl` (pkg at `bloomcli/src/bloomctl/`) already has `login` + `download` (`--scan-id`/`--experiment-id`); no ingest path yet.* | **[salk-bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)** (+ non-interactive auth [#398](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/398)) | ⬜ |
| **backfill** | push Box-resident results via D. **Needs a defined key-derivation for provenance-incomplete legacy results** (missing `code_sha`/`container_digest`/`images_checksum`) or a distinct legacy key scheme, else collisions silently drop/conflate | **[#19](https://github.com/talmolab/sleap-roots-pipeline/issues/19)** (design decision; old EPIC #13 closed) | ⬜ |

#### A3 producer change breakdown

> **Tracking:** A3 EPIC = [#9](https://github.com/talmolab/sleap-roots-pipeline/issues/9) (this repo,
> cross-repo tracker); sub-issues [#11](https://github.com/talmolab/sleap-roots-pipeline/issues/11)
> (predict), [#12](https://github.com/talmolab/sleap-roots-pipeline/issues/12) (traits — critical path),
> [#13](https://github.com/talmolab/sleap-roots-pipeline/issues/13) (training),
> [#14](https://github.com/talmolab/sleap-roots-pipeline/issues/14) (params) +
> [#15](https://github.com/talmolab/sleap-roots-pipeline/issues/15) (parity decision). Filed 2026-07-06.

| Change | Repo | Validation target | Tracking | Status |
|---|---|---|---|---|
| A3-predict | sleap-roots-predict | sleap-nn rewrite + warm GPU worker; prediction parity vs current pipeline within **defined tolerance** (e.g. keypoint RMSE ≤ N px / trait-summary deltas ≤ X% on a reference scan set — *set the number*) | [#9](https://github.com/talmolab/sleap-roots-pipeline/issues/9) → **[#11](https://github.com/talmolab/sleap-roots-pipeline/issues/11)**; parity [#15](https://github.com/talmolab/sleap-roots-pipeline/issues/15) | 🔵 inference core (predict #6) + warm worker & wandb **model-management** (predict #9) landed — models fetched from the registry in-process, `models-downloader` consolidated in; **registry now seeded** (13 production models live, predict's `pytest -m wandb` green against them); **default source flipped to the live registry** ([predict #17](https://github.com/talmolab/sleap-roots-predict/pull/17), closes predict #11 + #12): with only `WANDB_API_KEY` set, `WandbRegistrySource()` / `WarmModelWorker(source=None)` fetch the production models out-of-the-box (registry defaults to `sleap-roots-models`; env vars model-scoped to `SRP_WANDB_MODEL_REGISTRY`/`SRP_WANDB_MODEL_ALIAS`; one malformed artifact skips-with-warning; fail-loud on missing key, no offline fallback); **parity gate still open** (set tolerance + ref scans); **output contract landed** ([predict #16](https://github.com/talmolab/sleap-roots-predict/pull/16): the `prediction-output` capability — named per-root `.slp` + a combined `{scan}.predictions.json` manifest carrying predict-side provenance + per-`.slp` checksum/size) → the **predict→traits handoff format is now defined**, unblocking A3-traits' input (traits loads each `.slp` via `Series.load` with the manifest's explicit paths and assembles `Provenance`/`BlobRef` from the sidecar). Manifest schema is **predict-local for now** (reuses `ModelRef`); promote to `sleap-roots-contracts` when A3-traits consumes it. **Container CLI + GHCR image ✅ shipped — [predict #27](https://github.com/talmolab/sleap-roots-predict/pull/27)** (merged 2026-07-07, closes [predict #24](https://github.com/talmolab/sleap-roots-predict/issues/24); OpenSpec `predict-container` capability promoted to specs; 3× adversarial `/review-openspec` + a 5-subagent `/review-pr`): a warm-batch entrypoint `sleap-roots-predict <in_scan_dir> <out_dir>` / `python -m sleap_roots_predict` (`run_batch`) — discovers scans (a `{scan_key}.scan_metadata.json` sidecar co-located with frames), loads models **once**, per scan skip-if-done (existence-based resume) → predict → writes `out/{scan_key}/{scan}.predictions.json` + per-root `.slp`, and **copies the sidecar forward** so predict's output is a self-contained trait-extractor input tree (**D1**). Real exec-form **`linux_cuda`** Dockerfile ENTRYPOINT baking `SRP_PREDICT_CODE_SHA` → non-empty `predict_code_sha` (the §7 requirement's predict half — symmetric to traits `SRT_TRAITS_CODE_SHA`); image `ghcr.io/talmolab/sleap-roots-predict`, tags `latest` (tracks main) + immutable `sha-<gitsha>` (`type=sha,format=long`). Fail-loud on a missing input mount vs. no-op on empty. **parity gate still open**. Follow-ups: [predict #25](https://github.com/talmolab/sleap-roots-predict/issues/25) model-derived channels (plates = color), [predict #26](https://github.com/talmolab/sleap-roots-predict/issues/26) Argo-readiness (exit-code vs `retryStrategy` / empty-input / SIGTERM + atomic-write + checksum-verified skip, symmetric with [sleap-roots #259](https://github.com/talmolab/sleap-roots/issues/259)) |
| A3-traits | sleap-roots | **Port + redo the trait-extractor.** The existing one lives at **GitLab `salk-tm/sleap-roots-traits`** (`registry.gitlab.com/salk-tm/sleap-roots-traits:latest`, pulled by the current Argo `trait-extractor` template) → port to `talmolab/sleap-roots` as a **reference** and rebuild to **consume the A1 contract + emit `ResultEnvelope`** (provenance + traits + blobs) + publish a **GHCR** image. Container stays **filesystem-only** (confirmed — predict/traits read local paths, no boto3/fsspec); inputs are staged in by A4's images-downloader, not read from S3. | [#9](https://github.com/talmolab/sleap-roots-pipeline/issues/9) → **[#12](https://github.com/talmolab/sleap-roots-pipeline/issues/12)** ≡ [sleap-roots #250](https://github.com/talmolab/sleap-roots/issues/250); **critical path** | ✅ **Merged — [sleap-roots #254](https://github.com/talmolab/sleap-roots/pull/254)** (2026-07-06, closes #250; branch `add-traits-extractor-service`; +3060/−5, 42 files; real TDD 66✓ + full suite 1552✓ on 3 OSes; 3× adversarial OpenSpec review + a 5-subagent PR review; OpenSpec archived in [#255](https://github.com/talmolab/sleap-roots/pull/255)). New `trait_extractor/` service pkg (excluded from wheel): consumes predict's `{scan}.predictions.json` + a new `ScanMetadata` sidecar → `choose_pipeline` → scan-grain traits → emits per-scan `ResultEnvelope` JSON (`contract_version` bare `0.1.0a3`; contracts is dev/test-only, AST-guarded). **→ A4's traits step is now unblocked; only the GHCR image + the write-back wiring remain.** **Fast-follows:** GHCR image ✅ **shipped — [sleap-roots #257](https://github.com/talmolab/sleap-roots/pull/257)** (merged main `bb2199c`): image `ghcr.io/talmolab/sleap-roots-trait-extractor`, tags `latest` (tracks main) + immutable `sha-<gitsha>` (e.g. `sha-bb2199c`), `@sha256:` digest in the build run summary; ENTRYPOINT `python -m trait_extractor <in> <out>`; **bakes `SRT_TRAITS_CODE_SHA` → non-empty `traits_code_sha`** (the §7 requirement landed). Argo template — **wired in A4 plan 2** (`args` rewritten to the two dirs + pinned `sha-bb2199c`); still remains: **write-back** + driver Argo-readiness ([sleap-roots #259](https://github.com/talmolab/sleap-roots/issues/259): exit-code vs retryStrategy, empty-input, SIGTERM). MinIO/Box upload + write-back RPC call + `BlobRef` locations; multi-plant grain [#252](https://github.com/talmolab/sleap-roots/issues/252). Cross-repo deps: bloom #393 ✅ (D re-pin done — [#399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399), RPC accepts a3), [contracts #14](https://github.com/talmolab/sleap-roots-contracts/issues/14) (contract_version byte + PipelineCard), [#251](https://github.com/talmolab/sleap-roots/issues/251)/[#253](https://github.com/talmolab/sleap-roots/issues/253). |
| A3-training | sleap-roots-training | rebuild on sleap-nn; feeds model registry | [#9](https://github.com/talmolab/sleap-roots-pipeline/issues/9) → **[#13](https://github.com/talmolab/sleap-roots-pipeline/issues/13)**; [training #4](https://github.com/talmolab/sleap-roots-training/pull/4) ✅ / plate [training #3](https://github.com/talmolab/sleap-roots-training/issues/3) | 🔵 **feeds-registry half done** — [`seed-production-model-registry`](https://github.com/talmolab/sleap-roots-training/pull/4) merged (archive [#5](https://github.com/talmolab/sleap-roots-training/pull/5)); 13 legacy production models seeded to `eberrigan-…/sleap-roots-models` (canary-first; predict's `pytest -m wandb` green). **Native sleap-nn rebuild still pending** (same `ModelCard` contract carries native weights later); plate models deferred ([training #3](https://github.com/talmolab/sleap-roots-training/issues/3)). |
| A3-params | sleap-roots-predict | Bloom dataset metadata → `ResolvedParams`; oracle: given metadata X → expected params; user override wins. **Oracle case defined:** a `cyl_scans_extended` row `{species_name: "Pennycress", plant_age_days: 14}` → `{species: pennycress, mode: cylinder, age: 14}` | [#9](https://github.com/talmolab/sleap-roots-pipeline/issues/9) → **[#14](https://github.com/talmolab/sleap-roots-pipeline/issues/14)**; [predict #18](https://github.com/talmolab/sleap-roots-predict/pull/18) ✅ | ✅ **Merged — [predict #18](https://github.com/talmolab/sleap-roots-predict/pull/18) (2026-07-06; OpenSpec change archived, `param-resolution` capability promoted to specs).** Pure `resolve_params(metadata, overrides=None)` in sleap-roots-predict (new `param-resolution` OpenSpec capability): `species_name`→species (lowercase passthrough; registry stays the authority — unmodelled species zero-match/skip, no whitelist), `mode` via a one-line `_mode_for_scan` seam (`"cylinder"`; GraviScan/multiscanner deferred), `plant_age_days`→age (**confirmed days** vs the 13 seeded cards' `age_min`/`age_max`, windows 2–14). Override-wins per field (keys ⊆ `{species, mode, age}`, values canonicalized so `param_hash` is representation-independent); strict fail-loud validation; round-trips `resolve_params → choose_models`. Follow-ups: [predict #19](https://github.com/talmolab/sleap-roots-predict/issues/19) GraviScan mode, [#20](https://github.com/talmolab/sleap-roots-predict/issues/20) TS-parity, [#21](https://github.com/talmolab/sleap-roots-predict/issues/21) A4 wire-in, [#22](https://github.com/talmolab/sleap-roots-predict/issues/22) salk-bloom override UX, [#23](https://github.com/talmolab/sleap-roots-predict/issues/23) multiscanner |

#### A4 change breakdown (design settled 2026-07-01; decompose now — past tier-decomposition time)

> A4's design + connectivity are settled, so per the issue policy it's decomposed into changes with
> tracking. **A4 EPIC = [#10](https://github.com/talmolab/sleap-roots-pipeline/issues/10)** (this repo;
> maps to Bloom EPIC #9 → #10/#11/#13). The single external unblock is **1 firewall rule
> ([#16](https://github.com/talmolab/sleap-roots-pipeline/issues/16)) + 1 scoped Supabase credential
> ([#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17))** — both blockers, promoted out of
> the vault draft. The remaining changes are filed as reached. Filed 2026-07-06.

| Change | What | Tracking | Status |
|---|---|---|---|
| **firewall** | open `bloom-dev` → cluster k8s API `:6443` (control plane; submission is `argo` Kubernetes-mode CRDs). Draft: vault `a4-firewall-request.md` | **[#16](https://github.com/talmolab/sleap-roots-pipeline/issues/16)** (Bloom #9→#11) | ⬜ blocker |
| **credential** | provision a **scoped Supabase credential** for the cluster (data plane: stage-in via Storage API + write-back via RPC, over public `bloom.salk.edu:443`) | **[#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17)** (Bloom #9→#10) | ⬜ blocker |
| **images-downloader** | per-scan stage-in. **CLI capability ✅ landed** — `bloomctl download --scan-id` writes `scans.csv` + images in the predict-container layout (bloomcli #350/#351 merged). Remaining: non-interactive auth (bloom #398) + Argo-stage wiring. | EPIC #9 → #10 | 🔵 (CLI done; wiring + #398 pending) |
| **workflow template** | per-scan Argo `Workflow`/`WorkflowTemplate` (shared cross-node file storage, not hostPath): images-downloader → predict(warm) → traits → write-back → notify | EPIC #9 → #11 | ⬜ |
| **predict wiring** | wire the warm predict worker (A3-predict) into the workflow | EPIC #9 → #11 | 🔵 (container CLI + GHCR image ✅ **shipped** [predict #27](https://github.com/talmolab/sleap-roots-predict/pull/27), closes [#24](https://github.com/talmolab/sleap-roots-predict/issues/24): warm-batch `<image> <in_scan_dir> <out_dir>`, loads once, sidecar copy-through (**D1**), bakes `predict_code_sha`; image `ghcr.io/talmolab/sleap-roots-predict`, tag `sha-<gitsha>`/`latest`). Remaining: **Argo template pin + wiring** — A4 plan Task 8 on `a4-request-driven-pipeline` (`sleap-roots-predictor-template.yaml`: `sha-PENDING` → real `sha-<sha>`, `args: ["<in>", "<out>"]`, add `WANDB_API_KEY`, drop the `models_input` mount); driver Argo-readiness [predict #26](https://github.com/talmolab/sleap-roots-predict/issues/26); **PoC ✅ ran green** 2026-07-07 [PR #23](https://github.com/talmolab/sleap-roots-pipeline/pull/23) — pinned `sha-4a70e599` + `priorityClassName: interactive-preemptible` + env from `genericsecret-wandb-api-key`, predictor green on `gpu-node3`) |
| **traits wiring** | wire A3-traits (emits `ResultEnvelope`) into the workflow | EPIC #9 → #11 | 🔵 (emitter ✅ [#254](https://github.com/talmolab/sleap-roots/pull/254); **GHCR image ✅ shipped** [sleap-roots #257](https://github.com/talmolab/sleap-roots/pull/257) `sha-bb2199c`; **Argo template wired** — A4 plan 2 / OpenSpec `add-per-scan-argo-workflow`: template `args` rewritten to the two dirs + image pinned, `argo lint` clean. Remaining: **write-back** step (D re-pin ✅ #399 — RPC accepts a3; ingest CLI #397) + driver Argo-readiness [#259](https://github.com/talmolab/sleap-roots/issues/259); **PoC ✅ ran green** 2026-07-07 [PR #23](https://github.com/talmolab/sleap-roots-pipeline/pull/23) — emitted `scan_6791737.result.json` = `ResultEnvelope 0.1.0a3`, 918 traits) |
| **write-back** | `bloomctl → insert_cyl_result_envelope` RPC (incl. the MinIO blob upload = old "step G"); idempotent re-delivery via D's `idempotency_key` | [bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397) (ingest CLI) + [#398](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/398) (auth) | ⬜ (D re-pin ✅ #399 — RPC accepts a3; **needs ingest CLI #397**) |
| **notification** | fire on success **and** failure — **channel undefined (set it)** | **[#18](https://github.com/talmolab/sleap-roots-pipeline/issues/18)** | ⬜ |

### Track B — analyze / analysis-input contract  *(cross-linked dependency — owned by the analyze / bloom-mcp effort, not managed here)*

> **See also:** the analyze/bloom-mcp workstream's own roadmap is §11 of the bloom-mcp design spec (vault `docs/superpowers/specs/2026-05-11-metcalf-2026-evelyn-bloom-mcp-design.md`). B1/B2 here = that spec's contracts#3 + analyze#144; the spec also owns the downstream pieces this roadmap delegates (#142, #120, #119, serializable result types #127–130, and the bloom-mcp data-access layer). **Naming bridge:** that spec's "integration sub-project #2" = tier **A2** above — A2 gates the bloom-mcp data-access layer.

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **B1 — analysis-input contract** | sleap-roots-contracts | canonical analyze CSV schema + `validate_analysis_input` (structural-only: fixed canonical role names, opaque traits, no registry/range checks; co-versions A1 in the same package — a B1 release can force A2 to re-pin; prefer per-`$id` pinning) + **packaged examples** (`load_analysis_input_example` accessor, ship in wheel) + **`canonicalize_role_dtypes`** helper (role→string cast; rename stays consumer-side) | A1 | structural validation of canonical role+trait frame; real EDPIE fixtures; drift guard + `--strict` green | ✅ **contracts #3 / PR #4 merged 2026-06-11; released `v0.1.0a1` to PyPI** (validator + accessor + 5 examples + `canonicalize_role_dtypes`; PyPI install verified). Alpha until first consumer (analyze #144) round-trips end-to-end. |
| **B2 — analyze consumes the contract** | sleap-roots-analyze | wire `validate_analysis_input` into `run-all` / loaders — call it on the **canonicalized, trait-subsetted** frame (after `get_trait_columns` drops metadata + role rename to canonical), **not** the raw wide frame. The contract is structural and has no metadata registry, so column exclusion stays in analyze's config (do not duplicate the denylist in the contract). | B1 | run-all rejects malformed input; reproducibility gates (analyze #133 / epic #130 — both now **closed**) | ⬜ **analyze #144** (open) |

### Cross-cutting

| Item | Status |
|---|---|
| Canonical dev-command set (in `scaffolding-lab-python-repo` skill) | ✅ |
| Command alignment — contracts #2 / analyze #126 | ✅ closed |
| Command alignment — sleap-roots #223 ([PR #249](https://github.com/talmolab/sleap-roots/pull/249), supersedes #228) | ✅ merged 2026-06-30 |
| This roadmap | 🔵 created 2026-06-10; last swept + adversarially re-reviewed 2026-07-06 |

## Bloom EPIC #9 mapping

EPIC #9 is the Bloom-side execution tracker; children map to this roadmap:

| EPIC #9 child | Roadmap |
|---|---|
| #10 Infrastructure (storage / RunAI mount) | A4 (infra) |
| #11 Pipeline Trigger | A4 (trigger) |
| #12 Metadata & Provenance | A2 change A |
| #13 Results Sync | A2 changes D / read-path / CLI / backfill |
| #14 Downstream Analysis | B2 (cross-linked) |
| #15 Prediction viewer + status dashboard | **Out of scope** (Bloom UI) — but its Box-link surfacing + trait-queryability overlap A2 read-path / A4, covered there |
| EPIC #16 CI/CD staging/prod | precondition for A2 prod promotion — ✅ **closed/landed** |

## Sequencing

A0 unblocks A3/A4 (the service repos need OpenSpec/commands first). A1 ✅ unblocks A2, A3, B1.
Within A2: **consume-pin ✅ → A ✅ → C ✅ (B deferred, off critical path) → D+E ✅ (co-land) →
read-path ✅ → `bloom cyl` CLI → D re-pin (a2→a3, #393) → backfill**. A4 needs A0 + A2 + A3. B2 needs B1.

**Next (true frontier, as of 2026-07-06):**
1. **A3-traits emitter — ✅ MERGED** ([sleap-roots #254](https://github.com/talmolab/sleap-roots/pull/254),
   merged 2026-07-06, closes #250; OpenSpec archived in [#255](https://github.com/talmolab/sleap-roots/pull/255)):
   the `trait_extractor/` service emitting per-scan `ResultEnvelope` JSON is landed. **Now build its scoped-out
   fast-follows** — the GHCR image (**in progress: sleap-roots [#256](https://github.com/talmolab/sleap-roots/issues/256)
   / OpenSpec `add-trait-extractor-image`**) + the Argo template (this repo, A4 plan 2), and the actual write-back
   RPC call + MinIO/Box blob upload + `BlobRef` locations. Critical path: the whole write-back path and A4 run
   *through* these.
2. **A2 ingest CLI** ([bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)) +
   non-interactive auth ([#398](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/398)) —
   A4's write-back rides these; co-equal priority with A3-traits.
3. **A2 D re-pin — ✅ DONE** ([bloom #399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399), closes #393): the RPC now accepts `0.1.0a3` via a prefix-tolerant `contract_version` match, so envelopes round-trip. (The contract-byte convention lives on in [contracts #14](https://github.com/talmolab/sleap-roots-contracts/issues/14).)
4. **Set the A3-predict parity gate** (tolerance + reference scan set) — the one open item keeping A3-predict 🔵.

Then A4 (needs A0 + A2 + A3), gated operationally on **1 firewall rule (`bloom-dev`→cluster `:6443`) + 1
scoped Supabase credential**.

## Close-the-loop checklist (after each change merges)

1. Tick the roadmap row/change (+ PR link). 2. Dated status update + sync Notion. 3. **Reconcile
the tracking issue(s)** (owner: eberrigan). 4. Write the next change's handoff. 5. Park follow-ups
as issue drafts.
**Pre-merge gate (DB-safety changes):** migrations tested up+down on local Supabase; zero prod
connection strings in CI.

> **Roadmap-review gate — ✅ adopted** (in the `roadmap-driven-pipeline` skill, §"Roadmap changes —
> the review gate" + §"Tracking issues"): when creating/materially revising this roadmap, run an
> adversarial multi-subagent review (factual accuracy vs repo/PR/issue state; dependency/sequencing;
> completeness; scope/consistency/safety) against **live state** before committing, reconcile every
> BLOCKING/IMPORTANT finding literally, record the reconciliation here, then the user-approval gate.
> (This 2026-07-06 sweep was run under that gate.)

## Out of scope

- `sleap-roots` **circumnutation** tiers (0–3b) — a *separate* program (behavior quantification
  on Graviscan time-series, not ingest-time write-back). Also excludes Lin Wang's "Quantifying
  Behavior of Root" / Graviscan motif work.
- **bloom-mcp / bloom_agent** (egao28's Metcalf project) — touches the same trait tables + B2,
  but is its own effort; cross-link only.
- EPIC #9 **#15** prediction-viewer UI (see mapping note).

---

## Review reconciliation (2026-07-06)

2nd adversarial 4-lens review (factual / dependency-sequencing / completeness / scope-consistency-safety),
each lens verified against **live** GitHub state, run under the `roadmap-driven-pipeline` review gate.
Resolutions:
- **Factual — contract version (all 4 lenses, MAJOR):** head is **`v0.1.0a3`**, not a1. Corrected the Progress
  banner, Hard-constraints pinning block (added the a0→a1→a2→a3 ledger; a2/a3 were real revisions), A1 row, and
  A2 "Depends on". ✅
- **Dependency — a2↔a3 write-back seam (BLOCKING):** D's RPC validates `a2`, producers emit `a3` → D rejects
  A3-traits' envelope. Added an **A2 "D re-pin" change** + Hard-constraint note, both citing open blocker
  **#393**; flagged that "cut `v0.1.0`" is gated on it. ✅
- **Sequencing — stale "Next" (BLOCKING):** it pointed at merged change A #290. Rewrote to the true frontier
  (A3-traits → `bloom cyl` CLI → D re-pin #393 → set parity gate); marked B deferred/off-path in the A2 chain;
  promoted A3-traits from parenthetical to primary critical-path build; flagged the CLI as A4's write-back gate. ✅
- **Completeness — decomposition (BLOCKING):** A3 had no EPIC/sub-issues and A4 was a monolithic cell. Added an
  **A4 change sub-table** + a **Tracking column** to A3; **filed the decomposition in this repo** — A3 EPIC
  #9 (→ #11–#15), A4 EPIC #10 (→ #16–#18), A2 backfill #19; promoted the A4 firewall + scoped-credential
  unblock and the backfill key-derivation out of prose into tracked issues. ✅
- **Completeness — stale Progress + A3 status (MAJOR):** rebuilt Progress with the ~7 missing merged PRs; flipped
  the A3 tier ⬜→🔵. ✅
- **Completeness — unset oracles (MAJOR):** flagged the A3-predict parity gate, A3-params oracle case, and A4
  notification channel inline as "set it"; filed the parity-decision issue (#15) + notification issue (#18). ✅
- **Scope/safety — A4 trigger contradiction (MAJOR):** the 2026-07-01 "design settled" entry said "Argo Server
  API"; annotated it as corrected to k8s `:6443` (argo Kubernetes mode), per the same-day connectivity entry. ✅
- **Factual — archive/EPIC state (MAJOR/MINOR):** #300/#318 were closed-unmerged (archiving via batch #319);
  read-path archive #376 still open; EPIC #16/#13 and analyze #130/#133 closed — all corrected. Training PR #2
  re-attributed (1-file audit fix, not the scaffold). ✅
- **Scope — "phantom" `roadmap-driven-pipeline` skill (all 4 lenses) — REJECTED:** the skill **exists** (at
  `C:\vaults\.claude\skills\`, outside the searched paths) and already contains the review gate + issue policy.
  So the roadmap's "pending skill addition" is **done** — un-flagged the gate note; no skill edit needed. ✅
- **Dropped (false positive):** "pipeline 9→10 commands" — 9 `.md` commands + the `openspec/` namespace dir; "9
  canonical commands" is correct.

## Review reconciliation (2026-06-10)

Adversarial 4-lens review. Resolutions:
- **Factual:** contracts #3 = eberrigan / PR #4 = egao28; `v0.1.0a0` marked pre-release. ✅ applied.
- **Version pin (blocking):** pinned-version added to `Depends on` + a hard constraint. ✅
- **consume mis-sequenced (blocking):** consume-pin moved to **first** in A2. ✅
- **No A0 baseline / unnamed traits producer (blocking):** added **A0 tier** + **A3-traits**
  (sleap-roots emits ResultEnvelope). ✅
- **E↔D ordering (blocking, safety):** restated as **co-land**; added to hard constraints. ✅
- **idempotency equality:** **RPC-only (D)** per decision + PR #290 rationale; "do not CHECK in A". ✅
- **Track B ownership / two-master:** Track B **cross-linked**; source-of-truth **narrowed**
  (scope/sequencing here; Bloom impl detail in EPIC #9/PRs); reconcile owner named. ✅
- **#15 viewer:** **out of scope** w/ overlap note. ✅
- **A4 analyze-trigger:** **scoped out** of A4 first cut (later change, deps B2). ✅
- **Vocabulary:** tier → changes → one PR per change; **A3 split** per repo. ✅
- **Oracles/refs:** A3 tolerance to set; A4 notification channel + success/failure oracle; A2
  **read-path** change added; backfill key-derivation noted; EPIC #16 + analyze #130 cross-refs;
  image-grain = scan-only for now; local-Supabase pre-merge gate; #13 sub-issues to file. ✅

### Status log
- **2026-07-07** — **A4 per-scan pipeline — end-to-end compute PoC ✅ GREEN on RunAI.** The full
  predict→traits path ran on the cluster and produced a contract-valid per-scan `ResultEnvelope`.
  Submitted the `add-per-scan-argo-workflow` DAG (branch `a4-request-driven-pipeline`,
  [PR #23](https://github.com/talmolab/sleap-roots-pipeline/pull/23)) via `argo submit` in
  **Kubernetes mode** (the `argo-user` SA kubeconfig — the `runai_run_pipeline.sh` launcher needs
  `ARGO_TOKEN`/the in-cluster Argo Server `:8888`, unusable from an operator box). Workflows
  `sleap-roots-pipeline-4m2zg`/`b7x7t` **Succeeded** in ~2m34s: predictor on a GPU (`gpu-node3`,
  warm sleap-nn, models pulled live from the wandb registry), trait-extractor on CPU. **Acceptance
  gate PASSED:** `scan_6791737.result.json` = `ResultEnvelope` `contract_version 0.1.0a3`,
  `scan_key scan_6791737`, **918 traits**, 72 `image_ids`; provenance `predict_code_sha 4a70e599`
  + `traits_code_sha bb2199c` **both match the pinned images** (provenance chain intact →
  idempotency-key ready). Images: predict `sha-4a70e59978cffbf2b144b5b20cb08f8d12ef633f` (predict
  #27, digest `@sha256:68a0ba12…`), traits `sha-bb2199c`; both GHCR packages **public/pullable**
  (predict image 8.9 GB, ~7 min cold pull, cached after — re-runs start instantly). **Three
  operational fixes landed in [PR #23](https://github.com/talmolab/sleap-roots-pipeline/pull/23)**
  (found during the run): (1) predictor needs `priorityClassName: interactive-preemptible` — the
  20-GPU deserved quota was full (`NonPreemptibleOverQuota`); the `preemptible` *annotation* is
  inert. (2) RunAI-console "Generic secret" credentials **prefix the k8s secret name** →
  `secretKeyRef` must use **`genericsecret-wandb-api-key`** (asset `wandb-api-key`, Project scope) —
  a real input for the A4 scoped-credential [#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17).
  (3) hostPaths point at the verified `a4_poc/` reference-scan tree. **Scope of this PoC = compute
  path only** (predict→traits→`result.json`; **no Bloom write-back**). The PoC sidecar
  (`image_ids`/`images_checksum`) was **hand-authored** — the real stage-in must author it from live
  `cyl_images` + `resolve_params`. **Still deferred (the real A4):** real stage-in (`bloomctl
  download --scan-id` → nested layout + sidecar), write-back ([bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)
  ingest CLI + blob upload), notification ([#18](https://github.com/talmolab/sleap-roots-pipeline/issues/18)),
  the Bloom trigger + scoped `bloom_workflows` credential
  ([#17](https://github.com/talmolab/sleap-roots-pipeline/issues/17)) + firewall
  ([#16](https://github.com/talmolab/sleap-roots-pipeline/issues/16)). Flipped A4 tier ⬜→🔵;
  predict/traits wiring PoC-verified green.
- **2026-07-06** — **A2 D re-pin ✅ (RPC accepts `0.1.0a3`).** [bloom #399](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/399) merged (closes #393): re-pinned the cyl contract to a3 + a **prefix-tolerant** `contract_version` match, so `insert_cyl_result_envelope` now accepts the bare `0.1.0a3` the producers emit. **Resolves the a2↔a3 write-back seam skew** — the A4 write-back path is no longer contract-blocked; it now needs only the **ingest CLI ([bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397))** (+ non-interactive auth #398 for the cluster). Flipped the A2 "D re-pin" change → ✅ and the hard-constraint seam-skew note → resolved.
- **2026-07-06** — **A3-traits GHCR image ✅ SHIPPED + A4 Argo template wired.** [sleap-roots #257](https://github.com/talmolab/sleap-roots/pull/257) merged to `main` (`bb2199c`); build+push green → `ghcr.io/talmolab/sleap-roots-trait-extractor` (`latest` + immutable `sha-<gitsha>`, `@sha256:` digest in the run summary). ENTRYPOINT `python -m trait_extractor <in> <out>`; **bakes `SRT_TRAITS_CODE_SHA`** → non-empty `traits_code_sha` (the design §7 requirement landed). In this repo (A4 plan 2 / OpenSpec `add-per-scan-argo-workflow`, branch `a4-request-driven-pipeline`): rewrote the DAG to warm-predict → traits (dropped models-downloader), the trait-extractor template `args` → the two dirs + pinned `sha-bb2199c` (**not** a drop-in swap — old 4-elem args would break argv), `argo lint` clean via WSL. **Remaining for traits wiring:** the write-back step (gated [bloom #393](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/393) + ingest CLI [#397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)) + driver Argo-readiness ([sleap-roots #259](https://github.com/talmolab/sleap-roots/issues/259): exit-code vs retryStrategy / empty-input / SIGTERM). **Predict image still pending** ([predict #24](https://github.com/talmolab/sleap-roots-predict/issues/24), the warm-batch CLI) before the end-to-end PoC can run.
- **2026-07-06** — **A3-traits emitter ✅ MERGED** ([sleap-roots #254](https://github.com/talmolab/sleap-roots/pull/254), squash-merged to `main` as `e166dca`, closes [#250](https://github.com/talmolab/sleap-roots/issues/250); OpenSpec Stage-3 archive in [#255](https://github.com/talmolab/sleap-roots/pull/255)). CI green on ubuntu/windows/macOS + lint + docs + codecov; a pre-PR **and** a post-PR 5-subagent review were applied (byte-identical LF envelopes cross-OS, duplicate-`scan_key` refusal in `extract_batch`, basename `..` guard, an authoritative wheel/sdist-exclusion build check). **→ A4's traits step is now unblocked; only the GHCR trait-extractor image (+ Dockerfile/Argo template) and the write-back wiring (bloomcli RPC call + blob upload) remain.** Flipped A3-traits 🔵→✅; A4 `traits wiring` now blocked only on the GHCR image fast-follow. **Deferred slices (unchanged):** GHCR image + Dockerfile + Argo template; MinIO/Box upload + write-back RPC call + `BlobRef` locations; multi-plant grain ([#252](https://github.com/talmolab/sleap-roots/issues/252)). **A4 write-back still blocked on [bloom #393](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/393)** (RPC must re-pin to accept bare `0.1.0a3`).
- **2026-07-06** — **A3-traits emitter is in review** ([sleap-roots #254](https://github.com/talmolab/sleap-roots/pull/254), branch `add-traits-extractor-service`; tracked by [sleap-roots #250](https://github.com/talmolab/sleap-roots/issues/250), closes it) — **not "not started."** A full non-draft impl (+3060/−5, 42 files): a new `trait_extractor/` service pkg (excluded from the wheel) consumes predict's `{scan}.predictions.json` manifest + a new `ScanMetadata` sidecar → `choose_pipeline` → scan-grain traits → emits a per-scan `ResultEnvelope` JSON (`contract_version` bare `0.1.0a3`). Ports GitLab `salk-tm/sleap-roots-traits`; real TDD (64✓); 3× adversarial OpenSpec review + a 5-subagent PR review; `sleap-roots-contracts` is dev/test/container-only (CI AST-guarded), not a runtime dep. **Scoped out (fast-follows):** GHCR image + Dockerfile + Argo template; MinIO/Box upload + the write-back RPC call + `BlobRef` locations; multi-plant grain ([#252](https://github.com/talmolab/sleap-roots/issues/252)). **Cross-repo deps:** bloom #393 (D re-pin — A4 write-back blocked on it), [contracts #14](https://github.com/talmolab/sleap-roots-contracts/issues/14) (contract_version byte + PipelineCard), sleap-roots [#251](https://github.com/talmolab/sleap-roots/issues/251)/[#253](https://github.com/talmolab/sleap-roots/issues/253). Flipped A3-traits ⬜→🔵 in review; updated tracker #12. **Revised "Next":** land #254 + its GHCR/Argo/RPC-call fast-follows (supersedes the earlier "build A3-traits" note — it's built, now in review). The contract-side `contract_version` convention issue I'd offered to file already exists as **contracts #14**.
- **2026-07-06** — **A2/A4 CLI grounded against the live bloom repo → 2 issues filed.** The Node CLI is being replaced by a new Python **`bloomctl`** (pkg `bloomcli/src/bloomctl/`, PyPI `bloomctl` `0.1.0a1`; #347/#350/#351/#383, `list` in flight #385). Reading the code corrected two roadmap assumptions: **(1) per-scan stage-in already exists** — `bloomctl download --scan-id` writes `scans.csv` + images in the predict-container layout (not "experiment-level only"), so A4's images-downloader CLI capability is ✅ (wiring + non-interactive auth remain); **(2) auth is interactive user email/password only** (`sign_in_with_password`), no service-credential path. Filed the two real CLI gaps: **[bloom #397](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/397)** — `bloomctl` ResultEnvelope **ingest/write-back** command (A2 CLI / A4 write-back; depends on D re-pin #393) — and **[bloom #398](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/398)** — **non-interactive scoped-credential auth** for the A4 cluster pod (pairs with credential #17). No ingest command or open ingest/CLI issue existed (no duplication). **D re-pin #393 is in flight (owner-side) — left alone.**
- **2026-07-06** — **Adversarial roadmap re-review + reconciliation sweep** (2nd sweep; run under the `roadmap-driven-pipeline` skill's roadmap-review gate — 4 lenses, each verified against live repo/PR state). Reconciled ~25 drift items (see the 2026-07-06 reconciliation section). Headlines: (1) **contract version corrected everywhere a1→a3** with a re-pin ledger (a2/a3 were *real* payload revisions, not `$id`-only no-ops); (2) surfaced the **live a2↔a3 write-back seam skew** — D's RPC gates `v0.1.0a2` but producers emit `a3` → added an **A2 "D re-pin" change** referencing the open blocker **salk-bloom #393**; (3) **Progress section rebuilt** (was ~7 merged PRs stale: A2 C/D+E/read-path, A3 predict/training); (4) **A3 tier flipped ⬜→🔵**; (5) **A3 + A4 decomposed** — added an A4 change sub-table + a Tracking column to A3 (EPIC/sub-issues **to file** — drafts staged); (6) fixed the stale "Next" pointer → true frontier = **A3-traits** (unblocked emitter) + `bloom cyl` CLI + D re-pin + set the parity gate; (7) corrected archive-PR refs (#300/#318 closed-unmerged → batch #319; read-path archive #376 still open), the A4 trigger contradiction (k8s `:6443`, not Argo Server), training PR #2 attribution, closed-EPIC gates (#16/#13/analyze #130/#133), and bumped stale sweep dates. **The roadmap-review-gate + issue-policy "pending skill addition" is un-flagged — both already live in the `roadmap-driven-pipeline` skill** (the "phantom skill" concern was a bad search path: it lives at `C:\vaults\.claude\skills\`). **Decomposition filed (this repo, cross-repo trackers):** A3 EPIC #9 (→ #11 predict / #12 traits / #13 training / #14 params / #15 parity-decision); A4 EPIC #10 (→ #16 firewall / #17 credential / #18 notification); A2 backfill key-derivation #19. **Next: build A3-traits (#12)** — the unblocked critical-path emitter.
- **2026-07-05** — **A3-predict flipped its default model source to the live registry** ([predict #17](https://github.com/talmolab/sleap-roots-predict/pull/17) merged; closes predict #11 + #12). `WandbRegistrySource` now defaults its registry to `sleap-roots-models` and `WarmModelWorker(source=None)` reads the live production registry, so with only `WANDB_API_KEY` set the warm worker fetches the 13 production models **out-of-the-box** — the default source is the registry, not a stub/local source. Env vars **model-scoped** (`SRP_WANDB_REGISTRY`→`SRP_WANDB_MODEL_REGISTRY`, `SRP_WANDB_ALIAS`→`SRP_WANDB_MODEL_ALIAS`; old names unread) to match training's `SLEAP_ROOTS_MODEL_*`. `list_cards()` now **skips a single malformed production artifact with a warning** instead of aborting (predict #12); **fail-loud** on a missing key, no offline fallback. Live `pytest -m wandb` **green** against the registry via the default path (no registry env). Process: `/new-feature` (brainstorm → OpenSpec → real TDD) + 5-agent `/review-openspec` and `/review-pr` (the PR review caught a set-but-empty-env footgun — empty `SRP_WANDB_MODEL_ALIAS` disabled the filter → fixed to fall back to the default). **A3-predict stays 🔵** — the flip + rename landed; the **parity gate** (tolerance + reference scan set) remains the one open A3-predict item. Deferred to later predict slices: predict #7 (provenance-config shape), #14 (checksum-dedupe the warm cache), #13 (wandb version floor), #10 (`sleap_nn_version` mismatch warning). **Resolves the "flip predict's default source to the live registry" action** named in the 2026-07-05 seed entry.
- **2026-07-05** — **Production model registry seeded** ([`seed-production-model-registry`](https://github.com/talmolab/sleap-roots-training/pull/4) merged, archive [#5](https://github.com/talmolab/sleap-roots-training/pull/5)). `sleap-roots-training` now owns a `seed-registry` CLI that publishes the current legacy root models as wandb `type="model"` artifacts with flat `ModelCard` selection metadata + the `production` alias — the exact surface predict's `WandbRegistrySource` reads. **13 production cards** (7 chooser rows over 8 SHA256-pinned models; arabidopsis `plate` deferred → [training #3](https://github.com/talmolab/sleap-roots-training/issues/3)) live in `eberrigan-salk-institute-for-biological-studies` / `sleap-roots-models` under the `production` alias. Seeded **canary-first** (2 representative cards → predict's gated `pytest -m wandb` → the remaining 11 with idempotent skip); producer `--verify` 13/13; **consumer gate green** — `list_cards()` returns the 13 pinned `ModelCard`s and `materialize()` downloads+caches. **No wandb version skew** (both repos resolve wandb 0.28.0, not the feared 0.21.3). Process: `/new-feature` (brainstorm → OpenSpec → TDD), **3 adversarial proposal-review rounds + a 5-agent `/review-pr`** (caught a BLOCKING idempotency-read bug — lazy-paginator abort + swallowed errors → fixed fail-closed). The `model-registry` capability spec now lives in training's `openspec/specs/`. Depends on `sleap-roots-contracts` **0.1.0a3** (`ModelCard`). **Resolves the "seed before predict flips its default source" open item in the 2026-07-04 entry:** A3-training's feeds-registry half is done (🔵; native sleap-nn rebuild still pending), and A3-predict can now flip its default source (still 🔵 — parity gate unset).
- **2026-07-04** — **A3-predict warm model worker + wandb model-management landed** ([predict #9](https://github.com/talmolab/sleap-roots-predict/pull/9) merged). On the rebuilt sleap-nn 0.3.0 inference core (predict #6), adds a pure model-selection matcher (Bloom `species`/`mode`/`age` → model per root type), a pluggable `ModelCardSource` (offline `LocalCardSource` + networked `WandbRegistrySource`), and a `WarmModelWorker` keeping predictors resident across scans (fetch-once/load-once, fail-loud). **`models-downloader` is consolidated into predict** — models are fetched from the wandb registry in-process, so there is **no separate models-downloader stage** in the A4 warm path (`images-downloader → predict(warm) → traits`). Depends on `sleap-roots-contracts` **0.1.0a3** (`ModelCard` + `Provenance.predict_inference_config`, [contracts #10](https://github.com/talmolab/sleap-roots-contracts/pull/10)). Real TDD (no mocks); GHCR image build green; GPU verified locally (the dead self-hosted GPU runner was retired from CI, GPU tests moved to a required local `/pre-merge` step). **Still open:** the production wandb registry is being seeded by `sleap-roots-training` (`seed-production-model-registry`, in flight) before predict flips its default source; the **A3-predict parity gate** (tolerance + reference scan set) is unset — so **A3-predict stays 🔵** (warm-worker + model-management done; parity pending), and A3-training's "feeds model registry" half advances only once the seed merges (native-model feed + sleap-nn rebuild still pending). Deferred to later predict slices: serving protocol/CLI, the `predictions.csv` output contract + `.slp` naming, emitting `Provenance`/`ResultEnvelope`.
- **2026-07-01** — **A4 connectivity verified on the real hosts** (corrects the "reachable both ways" assumption in the design-settled entry below). Probed from `bloom-dev.salk.edu` (Bloom prod, 198.202.68.43, public subnet) and from a cluster pod (`gpu-node10`, ns `runai-talmo-lab`). **Control plane:** bloom-dev → cluster k8s API 10.7.30.173:**6443** **times out (firewall-blocked)** → bloom-dev cannot submit. (Submission is `argo` Kubernetes-mode CRDs to :6443 via the SA kubeconfig; the Argo Server :8888 is unused/in-cluster-only; the submit workstation works only because it's on the internal 10.x LAN.) **Data plane:** cluster → bloom.salk.edu:**443** **works** (cluster pod: `/rest/v1/`→308, `/storage/v1/`→308) — bloom-dev exposes only 443 publicly (Caddy); MinIO/Postgres are Docker-internal. So stage-in (Supabase Storage API) + write-back (bloomcli → RPC) ride public 443 with a **scoped Supabase credential** — no data-plane firewall. Use `bloom.salk.edu` (TLS/SNI), not `bloom-dev`. **Net A4 infra ask = 1 firewall rule (bloom-dev→cluster:6443) + 1 scoped Supabase credential.** Firewall request drafted (vault `a4-firewall-request.md`); recorded in memory + salk-bloom #10/#11.
- **2026-07-01** — **A4 design settled (scan-level orchestration).** **Trigger = Bloom submits per-scan workflows to the Argo Server API** *[⚠️ corrected 2026-07-06: submission is `argo` **Kubernetes-mode** CRDs to the cluster k8s API `:6443` — **NOT** the Argo Server `:8888` (in-cluster-only); see the 2026-07-01 connectivity entry directly above]* (manual-first per EPIC #11; Bloom prod is on the Salk server (`bloom-dev.salk.edu`), MinIO storage; **not** Argo-Events ingress for v1; event-driven auto-on-ingest is a later phase). **No `cyl_pipeline_runs` table for v1** — the write-back RPC already persists `pipeline_run_id` (a **batch key**) + full provenance on `cyl_trait_sources` (`metadata` + `name`), and Argo/RunAI already track run status + queue; a Bloom runs table is only justified for a Bloom-native status/queue/cancel UX (EPIC #15, out of scope) — **resolves the long-open 'Bloom runs table vs Argo' question**. **Input = Option A stage-in**: producers are **filesystem-only** (confirmed — predict/traits read local paths, no boto3/fsspec) and there is **no shared NFS** (Bloom = MinIO/S3), so a per-scan `images-downloader` fetches one scan's frames from MinIO via **bloomcli `--scan_id`** (experiment-level today — filed as an addition, coordinated with @blm3886's in-flight bloomcli PRs salk-bloom #350/#351). **Storage = hostPath** (no dynamic provisioner; only PV is hostPath-backed). Read-path (#298) in review (salk-bloom PR #373).
- **2026-06-30** — **A0 batch: training ✅; sleap-roots commands ✅; predict tooling ✅ but GHCR red.** **training** A0 done ([talmolab/sleap-roots-training #2](https://github.com/talmolab/sleap-roots-training/pull/2) merged — scaffolded under talmolab, 18 canonical commands, `{build,ci,version}.yml`; `standardize-dev-commands` audit, 15/16 KEEP + `fix-formatting` drift fix). **sleap-roots** command standardization merged ([#249](https://github.com/talmolab/sleap-roots/pull/249), closes #223 / supersedes #228) — but its `build.yml` is **PyPI-only**, so the **GHCR trait-extractor image is a separate effort — reclassified to A3-traits** (port + redo of GitLab `salk-tm/sleap-roots-traits`). **predict** A0 tooling merged ([#4](https://github.com/talmolab/sleap-roots-predict/pull/4): openspec + 18 commands + Dockerfile + `docker-build.yml`) — **but the post-merge `docker-build.yml` run on `main` FAILED**, so predict stays 🔵 until the GHCR build is fixed. **A0 remaining: (1) fix predict's GHCR build on `main` ([predict #5](https://github.com/talmolab/sleap-roots-predict/issues/5)). (2) trait-extractor GHCR is NOT a quick A0 add — reclassified to A3-traits (port + redo of GitLab `salk-tm/sleap-roots-traits` → talmolab). sleap-roots A0 baseline (commands) is ✅.** Closed the stale/conflicted partial roadmap PR #6 (this entry + table edits supersede it; committed directly to `main`).
- **2026-06-30** — **A2 changes D + E merged + archived** (`salk-bloom` #371 → `staging`, merge `8010357`; OpenSpec archived via #372). `insert_cyl_result_envelope(jsonb)` — SECURITY DEFINER (owner `postgres`, `rolbypassrls`, pinned `search_path`), single-txn ingest of a `ResultEnvelope`: validates `contract_version` `v0.1.0a2` / non-empty `idempotency_key` / envelope `scan_key` consistency; resolves the scan from `inputs.image_ids → cyl_images.scan_id` (exactly one distinct; **gate-before-resolve**); **first-writer-wins source gate** (`ON CONFLICT (idempotency_key) DO NOTHING`) so re-delivery is a **pure no-op** (immutable provenance); trait rows via the `cyl_traits` registry (auto-register `trait_id`), finite-or-null values (`jsonb_typeof='number'` guard + overflow→NULL); blob rows; intra-envelope duplicates rejected. **E (co-landed, one migration):** dropped legacy `authenticated` INSERT on the two older tables **and** `bloom_writer` INSERT/UPDATE on all three → only the RPC (via its `postgres` owner) + `bloom_admin` write; `bloom_writer` keeps SELECT + EXECUTE on the RPC (Bloom Desktop scan/image writes untouched). Process: two `/review-openspec` rounds + a 5-agent `/review-pr` round (no blockers; hardened gate-before-resolve, value typing, symmetric dup handling, clean error surface). Flipped 3 deferred contract↔DB mappings active in the migration-match CI. **Next: read-path (#298).**
- **2026-06-30** — **A0 `sleap-roots-pipeline` done** ([PR #4](https://github.com/talmolab/sleap-roots-pipeline/pull/4) merged, squash `f0d0c3a`). `openspec init --tools claude` + `project.md` (Argo/RunAI/per-scan orchestration) + 9 canonical Claude commands (Python/test/build commands SKIPPED — declarative-YAML repo). Two adversarial `/review-pr` rounds fixed: stale cluster identifiers `tye-lab`→**`talmo-lab`** in the manifests/README/launcher (canonical per GAPIT + mosquito-cfd), inverted PV/PVC↔hostPath claim, preemptibility-is-`priorityClassName`-not-annotation, and a fabricated GHCR image registry (real = `registry.gitlab.com/salk-tm/...`). Also ported a **RunAI skill** (`.claude/skills/runai/`) from mosquito-cfd. `openspec validate --all --strict` green. A0 remaining repos: predict, traits-GHCR, training-transfer.
- **2026-06-30** — **A2 change C merged + archived** (`salk-bloom` #357 → `staging`, squash `1a89bb0`; OpenSpec archived #369). `cyl_scan_intermediates`: per-scan artifact pointers (one `.slp` per root type), dual pointer (`s3_location` MinIO canonical + `box_link`), `checksum`/`file_size`, at-least-one-location CHECK, strict `kind`/`root_type` CHECKs, `UNIQUE(source_id,scan_id,kind,root_type)`, role RLS (writer=ingest), forward-only migration + manual rollback. **Trait↔blob link = shared `(source_id, scan_id)`** — no `cyl_scan_traits` change. **Contract re-pinned `v0.1.0a2`** (talmolab/sleap-roots-contracts #5): `BlobRef.kind`={predictions_slp} (dropped `h5`/`labels`/`qc_image`), **added required `root_type`**={primary,lateral,crown}; `traits_csv` dropped (numbers → `cyl_scan_traits`), `viewer_html` deferred. `.slp` is per-(scan,root-type), NOT per-frame. **Next: change D** (service-role write-back RPC).
- **2026-06-16** — **Change C / blob-storage design settled** (from the real `/run-cylinder-pipeline`
  Box-upload flow; scope on `salk-bloom` #296). **Per-scan** `BlobRef` (moving off the current
  per-experiment Box folder). **Dual pointer**: `s3_location` = Bloom **MinIO** (canonical, RLS,
  mirrors `plates_blob_path_storage`) **+** `box_link` = human-shareable Box link — both stored,
  `checksum`/`file_size` tie them and detect partial uploads (contract `BlobRef` already supports
  this; no change needed for the dual-pointer). **`kind` enum must be revised** to the real
  artifacts (`predictions_slp` ✓; add `traits_csv`/`viewer_html`; `h5`/`labels`/`qc_image` don't
  match the cylinder pipeline) — that enum lives in `sleap-roots-contracts`, so it's a **contract
  revision + re-pin** (#1 → re-run consume-pin), cheap now (no consumer). Write-back gains a step
  (change **G**): upload each blob to MinIO + record `s3_location` (today only rclone→Box).
  **Decision: `sleap-roots-analyze-output/` (QC/PCA/heritability/plots) is PER-EXPERIMENT → a
  separate change at #28's analyze-side provenance grain, NOT change C** (C is per-scan only).
  Also: OpenSpec backlog reconciled (`salk-bloom` #319 — archived 8 deployed changes, removed 2
  superseded; live specs 2 → 9).
- **2026-06-16** — **A2 consume-pin merged** (`salk-bloom` #304 → `staging`, squash `539763d`;
  OpenSpec archive PR #318 → live spec `contract-pinning`). Pinned **`sleap-roots-contracts
  v0.1.0a1`** (vendored schema + `pin.json` under `contracts/`), codegen TS
  (`json-schema-to-typescript` exact `15.0.4`) + byte-equal **drift guard** + `node --test`, and a
  **migration-matches-schema** pytest (asserts `cyl_trait_sources.metadata` jsonb + `idempotency_key`
  text + UNIQUE/CHECK **by `contype`**, plus contract-side sanity: `contract_version` required,
  `idempotency_key.default == ""`). 3 adversarial review rounds + `/review-pr` (no blockers);
  approved by @blm3886. Unblocked only after a separate staging-wide `langchain` CVE bump (#317).
  **Codegen caveat:** json2ts drops `BlobRef.kind`/`scan_key`/enum (anyOf-over-properties) →
  **change C must validate blobs against the schema directly**, not the generated `BlobRef`.
  **@blm3886 (Benfica) review suggestion — handoff to B/D/A4:** lifecycle/audit columns for an
  eventual scanner-triggered pipeline — `created_at` → audit field for B/D (NB **reconcile** with
  read-path #298's `max(id)` latest-selection + "no created_at" decision; created_at here =
  display/sort, not latest-selection); `created_by_user_id` → **D** caller-attribution (the D3
  hybrid `SECURITY DEFINER` + recorded caller, already on record); `status`
  (pending/running/complete/failed) + `error_code`/`error_message` → **A4 orchestration** / a future
  `cyl_pipeline_runs` reached via `Provenance.pipeline_run_id` (the **superseded**-`pipeline_runs`
  model) — **NOT** on `cyl_trait_sources`. **Open A4 question: whether in-flight run lifecycle
  becomes a Bloom runs table vs. lives in Argo — not currently planned.** Next: change B (#295).
- **2026-06-11** — **A2 change A merged** (`salk-bloom` #290 → `staging`, squash `9b17d31`).
  `cyl_trait_sources` += `metadata jsonb` (opaque Provenance) + `idempotency_key` (UNIQUE +
  non-empty CHECK); 1 run → 1 source row. TDD 10/10 on local Supabase; reviewed by @blm3886
  (migration made re-runnable via `IF NOT EXISTS`/drop-then-add; **D RPC role-model decision
  recorded — leaning `SECURITY DEFINER` + recorded app caller**, settle in D). OpenSpec
  archived (PR #300 → live spec `cyl-trait-writeback`). **Read-path #298 ≡ bloom-mcp
  data-access §4** (shared source-aware RPCs; latest = `max(id)`). Next: consume-pin #294, then change B (#295).
- **2026-06-11** — **B1 released: `sleap-roots-contracts v0.1.0a1`** on PyPI (analysis-input
  contract + validator + `canonicalize_role_dtypes` + packaged examples; `result_envelope`
  unchanged). Recorded the **`$id` re-stamp decision** for A2 consume-pin (#294): a re-pin
  re-stamps every schema's `$id` (version-stamped), so `result_envelope` shows a `$id`-only diff —
  **regenerate and accept the structural no-op**, don't treat it as a contract revision.
- **2026-06-11** — **B1** implementation completed on contracts PR #4 (structural validator +
  `AnalysisInputRow` + emitted schema + real EDPIE fixtures; OpenSpec `--strict` + drift guard +
  117 tests green; pending review/merge). Recorded the **B2 canonicalization precondition**: analyze
  calls `validate_analysis_input` on the canonicalized, trait-subsetted frame (after
  `get_trait_columns`), not the raw wide frame — column exclusion stays in analyze's config (the
  contract is structural, no metadata registry; duplicating analyze's denylist was rejected — it
  would fork a second source of truth and inherit analyze Bug #75's brittleness).
- **2026-06-10** — Roadmap created, corrected (A2 already underway in `salk-bloom`), then
  adversarially reviewed (4 lenses) and reconciled (above). Next: re-commit, reconcile EPIC #9 +
  file A2 sub-issues, add roadmap-review + issue-policy steps to the `roadmap-driven-pipeline`
  skill (via writing-skills).
