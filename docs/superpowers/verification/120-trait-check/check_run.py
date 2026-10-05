#!/usr/bin/env python3
"""#120 part 1 "also confirm" checks, read from the run's outputs and logs.

- predict selected crown only for wheat, and primary + lateral for sorghum (the `.slp`
  artifacts in each `{scan_key}.predictions.json`);
- traits picked OlderMonocotPipeline for wheat and DicotPipeline for sorghum. The envelope
  doesn't name the pipeline and only clamped scans log it, so this checks each envelope's
  trait-name fingerprint (crown_* only vs primary_* + lateral_*);
- every envelope's `provenance.params.values.age` is the sidecar's age (the real age for the
  selected scans);
- one past-window case per species is matched at 14, in both logs.

Usage:  python check_run.py --scratch <scratch>     (expects input/, pred/, traits/,
        predict.log, traits.log). Exit 0 all hold, 2 otherwise. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_TYPES = {"wheat": {"crown"}, "sorghum": {"primary", "lateral"}}
PIPELINE = {"wheat": "OlderMonocotPipeline", "sorghum": "DicotPipeline"}
WINDOW_MAX = 14
FINGERPRINT = ("crown_count", "primary_length", "lateral_count")
FINGERPRINT_OF = {
    "OlderMonocotPipeline": {"crown_count"},
    "DicotPipeline": {"primary_length", "lateral_count"},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scratch", required=True, type=Path)
    args = ap.parse_args()
    s = args.scratch
    problems: list[str] = []

    sidecars = {
        p.parent.name: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((s / "input").glob("*/*.scan_metadata.json"))
    }
    plog = (s / "predict.log").read_text(encoding="utf-8", errors="replace")
    tlog = (s / "traits.log").read_text(encoding="utf-8", errors="replace")

    root_types_seen: dict[str, set] = {}
    trait_counts: dict[str, set] = {}
    for key, sc in sidecars.items():
        species, age = sc["params"]["species"], sc["params"]["age"]

        man = s / "pred" / key / f"{key}.predictions.json"
        if not man.is_file():
            problems.append(f"{key}: no predictions.json")
            continue
        slps = sorted(p.name for p in (s / "pred" / key).glob("*.slp"))
        rts = {m.group(1) for n in slps if (m := re.search(r"\.root([a-z]+)\.slp$", n))}
        root_types_seen.setdefault(species, set()).update(rts)
        if rts != ROOT_TYPES[species]:
            problems.append(f"{key}: predict root types {sorted(rts)}")

        env_path = s / "traits" / f"{key}.result.json"
        if not env_path.is_file():
            problems.append(f"{key}: no result envelope")
            continue
        env = json.loads(env_path.read_text(encoding="utf-8"))
        env_age = env["provenance"]["params"]["values"]["age"]
        if env_age != age:
            problems.append(f"{key}: envelope age {env_age} != sidecar age {age}")

        # The envelope doesn't name the pipeline, so check its trait-name fingerprint.
        names = {t["name"] for t in env["traits"]}
        trait_counts.setdefault(species, set()).add(len(names))
        has = {m: f"{m}_median" in names for m in FINGERPRINT}
        want = {m: m in FINGERPRINT_OF[PIPELINE[species]] for m in FINGERPRINT}
        if has != want:
            problems.append(f"{key}: trait names don't fit {PIPELINE[species]}: {has}")

        if age > WINDOW_MAX:
            want = f"age={age} matched as age={WINDOW_MAX}"
            for name, log in (("predict", plog), ("traits", tlog)):
                hit = [ln for ln in log.splitlines() if "past-window age:" in ln and key in ln]
                if not any(want in ln for ln in hit):
                    problems.append(f"{key}: no '{want}' past-window line in {name}.log")

    print(
        f"scans: {len(sidecars)}; predict root types by species: "
        f"{ {k: sorted(v) for k, v in root_types_seen.items()} }; envelope trait counts: "
        f"{ {k: sorted(v) for k, v in trait_counts.items()} }"
    )
    for p in problems:
        print("PROBLEM:", p)
    print("all checks hold" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
