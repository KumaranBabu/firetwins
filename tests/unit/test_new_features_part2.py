"""Tests for features added in the "proceed to implement all" session: (part 2 of 2)."""


from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Surface,
    WindProfile, Move, HvacFilter, HvacLeakage,
)
from pyfds.domain.factory import EntityFactory
from pyfds.domain.egress import (
    EgressScenario, ExitZone, OccupantGroup, TenabilityLimit,
)
from pyfds.meshing.manager import MeshingManager
from pyfds.results.comparator import SimulationComparator, ChannelComparison


class TestSimulationComparator:
    """Tests use mock DeviceReader results to avoid needing real CSV files."""

    def _make_reader_result(self, data: list, units: str = "C"):
        from pyfds.results.reader import ReaderResult
        rr = ReaderResult(source_file="fake.csv", quantity="T", units=units)
        rr.data = np.array(data, dtype=float)
        return rr

    def _compare_channels(self, base_data, var_data, threshold=5.0) -> ChannelComparison:
        return SimulationComparator._compare_channel(
            "TC1", base_data, var_data, threshold
        )

    def test_ok_when_within_threshold(self):
        b = self._make_reader_result([10.0, 20.0, 15.0])
        v = self._make_reader_result([10.0, 21.0, 15.0])  # peak diff ≈ 5%
        ch = self._compare_channels(b, v, threshold=5.0)
        assert ch.status == "ok"

    def test_warning_when_exceeds_threshold(self):
        b = self._make_reader_result([100.0, 200.0])
        v = self._make_reader_result([100.0, 260.0])  # peak diff = 30%
        ch = self._compare_channels(b, v, threshold=5.0)
        assert ch.status == "warning"

    def test_missing_baseline(self):
        v = self._make_reader_result([50.0])
        ch = self._compare_channels(None, v, threshold=5.0)
        assert ch.status == "missing_baseline"

    def test_missing_variant(self):
        b = self._make_reader_result([50.0])
        ch = self._compare_channels(b, None, threshold=5.0)
        assert ch.status == "missing_variant"

    def test_peak_pct_diff_sign(self):
        """Higher variant peak → positive diff."""
        b = self._make_reader_result([0.0, 100.0])
        v = self._make_reader_result([0.0, 120.0])
        ch = self._compare_channels(b, v, threshold=50.0)
        assert ch.peak_pct_diff > 0.0

    def test_peak_pct_diff_negative_when_lower(self):
        b = self._make_reader_result([0.0, 100.0])
        v = self._make_reader_result([0.0, 80.0])
        ch = self._compare_channels(b, v, threshold=50.0)
        assert ch.peak_pct_diff < 0.0

    def test_units_preserved(self):
        b = self._make_reader_result([100.0], units="°C")
        v = self._make_reader_result([100.0], units="°C")
        ch = self._compare_channels(b, v)
        assert ch.units == "°C"

    def test_report_passed_property_no_warnings(self):
        from pyfds.results.comparator import ComparisonReport
        report = ComparisonReport(
            baseline_dir="a", variant_dir="b", threshold_pct=5.0,
            channels=[
                ChannelComparison(
                    name="TC1", units="C",
                    baseline_peak=100.0, variant_peak=103.0,
                    peak_pct_diff=3.0,
                    baseline_mean=80.0, variant_mean=82.0,
                    mean_pct_diff=2.5,
                    threshold_pct=5.0,
                    status="ok",
                ),
            ],
        )
        assert report.passed is True
        assert report.n_ok == 1
        assert report.n_warnings == 0

    def test_report_not_passed_with_warning(self):
        from pyfds.results.comparator import ComparisonReport
        report = ComparisonReport(
            baseline_dir="a", variant_dir="b", threshold_pct=5.0,
            channels=[
                ChannelComparison(
                    name="TC1", units="C",
                    baseline_peak=100.0, variant_peak=150.0,
                    peak_pct_diff=50.0,
                    baseline_mean=80.0, variant_mean=120.0,
                    mean_pct_diff=50.0,
                    threshold_pct=5.0,
                    status="warning",
                    note="Over threshold",
                ),
            ],
        )
        assert report.passed is False
        assert report.n_warnings == 1

    def test_report_summary_contains_channel_name(self):
        from pyfds.results.comparator import ComparisonReport
        ch = ChannelComparison(
            name="MY_DEVICE", units="", baseline_peak=1.0, variant_peak=1.0,
            peak_pct_diff=0.0, baseline_mean=0.5, variant_mean=0.5,
            mean_pct_diff=0.0, threshold_pct=5.0, status="ok",
        )
        report = ComparisonReport("x", "y", 5.0, channels=[ch])
        summary = report.summary()
        assert "MY_DEVICE" in summary

    def test_load_all_graceful_when_no_csv(self, tmp_path):
        """_load_all returns empty dict when directory has no *_devc.csv files."""
        cmp = SimulationComparator(str(tmp_path), str(tmp_path))
        data = cmp._load_all(tmp_path)
        assert data == {}

    def test_compare_no_csvs_returns_empty_report(self, tmp_path):
        cmp = SimulationComparator(str(tmp_path), str(tmp_path))
        report = cmp.compare(threshold_pct=5.0)
        assert len(report.channels) == 0
        assert report.passed is True

