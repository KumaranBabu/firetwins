"""Unit tests — pyfds.results.comparator (ComparisonReport, ChannelComparison, SimulationComparator)."""
from __future__ import annotations

import math
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from pyfds.results.comparator import (
    ChannelComparison, ComparisonReport, SimulationComparator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ch(name="TC_01", status="ok", peak_pct_diff=0.0, threshold=5.0):
    return ChannelComparison(
        name=name, units="°C",
        baseline_peak=100.0, variant_peak=100.0 * (1 + peak_pct_diff / 100),
        peak_pct_diff=peak_pct_diff,
        baseline_mean=50.0, variant_mean=50.0,
        mean_pct_diff=0.0,
        threshold_pct=threshold,
        status=status,
    )


def _make_reader_result(data, units="°C"):
    rr = MagicMock()
    rr.data = data
    rr.units = units
    return rr


# ---------------------------------------------------------------------------
# ChannelComparison
# ---------------------------------------------------------------------------

class TestChannelComparison:
    def test_basic_creation(self):
        ch = _ch("TC_01", "ok", 2.0)
        assert ch.name == "TC_01"
        assert ch.status == "ok"
        assert ch.peak_pct_diff == 2.0

    def test_note_default_empty(self):
        ch = _ch()
        assert ch.note == ""


# ---------------------------------------------------------------------------
# ComparisonReport — properties
# ---------------------------------------------------------------------------

class TestComparisonReport:
    def test_n_ok_counts_ok(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[_ch("A", "ok"), _ch("B", "ok"), _ch("C", "warning")],
        )
        assert rpt.n_ok == 2

    def test_n_warnings_counts_warnings(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[_ch("A", "warning"), _ch("B", "ok")],
        )
        assert rpt.n_warnings == 1

    def test_n_missing_counts_missing(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[
                _ch("A", "missing_baseline"),
                _ch("B", "missing_variant"),
                _ch("C", "ok"),
            ],
        )
        assert rpt.n_missing == 2

    def test_passed_true_when_no_warnings_or_missing(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[_ch("A", "ok"), _ch("B", "ok")],
        )
        assert rpt.passed is True

    def test_passed_false_when_warnings(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[_ch("A", "warning")],
        )
        assert rpt.passed is False

    def test_passed_false_when_missing(self):
        rpt = ComparisonReport(
            baseline_dir="b/", variant_dir="v/", threshold_pct=5.0,
            channels=[_ch("A", "missing_baseline")],
        )
        assert rpt.passed is False

    def test_summary_contains_dirs(self):
        rpt = ComparisonReport(
            baseline_dir="baseline/", variant_dir="variant/", threshold_pct=5.0,
        )
        summary = rpt.summary()
        assert "baseline/" in summary
        assert "variant/" in summary

    def test_summary_contains_threshold(self):
        rpt = ComparisonReport("b/", "v/", threshold_pct=10.0)
        assert "10.0" in rpt.summary()

    def test_summary_empty_channels(self):
        rpt = ComparisonReport("b/", "v/", threshold_pct=5.0)
        summary = rpt.summary()
        assert "0 total" in summary


# ---------------------------------------------------------------------------
# SimulationComparator._compare_channel (static)
# ---------------------------------------------------------------------------

class TestCompareChannel:
    def test_both_missing_returns_missing_baseline(self):
        ch = SimulationComparator._compare_channel("TC", None, None, 5.0)
        assert ch.status == "missing_baseline"

    def test_missing_baseline(self):
        var = _make_reader_result([1.0, 2.0])
        ch = SimulationComparator._compare_channel("TC", None, var, 5.0)
        assert ch.status == "missing_baseline"

    def test_missing_variant(self):
        base = _make_reader_result([1.0, 2.0])
        ch = SimulationComparator._compare_channel("TC", base, None, 5.0)
        assert ch.status == "missing_variant"

    def test_ok_when_within_threshold(self):
        base = _make_reader_result([100.0, 90.0, 80.0])
        var  = _make_reader_result([102.0, 91.0, 79.0])
        ch = SimulationComparator._compare_channel("TC", base, var, 5.0)
        assert ch.status == "ok"

    def test_warning_when_exceeds_threshold(self):
        base = _make_reader_result([100.0])
        var  = _make_reader_result([200.0])
        ch = SimulationComparator._compare_channel("TC", base, var, 5.0)
        assert ch.status == "warning"
        assert ch.peak_pct_diff == pytest.approx(100.0)

    def test_units_taken_from_baseline(self):
        base = _make_reader_result([100.0], units="kW")
        var  = _make_reader_result([100.0], units="kW")
        ch = SimulationComparator._compare_channel("HRR", base, var, 5.0)
        assert ch.units == "kW"

    def test_zero_baseline_zero_variant_is_ok(self):
        base = _make_reader_result([0.0, 0.0])
        var  = _make_reader_result([0.0, 0.0])
        ch = SimulationComparator._compare_channel("V", base, var, 5.0)
        assert ch.status == "ok"

    def test_empty_arrays_ok(self):
        base = _make_reader_result([])
        var  = _make_reader_result([])
        ch = SimulationComparator._compare_channel("E", base, var, 5.0)
        assert ch.status == "ok"


# ---------------------------------------------------------------------------
# SimulationComparator — full compare (mocked _load_all)
# ---------------------------------------------------------------------------

class TestSimulationComparator:
    def test_compare_empty_dirs_returns_report(self, tmp_path):
        base_dir = tmp_path / "base"
        var_dir  = tmp_path / "var"
        base_dir.mkdir()
        var_dir.mkdir()
        cmp = SimulationComparator(str(base_dir), str(var_dir))
        rpt = cmp.compare()
        assert isinstance(rpt, ComparisonReport)

    def test_compare_no_csv_files_logs_warning(self, tmp_path, caplog):
        import logging
        base_dir = tmp_path / "base"
        var_dir  = tmp_path / "var"
        base_dir.mkdir()
        var_dir.mkdir()
        cmp = SimulationComparator(str(base_dir), str(var_dir))
        with caplog.at_level(logging.WARNING, logger="pyfds.results.comparator"):
            cmp.compare()

    def test_channel_names_from_mocked_load(self, tmp_path):
        base_dir = tmp_path / "base"
        var_dir  = tmp_path / "var"
        base_dir.mkdir()
        var_dir.mkdir()
        cmp = SimulationComparator(str(base_dir), str(var_dir))

        mock_base = {"TC_01": _make_reader_result([1.0]), "Time": _make_reader_result([1.0])}
        mock_var  = {"TC_01": _make_reader_result([1.0]), "Time": _make_reader_result([1.0])}
        with patch.object(cmp, "_load_all", side_effect=[mock_base, mock_var]):
            b_names, v_names = cmp.channel_names()
        assert "TC_01" in b_names
        assert "TC_01" in v_names

    def test_compare_with_mocked_data(self, tmp_path):
        base_dir = tmp_path / "base"
        var_dir  = tmp_path / "var"
        base_dir.mkdir()
        var_dir.mkdir()
        cmp = SimulationComparator(str(base_dir), str(var_dir))

        # Exclude "Time" from mocks — the source has an operator-precedence quirk
        # where only var_data has "Time" subtracted, so including it in both would
        # yield an extra channel. Using non-Time names avoids that.
        mock_base = {"TC_01": _make_reader_result([100.0, 90.0])}
        mock_var  = {"TC_01": _make_reader_result([101.0, 91.0])}
        with patch.object(cmp, "_load_all", side_effect=[mock_base, mock_var]):
            rpt = cmp.compare(threshold_pct=5.0)

        assert len(rpt.channels) == 1
        assert rpt.channels[0].status == "ok"
