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

**Last sweep:** 2026-06-10. **Adversarial roadmap review:** 2026-06-10 (4 lenses; reconciliation
log at the bottom).

## Goal

> A scan is ingested into Bloom (local server) → triggers a **per-scan** Argo workflow (Argo
> stays) → `predict` (rebuilt on sleap-nn, warm GPU worker) → `traits` (emits `ResultEnvelope`)
> → results written back into Bloom with full provenance + blob pointers (S3 + Box), traceably
> and idempotently → a notification fires. Params default from the scan's Bloom dataset metadata
> but stay overridable. `analyze` runs at the **experiment** level, on request. Each repo ships
> its own Dockerfile + GHCR CI (services) / PyPI (libraries), OpenSpec, the canonical Claude
> commands, and is built TDD.

## Progress — merged PRs (links)

The shared contract is released to PyPI (`v0.1.0a1`, A1 + B1) and Bloom is now pulling it with a
drift-CI gate:

- **A1 — result + provenance contract** — [talmolab/sleap-roots-contracts #1](https://github.com/talmolab/sleap-roots-contracts/pull/1) ✅
- **B1 — analysis-input contract** — [talmolab/sleap-roots-contracts #4](https://github.com/talmolab/sleap-roots-contracts/pull/4) ✅
- **A2 change A — `cyl_trait_sources` provenance + idempotency** — [Salk-Harnessing-Plants-Initiative/bloom #290](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/290) ✅
- **A2 consume-pin — pin contract `v0.1.0a1` + codegen TS + drift CI** — [Salk-Harnessing-Plants-Initiative/bloom #304](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/304) ✅

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
  is a tracked event that re-pins all consumers. **`v0.1.0a1` is published** (2026-06-11, on PyPI;
  adds the analysis-input contract; `result_envelope` is unchanged). Cut `v0.1.0` once a consumer
  round-trips the shape end-to-end.
  - **Schema `$id` carries the package version**, so a re-pin **re-stamps every schema's `$id`** —
    including unchanged ones like `result_envelope` (`…/v0.1.0a0/…` → `…/v0.1.0a1/…`, no payload
    change). **Decision: consumers regenerate and accept the `$id`-only change as a structural
    no-op** — not a contract revision. At `a1`, only `analysis_input` is genuinely new.
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
| **Bloom (A2, A4-trigger)** | `salk-bloom` = `Salk-harnessing-plants-initiative/bloom` | GitHub; **staging-first** (`staging` → `main`; gated by EPIC #16) |
| predict (A3) | `sleap-roots-predict` | GitHub talmolab; GHCR |
| **traits producer (A3)** | `sleap-roots` (traits lib) | GitHub talmolab; GHCR (trait-extractor) |
| training (A3) | `sleap-roots-training` | GitHub **eberrigan** (transfer to talmolab in A0) |
| Orchestration (A4) | `sleap-roots-pipeline` | GitHub talmolab; Argo YAML |
| Analyze (B2, cross-linked) | `sleap-roots-analyze` | GitHub talmolab |

## Tiers

Status: ✅ done · 🔵 in progress · ⬜ not started.

### A0 — tooling baseline (NEW; the Goal promises it, nothing tracked it)

Bring the service repos to the standard: OpenSpec + canonical Claude commands + Dockerfile/GHCR
(services) and transfer `sleap-roots-training` to talmolab. Per-repo OpenSpec changes.

| Repo | Need | Validation target | Status |
|---|---|---|---|
| sleap-roots-predict | openspec init, canonical commands, Dockerfile, GHCR CI | `openspec validate` passes; commands present; GHCR image builds | ⬜ |
| sleap-roots (traits) | already has openspec/.claude; add GHCR for trait-extractor if missing | GHCR image builds | ⬜ |
| sleap-roots-training | transfer to talmolab; openspec + commands | repo under talmolab; openspec validates | ⬜ |
| sleap-roots-pipeline | openspec init + canonical commands | `openspec validate` passes | ⬜ |

### Track A — per-scan Bloom pipeline

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **A1 — result+provenance contract** | sleap-roots-contracts | Pydantic models + JSON Schema artifact + trait registry | — | drift guard green; round-trip/hash/idempotency tests; on PyPI (currently **`v0.1.0a0` pre-release**) | ✅ **PR #1 merged 2026-06-06; `v0.1.0a0` released 2026-06-08** |
| **A2 — Bloom schema + write-back + CLI** | salk-bloom | provenance/idempotency schema; FK; blob table; idempotent service-role RPC; RLS lockdown; read-path; `bloom cyl` CLI; consume; Box backfill | **A1 @ v0.1.0a1 (pinned)**; EPIC #16 (staging) | same envelope twice → 1 source row, no dup traits; direct write rejected, RPC succeeds; migration up/down; types-match-contract CI | 🔵 **In progress — change A ✅ (#290) + consume-pin ✅ (#304); change B (#295) next** |
| **A3 — producers (predict / traits / training / params)** | predict, sleap-roots, training | see sub-table | A0, **A1 @ pin** | per sub-row | ⬜ Not started |
| **A4 — event-driven orchestration** | sleap-roots-pipeline | Argo Events: scan ingest → per-scan workflow → predict(warm) → traits → write-back → **notification**. (Experiment-level `analyze` trigger is a **later change**, deps B2 — out of A4 first cut.) | A0, A2, A3 | end-to-end on a reference scan; idempotent re-delivery; notification fires on success **and** failure | ⬜ Not started |

#### A2 change breakdown (consume-pin ✅ + A ✅; B next)

| Change | What | Tracking | Status |
|---|---|---|---|
| **consume (pin)** | pinned `sleap-roots-contracts` **`v0.1.0a1`** (vendored under `contracts/` + `pin.json`); codegen TS (`json-schema-to-typescript` exact `15.0.4`) + byte-equal drift guard; **migration-matches-schema CI** (asserts `cyl_trait_sources.metadata` jsonb + `idempotency_key` text + UNIQUE/CHECK by `contype`; contract-side `contract_version` required + `idempotency_key.default == ""`). *Precedes A* — A's types-match-contract CI depends on it. **On any re-pin, `result_envelope`'s `$id` re-stamps with no content change → regenerate and accept the `$id`-only diff (structural no-op)** (see version-pinning constraint). **Codegen caveat:** json2ts drops `BlobRef.kind`/`scan_key`/enum (anyOf-over-properties) → **change C validates blobs against the schema directly** | #294 | ✅ **merged #304 (2026-06-16)**, archived #318 (OpenSpec `pin-sleap-roots-contract` → live spec `contract-pinning`) |
| **A** | `cyl_trait_sources`: jsonb `metadata` (opaque Provenance) + `idempotency_key` UNIQUE + **non-empty CHECK** (empty string would satisfy UNIQUE once then collide, silently merging unrelated envelopes); manual rollback; regenerated TS types. **Do NOT add the `idempotency_key = metadata->>'idempotency_key'` CHECK here** (breaks nullable + opaque-jsonb) | EPIC #9 → **#12**; OpenSpec `add-cyl-trait-source-provenance` | ✅ **merged #290 (2026-06-11), archived #300** (TDD 10/10) |
| **B** | `source_id` FK on `cyl_image_traits` (`cyl_scan_traits` **already has it**) → traceable to its run | #295 | ⬜ |
| **C** | intermediates/blob table (`source_id, scan_id, kind, s3_location, box_link, checksum, file_size`); mirrors `plates_blob_path_storage`. **Per-scan** `BlobRef` (`scan_key`). **Dual pointer: `s3_location` = Bloom MinIO (canonical) + `box_link` = human share** (both used; `checksum` ties them). **Revise `kind` enum to real artifacts** (`predictions_slp` ✓, add `traits_csv`/`viewer_html`; drop `h5`/`labels`/`qc_image`) → **contract change + re-pin** (#1, not Bloom-only). New flow step (G): write-back also uploads each blob to MinIO + records `s3_location` (today only rclone→Box). **Analyze outputs (`sleap-roots-analyze-output/`) are PER-EXPERIMENT → separate change (#28), NOT C.** Scope on #296. | #296 | ⬜ |
| **D** | idempotent **service-role write-back RPC**: upsert source on `idempotency_key`; trait rows w/ `source_id`; blob rows; one txn; re-delivery = no-op. **Enforces `idempotency_key == metadata->>'idempotency_key'` in the RPC** (RPC-only — safe because E makes the RPC the sole writer) | EPIC #9 → **#13** | ⬜ |
| **E** | RLS lockdown — DROP legacy `authenticated` INSERT policy on `cyl_trait_sources`/`cyl_scan_traits`. **Co-lands with D** | #297 | ⬜ |
| **read-path** | update `get_scan_traits` RPC + `cyl_scan_trait_names` view for the `source_id` dimension + latest-source selection (reprocessing mints new sources → reads must disambiguate) | #298 | ⬜ |
| **CLI** | `bloom cyl` ingest command writing a `ResultEnvelope` via D | EPIC #9 → #13 | ⬜ |
| **backfill** | push Box-resident results via D. **Needs a defined key-derivation for provenance-incomplete legacy results** (missing `code_sha`/`container_digest`/`images_checksum`) or a distinct legacy key scheme, else collisions silently drop/conflate | EPIC #9 → #13 | ⬜ |

#### A3 producer change breakdown

| Change | Repo | Validation target | Status |
|---|---|---|---|
| A3-predict | sleap-roots-predict | sleap-nn rewrite + warm GPU worker; prediction parity vs current pipeline within **defined tolerance** (e.g. keypoint RMSE ≤ N px / trait-summary deltas ≤ X% on a reference scan set — *set the number*) | ⬜ |
| A3-traits | sleap-roots | traits consume A1 contract + **emit `ResultEnvelope`** (provenance + traits + blobs); GHCR image | ⬜ |
| A3-training | sleap-roots-training | rebuild on sleap-nn; feeds model registry | ⬜ |
| A3-params | producer / bloom-client | Bloom dataset metadata → `ResolvedParams`; oracle: given metadata X → expected params; user override wins | ⬜ |

### Track B — analyze / analysis-input contract  *(cross-linked dependency — owned by the analyze / bloom-mcp effort, not managed here)*

> **See also:** the analyze/bloom-mcp workstream's own roadmap is §11 of the bloom-mcp design spec (vault `docs/superpowers/specs/2026-05-11-metcalf-2026-evelyn-bloom-mcp-design.md`). B1/B2 here = that spec's contracts#3 + analyze#144; the spec also owns the downstream pieces this roadmap delegates (#142, #120, #119, serializable result types #127–130, and the bloom-mcp data-access layer). **Naming bridge:** that spec's "integration sub-project #2" = tier **A2** above — A2 gates the bloom-mcp data-access layer.

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **B1 — analysis-input contract** | sleap-roots-contracts | canonical analyze CSV schema + `validate_analysis_input` (structural-only: fixed canonical role names, opaque traits, no registry/range checks; co-versions A1 in the same package — a B1 release can force A2 to re-pin; prefer per-`$id` pinning) + **packaged examples** (`load_analysis_input_example` accessor, ship in wheel) + **`canonicalize_role_dtypes`** helper (role→string cast; rename stays consumer-side) | A1 | structural validation of canonical role+trait frame; real EDPIE fixtures; drift guard + `--strict` green | ✅ **contracts #3 / PR #4 merged 2026-06-11; released `v0.1.0a1` to PyPI** (validator + accessor + 5 examples + `canonicalize_role_dtypes`; PyPI install verified). Alpha until first consumer (analyze #144) round-trips end-to-end. |
| **B2 — analyze consumes the contract** | sleap-roots-analyze | wire `validate_analysis_input` into `run-all` / loaders — call it on the **canonicalized, trait-subsetted** frame (after `get_trait_columns` drops metadata + role rename to canonical), **not** the raw wide frame. The contract is structural and has no metadata registry, so column exclusion stays in analyze's config (do not duplicate the denylist in the contract). | B1 | run-all rejects malformed input; reproducibility gates (analyze **#133**, under epic **#130**) | ⬜ **analyze #144** |

### Cross-cutting

| Item | Status |
|---|---|
| Canonical dev-command set (in `scaffolding-lab-python-repo` skill) | ✅ |
| Command alignment — contracts #2 / analyze #126 | ✅ closed |
| Command alignment — sleap-roots #223 (PR #228) | 🔵 |
| This roadmap | 🔵 created + reviewed 2026-06-10 |

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
| EPIC #16 CI/CD staging/prod | precondition for A2 prod promotion |

## Sequencing

A0 unblocks A3/A4 (the service repos need OpenSpec/commands first). A1 ✅ unblocks A2, A3, B1.
Within A2: **consume-pin → A → (B, C) → D+E (co-land) → read-path → CLI → backfill**. A4 needs
A0 + A2 + A3. B2 needs B1. **Next:** land A2 change A (PR #290) — but file the consume-pin first;
A3 (esp. A3-traits, which the contract needs as the *emitter*) can run in parallel after A0.

## Close-the-loop checklist (after each change merges)

1. Tick the roadmap row/change (+ PR link). 2. Dated status update + sync Notion. 3. **Reconcile
the tracking issue(s)** (owner: eberrigan). 4. Write the next change's handoff. 5. Park follow-ups
as issue drafts.
**Pre-merge gate (DB-safety changes):** migrations tested up+down on local Supabase; zero prod
connection strings in CI.

> **Roadmap-review gate (skill addition, pending):** when creating/materially revising this
> roadmap, run an adversarial multi-subagent review (factual accuracy vs repo/PR/issue state;
> dependency/sequencing; completeness; scope/consistency/safety) before committing.

## Out of scope

- `sleap-roots` **circumnutation** tiers (0–3b) — a *separate* program (behavior quantification
  on Graviscan time-series, not ingest-time write-back). Also excludes Lin Wang's "Quantifying
  Behavior of Root" / Graviscan motif work.
- **bloom-mcp / bloom_agent** (egao28's Metcalf project) — touches the same trait tables + B2,
  but is its own effort; cross-link only.
- EPIC #9 **#15** prediction-viewer UI (see mapping note).

---

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
