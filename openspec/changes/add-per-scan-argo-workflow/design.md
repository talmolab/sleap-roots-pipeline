## Context

Full architecture lives in `docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md`
(approved 2026-07-06). This change implements only its predict→traits execution core in this
declarative repo; everything else in that design is a later, separately-tracked change.

## Key decisions (scoped to this change)

- **Drop models-downloader.** The rebuilt warm predictor (predict #9 `WarmModelWorker`) fetches
  models from the wandb registry **in-process**, so a separate model-staging stage and its two
  volumes are removed. This is the single biggest DAG change.
- **Inter-stage coupling stays mount-based**, per repo convention: `predictor` writes
  `{scan}.predictions.json` + `.slp` to the predictions mount; `trait-extractor` reads that mount
  and writes `{scan}.result.json` to the results mount. No Argo parameters/artifacts.
- **Container contracts (consumed):**
  - predict (#24): `<image> <in_scan_dir> <out_dir>`, env `WANDB_API_KEY`, GPU, filesystem-only.
  - traits (#256): `<image> <in_dir> <out_dir>`, exec-form `ENTRYPOINT ["python","-m","trait_extractor"]`, CPU.
  These are the load-bearing interface; if the producer slices refine them, this change updates to match.
- **Submit path unchanged.** `runai_run_pipeline.sh` registers the templates and `argo submit`s to
  the Argo Server (`gpu-master:8888`) from an internal machine — the no-Tailscale PoC path.
- **Pin producer images by digest/`sha-<sha>`**, never `:latest` (repo convention + the A4 per-run
  reproducibility requirement).

## Out of scope (later changes)

write-back (bloom #393 ✅ RPC accepts a3 / PR #399; ingest CLI bloom #397 remains), automated stage-in (bloomctl), batching/fan-out, Argo
semaphore + RunAI-quota concurrency, cluster-side dedup, resume hardening (atomic writes /
checksum-verified skip / attempt cap), notification, the Bloom request trigger + `pipeline_runs`,
and the Tailscale/push transport.

## Risks

- **Producer interface drift.** The container args/env/output format here is defined ahead of
  predict #24's implementation; reconcile on that slice's merge. Mitigated by keeping the contract
  explicit (proposal + spec scenarios).
- **Image pull auth.** GHCR packages are private on first push (#256 notes this) — the cluster SA
  must be able to pull (public or `imagePullSecret`) before the run succeeds.
