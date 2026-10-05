#!/usr/bin/env python3
"""Build the #120 part 1 scratch input tree from `selected_scans.csv`, in bloomctl's layout.

For each selected scan this writes `<out>/scan_<id>/{1..72}.jpg` (copied from Z:, which is
only read) and `<out>/scan_<id>/scan_<id>.scan_metadata.json`, the same shape bloomctl's
`download_for_predict.build_sidecar` writes:

- `params` comes from `resolve_params(<scans.csv row>, overrides={"mode": "cylinder"})`, the
  exact call bloomctl makes on the `cyl_scans_extended` row. That is what turns the past runs'
  `species_name` "Wheat"/"Sorghum" into `wheat`/`sorghum`.
- `images_checksum` is sha256 over the frame bytes in frame-number order (bloomctl's
  `compute_checksum`), built through contracts' `InputRef`.
- `image_ids` are placeholders (`local-<scan_id>-<frame>`): the past runs predate Bloom's
  `cyl_images` ids. Neither container interprets them.

No run manifest is written, so both containers discover every sidecar in the tree.

Usage:
    uv run --no-project --with sleap-roots-contracts==0.1.0a9 python build_scratch_tree.py \
        --out <scratch>/input [--z-root Z:/users/eberrigan]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

from sleap_roots_contracts import InputRef, resolve_params

HERE = Path(__file__).parent
EXPECTED_SPECIES = {"wheat", "sorghum"}
FRAMES_PER_SCAN = 72


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--z-root", default="Z:/users/eberrigan")
    args = ap.parse_args()

    out = args.out.resolve()
    z_root = Path(args.z_root).resolve()
    if out == z_root or z_root in out.parents or "a4_poc" in out.parts:
        print(f"refusing to write under {out}", file=sys.stderr)
        return 1

    with (HERE / "selected_scans.csv").open(newline="") as f:
        selected = list(csv.DictReader(f))

    scans_rows: dict[str, dict[str, dict]] = {}
    for sel in selected:
        run_dir = z_root / sel["run"]
        if sel["run"] not in scans_rows:
            with (run_dir / "images_downloader_output" / "scans.csv").open(newline="") as f:
                scans_rows[sel["run"]] = {r["scan_id"]: r for r in csv.DictReader(f)}
        row = scans_rows[sel["run"]][sel["scan_id"]]

        params = resolve_params(row, overrides={"mode": "cylinder"}).values
        # The species/mode the containers will match exactly, and the real age.
        assert params["species"] == sel["species"] in EXPECTED_SPECIES, params
        assert params["mode"] == "cylinder", params
        assert params["age"] == int(row["plant_age_days"]), params

        src = run_dir / row["scan_path"].removeprefix("./")
        frames = [src / f"{i}.jpg" for i in range(1, FRAMES_PER_SCAN + 1)]
        missing = [p.name for p in frames if not p.is_file()]
        if missing:
            print(f"scan {sel['scan_id']}: missing frames {missing}", file=sys.stderr)
            return 1

        key = f"scan_{sel['scan_id']}"
        dst = out / key
        dst.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        for p in frames:
            target = dst / p.name
            shutil.copyfile(p, target)
            digest.update(target.read_bytes())

        input_ref = InputRef(
            image_ids=[f"local-{sel['scan_id']}-{i}" for i in range(1, FRAMES_PER_SCAN + 1)],
            images_checksum=f"sha256:{digest.hexdigest()}",
        )
        sidecar = {"scan_key": key, "params": params, **input_ref.model_dump()}
        (dst / f"{key}.scan_metadata.json").write_text(json.dumps(sidecar), encoding="utf-8")
        print(f"{key}\t{params}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
