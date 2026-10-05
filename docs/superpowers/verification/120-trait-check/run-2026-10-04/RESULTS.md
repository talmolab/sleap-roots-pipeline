# #120 part 1 trait check: results (run 2026-10-04)

**Verdict: FAIL** under the frozen gate (`../gate_spec.json`, owner-approved before the run).
**Wheat passes** all 5 traits. **Sorghum misses on two counts.** There were no selective
re-runs and no adjustments.

**Owner decision (2026-10-04): the sorghum miss is accepted, so the link may proceed for both
species.** The gate and its result are unchanged; this is an accepted exception, not a looser
tolerance. The reasons on record:

1. **The missing envelope (`scan_7704274`) is not evidence against the sorghum models.** The
   tube is empty. Both the old and the new models found no roots, and the trait-extractor then
   crashes on any species' empty scan. The cause is sleap-nn predict writing 0 labeled frames
   where classic SLEAP wrote 72 empty ones, and `Pipeline.compute_plant_traits` popping
   `plant_name` from an empty frame. It is filed as
   [sleap-roots#280](https://github.com/talmolab/sleap-roots/issues/280) and is not a link gate.
   The gate rule "a missing envelope fails the species" was written to catch model failures and
   caught this instead.
2. **The angle miss (`primary_angle_proximal_median`, ρ 0.832) comes from 2 of 22 scans.** The
   other 20 agree within 3.1° (17 within 0.6°), the median per-scan error is 0, and the other 10
   sorghum traits pass with ρ ≥ 0.997. Not investigated: why scans 7728682 and 7703698 differ.

## Setup

- **Images, by digest, run locally** (A5000 GPU for predict, no run id, no cluster, no Bloom):
  - predict `ghcr.io/talmolab/sleap-roots-predict@sha256:d45c971e…` (revision `79939ee`), with
    `SRP_WANDB_MODEL_ALIAS=candidate`;
  - traits `ghcr.io/talmolab/sleap-roots-trait-extractor@sha256:ba5693fc…` (revision `e45b6bf`).
- **When:** after predict#51 passed (3/3, closed 2026-10-05 UTC). `79939ee..origin/main` in
  sleap-roots-predict changes nothing under `sleap_roots_predict/`, the Dockerfile,
  `pyproject.toml` or `uv.lock`, so the deployed image is the one under test.
- **Input:** a local scratch tree of the 49 scans in `../selected_scans.csv`, plus the synthetic
  wheat past-window copy `scan_10211216_pw17` (age 17, not in the gate). Built by
  `../build_scratch_tree.py` and `../add_wheat_past_window.py`. Sidecar params come from
  `resolve_params(row, overrides={"mode": "cylinder"})`.
- **Reference:** each run's `sleap_roots_traits_output/traits_summary.csv` on Z:. Those runs
  used classic SLEAP inference and sleap-roots 0.1.3 (EDPIE, diversity screen) or 0.1.4
  (SbTx430).

## Run outcome

- **predict:** `Batch complete: 50 ok, 0 skipped, 0 failed`, exit 0.
- **traits:** `49 succeeded, 0 skipped, 1 failed`, exit 3. The failure is
  `FAIL scan_7704274: 'plant_name'`.

## Gate (pooled per species; `gate_results.md` is the script's output)

| species | trait | n | ρ | median rel Δ | result |
|---|---|---|---|---|---|
| wheat | `crown_count_median` | 24 | 0.989 | 0.000 | PASS |
| wheat | `crown_lengths_mean_median` | 24 | 0.995 | 0.000 | PASS |
| wheat | `crown_angles_proximal_mean_median` | 24 | 0.995 | 0.000 | PASS |
| wheat | `crown_angles_distal_mean_median` | 24 | 0.986 | 0.000 | PASS |
| wheat | `network_length_median` | 24 | 0.997 | 0.002 | PASS |
| sorghum | `primary_length_median` | 22 | 0.997 | 0.000 | PASS |
| sorghum | `lateral_count_median` | 24 | 1.000 | 0.000 | PASS |
| sorghum | `lateral_lengths_mean_median` | 19 | 1.000 | 0.000 | PASS |
| sorghum | `primary_angle_proximal_median` | 22 | **0.832** | 0.000 | **FAIL** (ρ < 0.9) |
| sorghum | `lateral_angles_proximal_mean_median` | 17 | 1.000 | 0.000 | PASS |
| sorghum | `network_length_median` | 24 | 0.997 | 0.000 | PASS |

A median relative Δ of 0.000 means more than half the scans fall within the trait's absolute
tolerance.

### Sorghum miss 1: `scan_7704274` has no result envelope

- Diversity screen, day 10, wave 2.
- **Predict:** both new models found 0 instances on all 72 frames (`frames=0 | instances=0`)
  for primary and lateral.
- **Reference:** almost empty too: `primary_length_median` NaN, `network_length_median` 0,
  `lateral_count_median` 1. It looks like an empty tube.
- **Traits:** raised `KeyError: 'plant_name'` instead of emitting NaN traits. In production,
  such a scan fails at traits rather than writing NaNs. That is a trait-extractor robustness
  gap, separate from the models.
- **Scoring:** the gate rule makes a missing envelope a species fail. In the per-trait rows,
  that scan counts as missing on both sides.

### Sorghum miss 2: `primary_angle_proximal_median`, ρ = 0.832

Per-age ρ (information only): d5 0.50, d10 0.95, d17 0.90. 20 of the 22 finite pairs agree
within 3.1° (17 within 0.6°). The outliers:

| scan | age | new | ref | \|Δ\| |
|---|---|---|---|---|
| 7728682 | 5 | 7.03° | 40.06° | 33.0° |
| 7703698 | 10 | 14.69° | 26.47° | 11.8° |
| 9495756 | 5 | NaN | 0.36° | one-sided NaN |

## Also confirmed

- **Predict root types:** wheat crown only (25/25 scans). Sorghum primary + lateral (25/25).
  The model ids are the `candidate` `v0` cards.
- **Traits pipeline:**
  - The envelopes' trait-name fingerprint matches: wheat has 900 traits, crown only, so
    OlderMonocot; sorghum has 1,035, primary + lateral, so Dicot.
  - `choose_pipeline` inside the deployed traits image gives wheat 5/11/14/17 →
    OlderMonocotPipeline (17 clamped to 14) and sorghum 5/10/17 → DicotPipeline (17 clamped
    to 14).
  - Capitalised `Wheat` / `Sorghum` raise `No pipeline matches`, which confirms the casing trap.
- **Real age in the envelopes:** `provenance.params.values.age` equals the sidecar age for all
  49 envelopes (`../check_run.py`). For the selected scans, that is `plant_age_days`.
- **Past-window, both logs:**
  - wheat `scan_10211216_pw17 … age=17 matched as age=14 -> OlderMonocotPipeline`;
  - sorghum, all 5 SbTx430 day-17 scans, `age=17 matched as age=14 -> DicotPipeline`.
- **Provenance:** contract `0.1.0a9`, `predict_code_sha` `79939ee`, `traits_code_sha`
  `e45b6bf`, both container digests set, `pipeline_run_id` null.

## Notes

- **Re-run of the comparison script only:** the first `compare_traits.py` run crashed printing
  its report (the Windows cp1252 console can't encode `Δ`) before writing any result. It was
  re-run once with `PYTHONIOENCODING=utf-8`, with no code or input change. No container was
  re-run.
- **`predict.filtered.log`** is predict's log without urllib3/DEBUG lines and per-frame path
  lists. `traits.log` is complete.
