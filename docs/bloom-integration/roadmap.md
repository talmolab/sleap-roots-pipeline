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

## Hard constraints

- **Bloom DB safety** — schema changes via Supabase migrations only (forward-only + manual
  rollback under `supabase/rollbacks/`); **all** writes go through the sanctioned, idempotent
  **service-role RPC** (change D); **D and E co-land in the same migration/deploy** — never
  D-without-E (legacy `authenticated` INSERT still open → forgery hole) and never E-without-D
  (no write path → write-back broken). Develop/test against a **local Supabase** instance; zero
  prod connection strings in CI.
- **Contract version pinning** — the cross-language seam is the most failure-prone part: every
  consumer **pins an explicit `sleap-roots-contracts` version** (per-`$id` `vX.Y`). Bumping it
  is a tracked event that re-pins all consumers. A1 is currently only `v0.1.0a0` (alpha) — A2's
  consume should pin that explicitly or A1 should cut `v0.1.0` first.
- **Argo stays** — orchestration remains declarative YAML.
- **Warm predict worker + stateless traits jobs** — avoid per-scan model reload.

## Tracking-issue policy (hybrid, just-in-time)

- **One tracking issue/EPIC per tier** (the row links to it).
- **Per-change sub-issues created at tier-decomposition time** (not all upfront); each PR
  references + closes its sub-issue. Since A2 is already decomposed, its B/C/E/read-path/etc.
  sub-issues are **now due** (filed during issue reconciliation).
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
| **A2 — Bloom schema + write-back + CLI** | salk-bloom | provenance/idempotency schema; FK; blob table; idempotent service-role RPC; RLS lockdown; read-path; `bloom cyl` CLI; consume; Box backfill | **A1 @ v0.1.0a0 (pin)**; EPIC #16 (staging) | same envelope twice → 1 source row, no dup traits; direct write rejected, RPC succeeds; migration up/down; types-match-contract CI | 🔵 **In progress — change A (PR #290) open; rest planned** |
| **A3 — producers (predict / traits / training / params)** | predict, sleap-roots, training | see sub-table | A0, **A1 @ pin** | per sub-row | ⬜ Not started |
| **A4 — event-driven orchestration** | sleap-roots-pipeline | Argo Events: scan ingest → per-scan workflow → predict(warm) → traits → write-back → **notification**. (Experiment-level `analyze` trigger is a **later change**, deps B2 — out of A4 first cut.) | A0, A2, A3 | end-to-end on a reference scan; idempotent re-delivery; notification fires on success **and** failure | ⬜ Not started |

#### A2 change breakdown (consume-pin first; A is in flight)

| Change | What | Tracking | Status |
|---|---|---|---|
| **consume (pin)** | pin `sleap-roots-contracts @ v0.1.0a0`; codegen TS; **migration-matches-schema CI**. *Precedes A* — change A's types-match-contract CI depends on it | sub-issue: to file | ⬜ planned (do first) |
| **A** | `cyl_trait_sources`: jsonb `metadata` (opaque Provenance) + `idempotency_key` UNIQUE + **non-empty CHECK** (empty string would satisfy UNIQUE once then collide, silently merging unrelated envelopes); manual rollback; regenerated TS types. **Do NOT add the `idempotency_key = metadata->>'idempotency_key'` CHECK here** (breaks nullable + opaque-jsonb) | EPIC #9 → **#12**; OpenSpec `add-cyl-trait-source-provenance` | 🔵 **PR #290 open** (TDD 9/9) |
| **B** | `source_id` FK on `cyl_scan_traits` (+ `cyl_image_traits`) → traceable to its run | sub-issue: to file | ⬜ |
| **C** | intermediates/blob table (`source_id, scan_id, kind, s3_location, box_link, checksum, file_size`); mirrors `plates_blob_path_storage` | sub-issue: to file | ⬜ |
| **D** | idempotent **service-role write-back RPC**: upsert source on `idempotency_key`; trait rows w/ `source_id`; blob rows; one txn; re-delivery = no-op. **Enforces `idempotency_key == metadata->>'idempotency_key'` in the RPC** (RPC-only — safe because E makes the RPC the sole writer) | EPIC #9 → **#13** | ⬜ |
| **E** | RLS lockdown — DROP legacy `authenticated` INSERT policy on `cyl_trait_sources`/`cyl_scan_traits`. **Co-lands with D** | sub-issue: to file | ⬜ |
| **read-path** | update `get_scan_traits` RPC + `cyl_scan_trait_names` view for the `source_id` dimension + latest-source selection (reprocessing mints new sources → reads must disambiguate) | sub-issue: to file | ⬜ |
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

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **B1 — analysis-input contract** | sleap-roots-contracts | canonical analyze CSV schema + `validate_analysis_input` (co-versions A1 in the same package — a B1 release can force A2 to re-pin; prefer per-`$id` pinning) | A1 | golden-file validation | 🔵 **contracts #3 (eberrigan) / PR #4 (egao28)** |
| **B2 — analyze consumes the contract** | sleap-roots-analyze | wire `validate_analysis_input` into `run-all` / loaders | B1 | run-all rejects malformed input; reproducibility gates (analyze **#133**, under epic **#130**) | ⬜ **analyze #144** |

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
- **2026-06-10** — Roadmap created, corrected (A2 already underway in `salk-bloom`), then
  adversarially reviewed (4 lenses) and reconciled (above). Next: re-commit, reconcile EPIC #9 +
  file A2 sub-issues, add roadmap-review + issue-policy steps to the `roadmap-driven-pipeline`
  skill (via writing-skills).
