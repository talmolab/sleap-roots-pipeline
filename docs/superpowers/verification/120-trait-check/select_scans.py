#!/usr/bin/env python3
"""Pick the #120 part 1 trait-check scans: a seeded, age-stratified sample from past hpi_dev runs.

The sample is drawn from each run's `images_downloader_output/scans.csv` only. No trait value is
read, so the pick cannot depend on how well the old run did on a scan. A scan is eligible when
its staged frame folder exists with 72 frames and it has a row in that run's reference
`sleap_roots_traits_output/traits_summary.csv` (existence only).

Usage:  python select_scans.py [--z-root Z:/users/eberrigan] > selected_scans.csv
Stdlib only. Read-only on Z:.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

SEED = 120

# (species, run folder, {age: number of scans}). Ages and counts are fixed before any run.
PLAN = [
    ("wheat", "20250328_Charlotte_Rambla_EDPIE_Feb_2025", {5: 8, 11: 8, 14: 8}),
    ("sorghum", "20250204_july_2024_sorghum_diversity_screen", {5: 10, 10: 10}),
    (
        "sorghum",
        "20260105_Kimberly_Echegoyen_Sorghum_T2_SbTx430_Weep_2_08_December_2025",
        {17: 5},
    ),
]

FRAMES_PER_SCAN = 72


_REF_IDS: dict[Path, set[str]] = {}


def eligible(run_dir: Path, rows: list[dict]) -> list[dict]:
    """Return rows whose frames are staged (72 .jpg) and that have a reference row."""
    if run_dir not in _REF_IDS:
        ref = run_dir / "sleap_roots_traits_output" / "traits_summary.csv"
        with ref.open(newline="") as f:
            _REF_IDS[run_dir] = {r["scan_id"] for r in csv.DictReader(f)}
    ref_ids = _REF_IDS[run_dir]
    out = []
    for r in rows:
        frames = run_dir / r["scan_path"].removeprefix("./")
        if (
            r["scan_id"] in ref_ids
            and frames.is_dir()
            and len(list(frames.glob("*.jpg"))) == FRAMES_PER_SCAN
        ):
            out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--z-root", default="Z:/users/eberrigan")
    args = ap.parse_args()

    rng = random.Random(SEED)
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(
        [
            "species",
            "run",
            "scan_id",
            "plant_age_days",
            "wave_number",
            "plant_qr_code",
            "species_name",
            "scan_path",
        ]
    )
    for species, run, ages in PLAN:
        run_dir = Path(args.z_root) / run
        with (run_dir / "images_downloader_output" / "scans.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        for age, n in ages.items():
            pool = sorted(
                (r for r in rows if r["plant_age_days"] == str(age)),
                key=lambda r: int(r["scan_id"]),
            )
            rng.shuffle(pool)
            picked = []
            for r in pool:  # first n eligible in seeded order; ineligible ones are skipped
                if eligible(run_dir, [r]):
                    picked.append(r)
                if len(picked) == n:
                    break
            if len(picked) < n:
                print(f"{run} age {age}: only {len(picked)} eligible, need {n}", file=sys.stderr)
                return 1
            for r in sorted(picked, key=lambda r: int(r["scan_id"])):
                w.writerow(
                    [
                        species,
                        run,
                        r["scan_id"],
                        age,
                        r["wave_number"],
                        r["plant_qr_code"],
                        r["species_name"],
                        r["scan_path"],
                    ]
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
