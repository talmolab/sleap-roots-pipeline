"""Tests for compare_traits.py on tiny synthetic tables.

Run:  uv run --no-project --with pytest pytest test_compare_traits.py -v   (from this folder)
"""

from __future__ import annotations

import json
import math

import pytest

from compare_traits import evaluate_trait, load_new_traits, scan_error, spearman

NAN = math.nan


class TestSpearman:
    def test_perfect_monotone_is_one(self):
        assert spearman([1, 2, 3, 4], [10, 20, 30, 400]) == pytest.approx(1.0)

    def test_reversed_is_minus_one(self):
        assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_known_answer_with_ties(self):
        # Ranks x = [1, 2.5, 2.5, 4], y = [1, 2, 3, 4]; Pearson on ranks = 0.9486832980505138
        # (scipy.stats.spearmanr([1, 2, 2, 3], [1, 2, 3, 4]) gives the same).
        assert spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.9486832980505138)

    def test_constant_side_is_undefined(self):
        assert math.isnan(spearman([5, 5, 5], [1, 2, 3]))

    def test_fewer_than_two_is_undefined(self):
        assert math.isnan(spearman([1], [1]))


class TestScanError:
    def test_relative_error_outside_tolerance(self):
        assert scan_error(new=110.0, ref=100.0, atol=0.0) == pytest.approx(0.10)

    def test_within_absolute_tolerance_is_zero(self):
        # A count off by one on a reference of 2 is 50% relative, but within ±1.
        assert scan_error(new=3.0, ref=2.0, atol=1.0) == 0.0

    def test_outside_absolute_tolerance_is_relative(self):
        assert scan_error(new=4.0, ref=2.0, atol=1.0) == pytest.approx(1.0)

    def test_zero_reference_outside_tolerance_is_infinite(self):
        assert scan_error(new=5.0, ref=0.0, atol=1.0) == math.inf

    def test_one_sided_nan_is_infinite(self):
        assert scan_error(new=NAN, ref=3.0, atol=1.0) == math.inf
        assert scan_error(new=3.0, ref=NAN, atol=1.0) == math.inf

    def test_both_nan_is_none(self):
        # Both missing is agreement, but carries no value: excluded from both criteria.
        assert scan_error(new=NAN, ref=NAN, atol=1.0) is None


def _pairs(news, refs):
    return list(zip(news, refs))


class TestEvaluateTrait:
    def test_passes_when_close_and_correlated(self):
        refs = [float(v) for v in range(10, 130, 10)]  # 12 scans
        news = [v * 1.05 for v in refs]
        r = evaluate_trait(_pairs(news, refs), atol=0.0)
        assert r["rho"] == pytest.approx(1.0)
        assert r["median_err"] == pytest.approx(0.05)
        assert r["n_pairs"] == 12
        assert r["passed"] is True

    def test_fails_on_median_relative_delta(self):
        refs = [float(v) for v in range(10, 130, 10)]
        news = [v * 1.2 for v in refs]  # perfectly ranked, but 20% off
        r = evaluate_trait(_pairs(news, refs), atol=0.0)
        assert r["rho"] == pytest.approx(1.0)
        assert r["passed"] is False
        assert "median" in r["reason"]

    def test_fails_on_rho(self):
        refs = [float(v) for v in range(1, 13)]
        news = refs[::-1]  # same values, reversed order: median Δ small-ish, rho -1
        r = evaluate_trait(_pairs(news, refs), atol=100.0)
        assert r["median_err"] == 0.0
        assert r["rho"] == pytest.approx(-1.0)
        assert r["passed"] is False
        assert "rho" in r["reason"]

    def test_one_sided_nans_count_against_median(self):
        refs = [float(v) for v in range(10, 130, 10)]
        news = list(refs)
        for i in range(7):  # 7 of 12 missing on the new side -> median error is inf
            news[i] = NAN
        r = evaluate_trait(_pairs(news, refs), atol=0.0)
        assert r["n_one_nan"] == 7
        assert r["median_err"] == math.inf
        assert r["passed"] is False

    def test_both_nan_excluded_and_reported(self):
        refs = [float(v) for v in range(10, 130, 10)] + [NAN, NAN]
        news = [float(v) for v in range(10, 130, 10)] + [NAN, NAN]
        r = evaluate_trait(_pairs(news, refs), atol=0.0)
        assert r["n_both_nan"] == 2
        assert r["n_pairs"] == 12
        assert r["passed"] is True

    def test_too_few_pairs_fails(self):
        refs = [float(v) for v in range(1, 10)]  # 9 finite pairs < 10
        r = evaluate_trait(_pairs(refs, refs), atol=0.0)
        assert r["passed"] is False
        assert "pairs" in r["reason"]

    def test_undefined_rho_fails(self):
        refs = [3.0] * 12
        r = evaluate_trait(_pairs(refs, refs), atol=1.0)
        assert math.isnan(r["rho"])
        assert r["passed"] is False

    def test_thresholds_are_inclusive(self):
        refs = [float(v) for v in range(10, 130, 10)]
        news = [v * 1.10 for v in refs]
        r = evaluate_trait(_pairs(news, refs), atol=0.0)
        assert r["median_err"] == pytest.approx(0.10)
        assert r["passed"] is True


