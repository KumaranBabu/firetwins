"""
Unit tests for BatchResultAnalyzer, BatchAnalysisReport, VariantSummary,
and ChannelStats in pyfds.results.batch_analysis.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from pyfds.results.batch_analysis import (
    BatchResultAnalyzer,
    BatchAnalysisReport,
    VariantSummary,
    ChannelStats,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_summaries():
    """Three variant summaries with known device data."""
    return [
        VariantSummary(
            variant_id="var_hrr=250",
            axis_values={"hrr": 250.0},
            device_peaks={"TC_01": 120.0, "TC_02": 80.0},
            device_means={"TC_01": 60.0,  "TC_02": 40.0},
            device_integrals={"TC_01": 6000.0, "TC_02": 4000.0},
            device_units={"TC_01": "degC", "TC_02": "degC"},
            completed=True,
        ),
        VariantSummary(
            variant_id="var_hrr=500",
            axis_values={"hrr": 500.0},
            device_peaks={"TC_01": 200.0, "TC_02": 140.0},
            device_means={"TC_01": 100.0, "TC_02": 70.0},
            device_integrals={"TC_01": 10000.0, "TC_02": 7000.0},
            device_units={"TC_01": "degC", "TC_02": "degC"},
            completed=True,
        ),
        VariantSummary(
            variant_id="var_hrr=750",
            axis_values={"hrr": 750.0},
            device_peaks={"TC_01": 280.0, "TC_02": 195.0},
            device_means={"TC_01": 140.0, "TC_02": 97.0},
            device_integrals={"TC_01": 14000.0, "TC_02": 9700.0},
            device_units={"TC_01": "degC", "TC_02": "degC"},
            completed=True,
        ),
    ]


def _make_report():
    """Build a BatchAnalysisReport from hand-rolled summaries."""
    summaries = _make_summaries()
    analyzer = BatchResultAnalyzer.__new__(BatchResultAnalyzer)
    analyzer._outlier_sigma = 2.0
    stats = analyzer._compute_stats(summaries)
    return BatchAnalysisReport(
        study_name="mock_study",
        n_variants=len(summaries),
        n_completed=len(summaries),
        variant_summaries=summaries,
        channel_stats=stats,
    )


# ---------------------------------------------------------------------------
# VariantSummary
# ---------------------------------------------------------------------------

class TestVariantSummary:
    def test_peak_returns_value(self):
        s = _make_summaries()[0]
        assert s.peak("TC_01") == 120.0

    def test_peak_returns_none_for_unknown(self):
        s = _make_summaries()[0]
        assert s.peak("UNKNOWN") is None

    def test_failed_summary(self):
        s = VariantSummary(
            variant_id="bad_var",
            axis_values={},
            device_peaks={},
            device_means={},
            device_integrals={},
            device_units={},
            completed=False,
            error="FDS crashed",
        )
        assert not s.completed
        assert s.error == "FDS crashed"
        assert s.peak("TC_01") is None


# ---------------------------------------------------------------------------
# ChannelStats
# ---------------------------------------------------------------------------

class TestChannelStats:
    def _make_stats(self):
        return ChannelStats(
            channel="TC_01",
            units="degC",
            n_variants=3,
            peak_min=120.0,
            peak_max=280.0,
            peak_mean=200.0,
            peak_std=65.57,
            integral_min=6000.0,
            integral_max=14000.0,
            integral_mean=10000.0,
            integral_std=3265.99,
            outlier_variant_ids=[],
        )

    def test_peak_cov_is_fraction(self):
        s = self._make_stats()
        expected = s.peak_std / s.peak_mean  # fraction, not percentage
        assert abs(s.peak_cov - expected) < 1e-6

    def test_peak_cov_zero_mean(self):
        s = ChannelStats(
            channel="X", units="-", n_variants=2,
            peak_min=0.0, peak_max=0.0, peak_mean=0.0, peak_std=0.0,
            integral_min=0.0, integral_max=0.0, integral_mean=0.0, integral_std=0.0,
            outlier_variant_ids=[],
        )
        assert s.peak_cov == 0.0

    def test_as_dict_keys(self):
        s = self._make_stats()
        d = s.as_dict()
        assert d["channel"] == "TC_01"
        assert d["units"] == "degC"
        assert "peak_mean" in d
        assert "integral_mean" in d
        assert "outliers" in d  # stored as "outliers", not "outlier_variant_ids"


# ---------------------------------------------------------------------------
# BatchAnalysisReport (computed from hand-rolled summaries)
# ---------------------------------------------------------------------------

class TestBatchAnalysisReport:
    def test_summary_text(self):
        report = _make_report()
        txt = report.summary()
        assert "mock_study" in txt
        assert "3" in txt  # 3 variants

    def test_channel_stats_present(self):
        report = _make_report()
        channels = set(report.channel_stats.keys())
        assert "TC_01" in channels
        assert "TC_02" in channels

    def test_to_csv(self, tmp_path):
        report = _make_report()
        out = tmp_path / "stats.csv"
        report.to_csv(str(out))
        assert out.exists()
        # The CSV contains two sections; read all rows and look for stat entries
        with open(out, newline="") as f:
            raw = f.read()
        assert "TC_01" in raw
        assert "TC_02" in raw
        assert "CROSS-VARIANT STATISTICS" in raw

    def test_to_json(self, tmp_path):
        report = _make_report()
        out = tmp_path / "report.json"
        report.to_json(str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert "study_name" in data
        assert "channel_stats" in data
        assert len(data["channel_stats"]) == 2

    def test_to_html(self, tmp_path):
        report = _make_report()
        out = tmp_path / "report.html"
        report.to_html(str(out), title="Test Report")
        assert out.exists()
        html = out.read_text()
        assert "Test Report" in html
        assert "TC_01" in html
        assert "<table" in html


# ---------------------------------------------------------------------------
# BatchResultAnalyzer._parse_axis_values
# ---------------------------------------------------------------------------

class TestParseAxisValues:
    def test_single_key_value_numeric(self):
        a = BatchResultAnalyzer.__new__(BatchResultAnalyzer)
        result = a._parse_axis_values("var_hrr=500")
        assert result == {"hrr": 500.0}

    def test_multiple_key_values_numeric(self):
        a = BatchResultAnalyzer.__new__(BatchResultAnalyzer)
        result = a._parse_axis_values("sim_hrr=250_tau=30.5")
        assert result["hrr"] == 250.0
        assert result["tau"] == 30.5

    def test_no_key_value(self):
        a = BatchResultAnalyzer.__new__(BatchResultAnalyzer)
        result = a._parse_axis_values("plain_variant_name")
        assert result == {}

    def test_non_numeric_value(self):
        a = BatchResultAnalyzer.__new__(BatchResultAnalyzer)
        result = a._parse_axis_values("var_fuel=methane")
        assert result == {"fuel": "methane"}


# ---------------------------------------------------------------------------
# BatchResultAnalyzer.analyze() — end-to-end with fake filesystem
# ---------------------------------------------------------------------------

class TestBatchResultAnalyzerEndToEnd:
    """Builds a fake batch output tree and exercises analyze()."""

    @pytest.fixture
    def batch_tree(self, tmp_path):
        """
        Creates:
          tmp_path/
            my_study/
              var_hrr=250/
                var_hrr=250_devc.csv
              var_hrr=500/
                var_hrr=500_devc.csv
        """
        study = tmp_path / "my_study"
        variants_data = {
            "var_hrr=250": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "var_hrr=500": [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200],
        }
        times = list(range(0, 110, 10))  # 0 .. 100

        for var_name, vals in variants_data.items():
            var_dir = study / var_name
            var_dir.mkdir(parents=True)
            csv_path = var_dir / f"{var_name}_devc.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                # DeviceReader expects: row1=channel names, row2=units
                writer.writerow(["Time", "TC_01"])
                writer.writerow(["s", "degC"])
                for t, v in zip(times, vals):
                    writer.writerow([t, v])

        return tmp_path, "my_study"

    def test_analyze_returns_report(self, batch_tree):
        root, study = batch_tree
        analyzer = BatchResultAnalyzer(str(root), study_name=study)
        report = analyzer.analyze()
        assert isinstance(report, BatchAnalysisReport)

    def test_two_variants_discovered(self, batch_tree):
        root, study = batch_tree
        analyzer = BatchResultAnalyzer(str(root), study_name=study)
        report = analyzer.analyze()
        assert len(report.variant_summaries) == 2

    def test_channel_stats_computed(self, batch_tree):
        root, study = batch_tree
        analyzer = BatchResultAnalyzer(str(root), study_name=study)
        report = analyzer.analyze()
        assert len(report.channel_stats) >= 1
        # channel_stats is a dict keyed by channel name
        assert "TC_01" in report.channel_stats
        tc = report.channel_stats["TC_01"]
        assert tc.peak_max > tc.peak_min
        assert tc.n_variants == 2

    def test_analyze_without_study_name(self, tmp_path):
        """When no study_name, output_root itself is treated as the study dir."""
        times = list(range(0, 60, 10))
        for var in ("v1", "v2"):
            d = tmp_path / var
            d.mkdir()
            csv_path = d / f"{var}_devc.csv"
            with open(csv_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Time", "DEV_A"])
                w.writerow(["s", "degC"])
                for t in times:
                    w.writerow([t, float(t * 2)])

        analyzer = BatchResultAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert len(report.variant_summaries) == 2

    def test_failed_variant_excluded_from_stats(self, tmp_path):
        """A variant with no CSV should be marked as failed/incomplete."""
        study = tmp_path / "s"
        (study / "good").mkdir(parents=True)
        (study / "bad").mkdir(parents=True)  # no CSV

        csv_path = study / "good" / "good_devc.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Time", "TC_1"])
            w.writerow(["s", "degC"])
            for t in range(0, 60, 10):
                w.writerow([t, float(t)])

        analyzer = BatchResultAnalyzer(str(tmp_path), study_name="s")
        report = analyzer.analyze()
        ids = [v.variant_id for v in report.variant_summaries]
        assert "good" in ids
        bad_summary = next(v for v in report.variant_summaries if v.variant_id == "bad")
        assert not bad_summary.completed


# ---------------------------------------------------------------------------
# Top-level pyfds exports
# ---------------------------------------------------------------------------

def test_top_level_exports():
    import pyfds
    assert hasattr(pyfds, "BatchResultAnalyzer")
    assert hasattr(pyfds, "BatchAnalysisReport")
    assert hasattr(pyfds, "VariantSummary")
    assert hasattr(pyfds, "ChannelStats")


def test_results_package_exports():
    from pyfds import results
    assert hasattr(results, "BatchResultAnalyzer")
    assert hasattr(results, "BatchAnalysisReport")


def test_api_analyze_batch_method():
    from pyfds.api.controller import FdsApi
    api = FdsApi()
    assert hasattr(api.results, "analyze_batch")
    assert callable(api.results.analyze_batch)
