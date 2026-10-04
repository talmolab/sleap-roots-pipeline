#!/usr/bin/env python3
"""#120 part 1 gate: compare the new run's traits with each past run's `traits_summary.csv`.

For every species and every trait in `gate_spec.json` (frozen before the run), pooled over that
species' selected scans:

- **Spearman rho >= 0.9** over the scans where both values are finite (at least 10 such
  scans; an undefined rho, e.g. a constant column, fails).
- **median per-scan error <= 0.10**, where a scan's error is 0 when |new - ref| <= the trait's
  absolute tolerance, and |new - ref| / |ref| otherwise (inf when ref is 0). A value missing on
  one side only is an error of inf; missing on both sides is excluded and reported.

Both thresholds are inclusive. A species passes when every trait passes. Per-age rho is
printed for information only; it does not gate.

Usage (from this folder, after the run):
    python compare_traits.py --traits-dir <scratch>/traits [--z-root Z:/users/eberrigan] \
        [--out results.md]
Exit: 0 all traits pass, 2 at least one trait fails, 1 bad input. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
RHO_MIN = 0.9
REL_MAX = 0.10
MIN_PAIRS = 10


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based), ties sharing the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rho (Pearson on average ranks); NaN when undefined."""
    if len(xs) < 2:
        return math.nan
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return math.nan
    return sxy / math.sqrt(sxx * syy)


def scan_error(new: float, ref: float, atol: float) -> float | None:
    """One scan's error under the gate; None when both values are missing."""
    new_nan, ref_nan = math.isnan(new), math.isnan(ref)
    if new_nan and ref_nan:
        return None
    if new_nan or ref_nan:
        return math.inf
    delta = abs(new - ref)
    if delta <= atol:
        return 0.0
    if ref == 0:
        return math.inf
    return delta / abs(ref)


def evaluate_trait(pairs: list[tuple[float, float]], atol: float) -> dict:
    """Apply the gate to (new, ref) pairs for one trait."""
    errors, finite = [], []
    n_both_nan = n_one_nan = 0
    for new, ref in pairs:
        e = scan_error(new, ref, atol)
        if e is None:
            n_both_nan += 1
            continue
        errors.append(e)
        if math.isnan(new) or math.isnan(ref):
            n_one_nan += 1
        else:
            finite.append((new, ref))
    rho = spearman([n for n, _ in finite], [r for _, r in finite])
    median_err = statistics.median(errors) if errors else math.inf

    reasons = []
    if len(finite) < MIN_PAIRS:
        reasons.append(f"only {len(finite)} finite pairs (< {MIN_PAIRS})")
    if math.isnan(rho) or rho < RHO_MIN:
        reasons.append(f"rho {rho:.3f} < {RHO_MIN}")
    if not median_err <= REL_MAX:
        reasons.append(f"median |rel delta| {median_err:.3f} > {REL_MAX}")
    return {
        "rho": rho,
        "median_err": median_err,
        "n_pairs": len(finite),
        "n_one_nan": n_one_nan,
        "n_both_nan": n_both_nan,
        "passed": not reasons,
        "reason": "; ".join(reasons),
    }


def _finite_rho(pairs: list[tuple[float, float]]) -> float:
    """Spearman rho over the pairs where both values are finite."""
    finite = [(n, r) for n, r in pairs if not (math.isnan(n) or math.isnan(r))]
    return spearman([n for n, _ in finite], [r for _, r in finite])


def _num(v) -> float:
    if v is None or v == "":
        return math.nan
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def load_new_traits(traits_dir: Path) -> dict[str, dict[str, float]]:
    """{scan_id: {trait name: value}} from the trait-extractor's `scan_<id>.result.json`."""
    out = {}
    for p in sorted(Path(traits_dir).glob("scan_*.result.json")):
        scan_id = p.name.removesuffix(".result.json").removeprefix("scan_")
        env = json.loads(p.read_text(encoding="utf-8"))
        out[scan_id] = {t["name"]: _num(t["value"]) for t in env["traits"]}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--traits-dir", required=True, type=Path)
    ap.add_argument("--z-root", default="Z:/users/eberrigan")
    ap.add_argument("--spec", type=Path, default=HERE / "gate_spec.json")
    ap.add_argument("--selected", type=Path, default=HERE / "selected_scans.csv")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    with args.selected.open(newline="") as f:
        selected = list(csv.DictReader(f))
    new = load_new_traits(args.traits_dir)

    refs: dict[str, dict[str, dict]] = {}
    for run in sorted({s["run"] for s in selected}):
        path = Path(args.z_root) / run / "sleap_roots_traits_output" / "traits_summary.csv"
        with path.open(newline="") as f:
            refs[run] = {r["scan_id"]: r for r in csv.DictReader(f)}

    lines = [
        (
            "| species | trait | n | rho | median rel Δ | one-sided NaN | both NaN | "
            "result | per-age rho (info) |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    all_pass = True
    for species, traits in spec["species"].items():
        scans = [s for s in selected if s["species"] == species]
        missing = [s["scan_id"] for s in scans if s["scan_id"] not in new]
        if missing:
            print(f"{species}: no result envelope for scans {missing}", file=sys.stderr)
            all_pass = False  # a scan with no envelope is a miss, not a skip
        for t in traits:
            name, column, atol = t["trait"], t["reference_column"], float(t["atol"])
            pairs, by_age = [], {}
            for s in scans:
                ref_row = refs[s["run"]][s["scan_id"]]
                if column not in ref_row:
                    print(f"reference column {column} missing in {s['run']}", file=sys.stderr)
                    return 1
                nv = new.get(s["scan_id"], {}).get(name, math.nan)
                if s["scan_id"] in new and name not in new[s["scan_id"]]:
                    print(f"trait {name} missing from scan_{s['scan_id']}", file=sys.stderr)
                    return 1
                pair = (nv, _num(ref_row[column]))
                pairs.append(pair)
                by_age.setdefault(s["plant_age_days"], []).append(pair)
            r = evaluate_trait(pairs, atol)
            all_pass &= r["passed"]
            ages = ", ".join(
                f"d{a}: {_finite_rho(ps):.2f}"
                for a, ps in sorted(by_age.items(), key=lambda kv: int(kv[0]))
            )
            lines.append(
                f"| {species} | `{name}` | {r['n_pairs']} | {r['rho']:.3f} | "
                f"{r['median_err']:.3f} | {r['n_one_nan']} | {r['n_both_nan']} | "
                f"{'PASS' if r['passed'] else 'FAIL: ' + r['reason']} | {ages} |"
            )
    report = "\n".join(lines) + f"\n\nOverall: {'PASS' if all_pass else 'FAIL'}\n"
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
