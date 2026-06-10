# sleap-roots ↔ Bloom integration — Roadmap

**Program:** event-driven, per-scan phenotyping at Bloom ingestion time, with traceable
write-back. Built **tier by tier** (one OpenSpec PR per tier) per the
`roadmap-driven-pipeline` workflow. This file is the canonical roadmap; the **Notion "Bloom
Project Roadmap → sleap-roots-pipeline integration"** project is the shared tracker.

**Design docs:** vault `C:\vaults\sleap-roots\bloom-pipeline-integration\` (program README +
#1 design + #1 plan); copies of the #1 docs also in `sleap-roots-contracts/docs/`.

**Last status sweep:** 2026-06-10.

## Goal

> A scan is ingested into Bloom (local server) → triggers a **per-scan** Argo workflow (Argo
> stays) → `predict` (rebuilt on sleap-nn, warm GPU worker) → `traits` → results written back
> into Bloom with full provenance + blob pointers (S3 + Box), traceably and idempotently → a
> notification fires. Params default from the scan's Bloom dataset metadata but stay
> overridable. `analyze` runs at the **experiment** level, on request. Each repo ships its own
> Dockerfile + GHCR CI (services) / PyPI (libraries), OpenSpec, the canonical Claude commands,
> and is built TDD.

## Hard constraints

- **Bloom DB safety** — schema changes via Supabase migrations only (reversible, no destructive
  ops on prod); writes go through a sanctioned, idempotent **service-role RPC**, never ad-hoc
  SQL or direct table writes (cyl trait tables keep SELECT-only RLS); develop against a local
  Supabase instance.
- **Argo stays** — orchestration remains declarative YAML.
- **Cross-language contract** — Python producers, TypeScript/Postgres consumer; the
  `sleap-roots-contracts` JSON Schema is the interchange artifact; hashes are producer-side only
  (Bloom treats them as opaque).
- **Warm predict worker + stateless traits jobs** — avoid per-scan model reload.

## Tiers

Each tier = one OpenSpec PR in its repo, validated against the stated target. Status:
✅ done · 🔵 in progress · ⬜ not started.

### Track A — per-scan Bloom pipeline

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **A1 — result+provenance contract** | sleap-roots-contracts | Pydantic models + JSON Schema artifact + trait registry | — | schema drift guard green; round-trip/hash/idempotency tests; published to PyPI | ✅ **PR #1 merged; v0.1.0a0 released 2026-06-08** |
| **A2 — Bloom schema + write-back + CLI** | bloom (GitLab) | jsonb provenance on `cyl_trait_sources` + `idempotency_key` UNIQUE; `source_id` FK on trait tables; intermediates/blob table; idempotent service-role write-back RPC; `bloom cyl` ingest CLI; consume contract schema; Box backfill | A1 | same envelope twice → 1 source row, no dup traits; direct table write rejected, RPC succeeds; migration up/down; types-match-contract CI | ⬜ **Not started** |
| **A3 — predict + training rebuild on sleap-nn** | sleap-roots-predict, -training | Rewrite on the current sleap-nn API; warm GPU predict worker; GHCR images | A1 | prediction parity vs current pipeline on a reference scan set (within tolerance); CI + GHCR | ⬜ **Not started** |
| **A4 — event-driven orchestration** | sleap-roots-pipeline | Argo Events: scan ingest → per-scan workflow → predict(warm) → traits → write-back → notification; experiment-level `analyze` trigger | A1, A2, A3 | end-to-end on a reference scan; idempotent re-delivery; notification fires | ⬜ **Not started** |

### Track B — analyze / analysis-input contract

| Tier | Repo | Goal | Depends on | Validation target | Status |
|---|---|---|---|---|---|
| **B1 — analysis-input contract capability** | sleap-roots-contracts | Canonical analyze CSV schema + validator (`validate_analysis_input`) | A1 | golden-file validation; schema published in the same artifact | 🔵 **issue #3 / PR #4 open (egao28)** |
| **B2 — analyze consumes the contract** | sleap-roots-analyze | Wire `validate_analysis_input` into `run-all` / loaders | B1 | run-all rejects malformed input per contract; reproducibility gates (determinism double-run + result round-trip, analyze #133) | ⬜ **issue #144 open** |

### Cross-cutting

| Item | Scope | Status |
|---|---|---|
| **Canonical dev-command set** | all lab repos | ✅ defined + in `scaffolding-lab-python-repo` skill |
| **Command alignment — contracts (#2)** | sleap-roots-contracts | ✅ closed |
| **Command alignment — analyze (#126)** | sleap-roots-analyze | ✅ closed |
| **Command alignment — sleap-roots (#223)** | sleap-roots | 🔵 PR #228 open |
| **This roadmap** | sleap-roots-pipeline/docs | 🔵 created 2026-06-10 |

## Sequencing

A1 ✅ unblocks **A2, A3, B1** (parallelizable). **A4** needs A2+A3. **B2** needs B1.
Recommended next: **A2 (Bloom write-back)** — prompt drafted; consumes the released contract.
A3 can run in parallel (different people/repos).

## Close-the-loop checklist (run after each tier merges)

1. Tick the tier's row (status + PR link). 2. Write a dated status update + sync to the Notion
tracker. 3. Write the next tier's handoff prompt. 4. Park follow-up findings as issue drafts.

## Out of scope

The `sleap-roots` **circumnutation** tier program (Tiers 0–3b) is a **separate** roadmap-driven
pipeline — not part of this integration. Do not fold it in.

---

### Status log

- **2026-06-10** — Roadmap created. A1 done + released (v0.1.0a0). B1 in progress (contracts
  PR #4). Command alignment: contracts/analyze closed, sleap-roots PR #228 open. A2/A3/A4/B2 not
  started. Next: A2 (Bloom write-back) handoff ready.
