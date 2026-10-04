#!/usr/bin/env python3
"""Add the synthetic wheat past-window case to the scratch tree (owner-approved 2026-10-04).

EDPIE has no wheat scan past day 14, the top of wheat's 5-14 window, so no real scan exercises
the clamp. As in the 2026-10-02 scan-1009 local verification, this adds one copy of a selected
day-14 scan (the lowest selected scan_id, 10211216) as `scan_10211216_pw17`, with `params.age`
overridden to 17 through the same `resolve_params` call. Predict and traits must each log
`past-window age: ... age=17 matched as age=14`.

It is not in `selected_scans.csv`, so `compare_traits.py` never reads it: the gate covers real
scans and real ages only.

Usage:
    uv run --no-project --with sleap-roots-contracts==0.1.0a9 python add_wheat_past_window.py \
        --out <scratch>/input [--z-root Z:/users/eberrigan]
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from sleap_roots_contracts import resolve_params

RUN = "20250328_Charlotte_Rambla_EDPIE_Feb_2025"
SCAN_ID = "10211216"
AGE = 17
KEY = f"scan_{SCAN_ID}_pw{AGE}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--z-root", default="Z:/users/eberrigan")
    args = ap.parse_args()

    src = args.out / f"scan_{SCAN_ID}"  # the real scan's copy, built by build_scratch_tree.py
    real = json.loads((src / f"scan_{SCAN_ID}.scan_metadata.json").read_text(encoding="utf-8"))
    with (Path(args.z_root) / RUN / "images_downloader_output" / "scans.csv").open(newline="") as f:
        row = next(r for r in csv.DictReader(f) if r["scan_id"] == SCAN_ID)
    assert row["plant_age_days"] == "14", row["plant_age_days"]

    params = resolve_params(row, overrides={"mode": "cylinder", "age": AGE}).values
    assert params == {"species": "wheat", "mode": "cylinder", "age": AGE}, params

    dst = args.out / KEY
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*.jpg")):
        shutil.copyfile(p, dst / p.name)
    sidecar = {
        "scan_key": KEY,
        "params": params,
        "image_ids": [i.replace(SCAN_ID, f"{SCAN_ID}_pw{AGE}") for i in real["image_ids"]],
        "images_checksum": real["images_checksum"],  # same frame bytes
    }
    (dst / f"{KEY}.scan_metadata.json").write_text(json.dumps(sidecar), encoding="utf-8")
    print(f"{KEY}\t{params}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