class TestLoadNewTraits:
    def test_reads_result_envelopes(self, tmp_path):
        env = {
            "provenance": {"scan_key": "scan_7", "params": {"values": {"age": 17}}},
            "traits": [
                {
                    "name": "lateral_count_median",
                    "value": 4.0,
                    "grain": "scan",
                    "scan_key": "scan_7",
                },
                {
                    "name": "primary_length_median",
                    "value": None,
                    "grain": "scan",
                    "scan_key": "scan_7",
                },
            ],
            "blobs": [],
        }
        (tmp_path / "scan_7.result.json").write_text(json.dumps(env))
        got = load_new_traits(tmp_path)
        assert got["7"]["lateral_count_median"] == 4.0
        assert math.isnan(got["7"]["primary_length_median"])


class TestMainEndToEnd:
    """main() on a synthetic Z-root, selection and traits dir."""

    def _setup(self, tmp_path, scale):
        run = "run_a"
        ref_dir = tmp_path / "z" / run / "sleap_roots_traits_output"
        ref_dir.mkdir(parents=True)
        traits_dir = tmp_path / "traits"
        traits_dir.mkdir()
        sel = ["species,run,scan_id,plant_age_days"]
        ref = ["scan_id,crown_count_median"]
        for i in range(12):
            sid = str(100 + i)
            sel.append(f"wheat,{run},{sid},{5 if i < 6 else 11}")
            ref.append(f"{sid},{10 + i}")
            env = {
                "provenance": {},
                "blobs": [],
                "traits": [
                    {
                        "name": "crown_count_median",
                        "value": (10 + i) * scale,
                        "grain": "scan",
                        "scan_key": f"scan_{sid}",
                    }
                ],
            }
            (traits_dir / f"scan_{sid}.result.json").write_text(json.dumps(env))
        (tmp_path / "sel.csv").write_text("\n".join(sel) + "\n")
        (ref_dir / "traits_summary.csv").write_text("\n".join(ref) + "\n")
        spec = {
            "species": {
                "wheat": [
                    {
                        "trait": "crown_count_median",
                        "reference_column": "crown_count_median",
                        "atol": 0,
                    }
                ]
            }
        }
        (tmp_path / "spec.json").write_text(json.dumps(spec))
        return [
            "--traits-dir",
            str(traits_dir),
            "--z-root",
            str(tmp_path / "z"),
            "--spec",
            str(tmp_path / "spec.json"),
            "--selected",
            str(tmp_path / "sel.csv"),
            "--out",
            str(tmp_path / "out.md"),
        ]

    def test_pass_exits_zero_and_writes_report(self, tmp_path):
        from compare_traits import main

        assert main(self._setup(tmp_path, 1.0)) == 0
        assert "Overall: PASS" in (tmp_path / "out.md").read_text(encoding="utf-8")

    def test_fail_exits_two(self, tmp_path):
        from compare_traits import main

        assert main(self._setup(tmp_path, 1.5)) == 2

    def test_missing_envelope_is_a_fail_not_a_skip(self, tmp_path):
        from compare_traits import main

        argv = self._setup(tmp_path, 1.0)
        (tmp_path / "traits" / "scan_100.result.json").unlink()
        assert main(argv) == 2