class TestExitZone:

    def test_to_dict_basic(self):
        ez = ExitZone(id="EXIT_A", xb=(9.9, 10.0, 0.0, 2.0, 0.0, 3.0))
        d = ez.to_dict()
        assert d["id"] == "EXIT_A"
        assert d["xb"] == [9.9, 10.0, 0.0, 2.0, 0.0, 3.0]
        assert "door_width_m" in d

    def test_capacity_included_when_set(self):
        ez = ExitZone(id="E", xb=(0,1,0,1,0,1), capacity=3)
        d = ez.to_dict()
        assert d["capacity_per_s"] == 3

    def test_capacity_absent_when_none(self):
        ez = ExitZone(id="E", xb=(0,1,0,1,0,1))
        assert "capacity_per_s" not in ez.to_dict()

    def test_notes_included_when_set(self):
        ez = ExitZone(id="E", xb=(0,1,0,1,0,1), notes="Fire exit")
        assert "notes" in ez.to_dict()

class TestOccupantGroup:

    def test_to_dict_round_trip(self):
        og = OccupantGroup(
            id="G1", count=100,
            start_region=(0.0, 10.0, 0.0, 10.0, 0.0, 3.0),
        )
        d = og.to_dict()
        assert d["id"] == "G1"
        assert d["count"] == 100
        assert len(d["start_region"]) == 6

    def test_mobility_default(self):
        og = OccupantGroup(id="G1", count=10, start_region=(0,1,0,1,0,1))
        assert og.mobility == "ambulatory"
        assert og.to_dict()["mobility"] == "ambulatory"

class TestEgressScenario:

    def _scenario(self) -> EgressScenario:
        return EgressScenario(
            fds_chid="test_fire",
            t_start_evac=60.0,
            exits=[
                ExitZone(id="E1", xb=(9.9, 10.0, 0.0, 2.0, 0.0, 3.0)),
                ExitZone(id="E2", xb=(9.9, 10.0, 8.0, 10.0, 0.0, 3.0)),
            ],
            occupant_groups=[
                OccupantGroup(id="G1", count=30, start_region=(0,5,0,5,0,3)),
                OccupantGroup(id="G2", count=20, start_region=(5,10,0,5,0,3)),
            ],
            hazard_channels=["TC_01", "CO_01"],
            tenability_limits={"TEMPERATURE": 60.0, "CO_PPM": 1400.0},
        )

    def test_total_occupants(self):
        s = self._scenario()
        assert s.total_occupants == 50

    def test_exit_ids(self):
        s = self._scenario()
        assert s.exit_ids == ["E1", "E2"]

    def test_to_dict_keys(self):
        d = self._scenario().to_dict()
        for key in ("fds_chid", "t_start_evac_s", "total_occupants",
                    "exits", "occupant_groups", "hazard_channels",
                    "tenability_limits"):
            assert key in d

    def test_to_dict_fds_chid(self):
        assert self._scenario().to_dict()["fds_chid"] == "test_fire"

    def test_to_dict_t_start(self):
        assert self._scenario().to_dict()["t_start_evac_s"] == 60.0

    def test_to_dict_exits_count(self):
        d = self._scenario().to_dict()
        assert len(d["exits"]) == 2

    def test_to_dict_occupants_count(self):
        d = self._scenario().to_dict()
        assert len(d["occupant_groups"]) == 2

    def test_to_dict_tenability_limits_serialised(self):
        d = self._scenario().to_dict()
        quantities = {item["quantity"] for item in d["tenability_limits"]}
        assert "TEMPERATURE" in quantities
        assert "CO_PPM" in quantities

    def test_from_dict_round_trip(self):
        s = self._scenario()
        d = s.to_dict()
        s2 = EgressScenario.from_dict(d)
        assert s2.fds_chid == s.fds_chid
        assert s2.t_start_evac == s.t_start_evac
        assert s2.total_occupants == s.total_occupants
        assert len(s2.exits) == len(s.exits)
        assert len(s2.occupant_groups) == len(s.occupant_groups)

    def test_from_dict_exit_fields(self):
        s = self._scenario()
        s2 = EgressScenario.from_dict(s.to_dict())
        e = s2.exits[0]
        assert e.id == "E1"
        assert len(e.xb) == 6

    def test_from_dict_tenability_limits(self):
        s = self._scenario()
        s2 = EgressScenario.from_dict(s.to_dict())
        assert s2.tenability_limits.get("TEMPERATURE") == 60.0

    def test_empty_scenario(self):
        s = EgressScenario(fds_chid="empty")
        assert s.total_occupants == 0
        assert s.exit_ids == []
        d = s.to_dict()
        assert d["total_occupants"] == 0

    def test_description_included_when_set(self):
        s = EgressScenario(fds_chid="x", description="Hotel lobby scenario")
        d = s.to_dict()
        assert d["description"] == "Hotel lobby scenario"

    def test_description_absent_when_empty(self):
        s = EgressScenario(fds_chid="x")
        d = s.to_dict()
        assert "description" not in d
