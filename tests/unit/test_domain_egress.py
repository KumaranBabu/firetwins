"""Unit tests — pyfds.domain.egress (ExitZone, OccupantGroup, EgressScenario)."""
from __future__ import annotations

import pytest
from pyfds.domain.egress import ExitZone, OccupantGroup, TenabilityLimit, EgressScenario


# ---------------------------------------------------------------------------
# ExitZone
# ---------------------------------------------------------------------------

class TestExitZone:
    def test_basic_creation(self):
        ez = ExitZone(id="EXIT_N", xb=(9.9, 10.0, 2.0, 4.0, 0.0, 3.0))
        assert ez.id == "EXIT_N"
        assert len(ez.xb) == 6

    def test_default_door_width(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        assert ez.door_width == 0.9

    def test_default_door_height(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        assert ez.door_height == 2.1

    def test_accessible_default_true(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        assert ez.accessible is True

    def test_capacity_none_by_default(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        assert ez.capacity is None

    def test_to_dict_keys(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2), capacity=5, notes="main")
        d = ez.to_dict()
        assert d["id"] == "E1"
        assert d["xb"] == [0, 1, 0, 1, 0, 2]
        assert d["capacity_per_s"] == 5
        assert d["notes"] == "main"

    def test_to_dict_excludes_none_capacity(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        d = ez.to_dict()
        assert "capacity_per_s" not in d

    def test_to_dict_excludes_empty_notes(self):
        ez = ExitZone("E1", (0, 1, 0, 1, 0, 2))
        d = ez.to_dict()
        assert "notes" not in d


# ---------------------------------------------------------------------------
# OccupantGroup
# ---------------------------------------------------------------------------

class TestOccupantGroup:
    def test_basic_creation(self):
        og = OccupantGroup(id="FLOOR1", count=50, start_region=(0, 10, 0, 10, 0, 3))
        assert og.id == "FLOOR1"
        assert og.count == 50

    def test_default_speed_mean(self):
        og = OccupantGroup("G1", 10, (0, 1, 0, 1, 0, 1))
        assert og.speed_mean == 1.2

    def test_default_mobility(self):
        og = OccupantGroup("G1", 10, (0, 1, 0, 1, 0, 1))
        assert og.mobility == "ambulatory"

    def test_to_dict_keys(self):
        og = OccupantGroup("G1", 30, (0, 5, 0, 5, 0, 3))
        d = og.to_dict()
        assert d["id"] == "G1"
        assert d["count"] == 30
        assert "speed" in d
        assert "pre_movement_s" in d
        assert d["mobility"] == "ambulatory"

    def test_to_dict_speed_structure(self):
        og = OccupantGroup("G1", 10, (0, 1, 0, 1, 0, 1), speed_mean=1.5, speed_std=0.3)
        d = og.to_dict()
        assert d["speed"]["mean_m_s"] == 1.5
        assert d["speed"]["std_m_s"] == 0.3

    def test_to_dict_notes_excluded_when_empty(self):
        og = OccupantGroup("G1", 10, (0, 1, 0, 1, 0, 1))
        d = og.to_dict()
        assert "notes" not in d

    def test_to_dict_notes_included_when_set(self):
        og = OccupantGroup("G1", 10, (0, 1, 0, 1, 0, 1), notes="elderly")
        d = og.to_dict()
        assert d["notes"] == "elderly"


# ---------------------------------------------------------------------------
# TenabilityLimit
# ---------------------------------------------------------------------------

class TestTenabilityLimit:
    def test_basic_creation(self):
        tl = TenabilityLimit(quantity="TEMPERATURE", threshold=60.0, units="°C")
        assert tl.quantity == "TEMPERATURE"
        assert tl.threshold == 60.0

    def test_to_dict(self):
        tl = TenabilityLimit(quantity="CO_PPM", threshold=1400.0, units="ppm")
        d = tl.to_dict()
        assert d["quantity"] == "CO_PPM"
        assert d["threshold"] == 1400.0
        assert d["units"] == "ppm"

    def test_to_dict_no_units_when_empty(self):
        tl = TenabilityLimit("TEMPERATURE", 60.0)
        d = tl.to_dict()
        assert "units" not in d


# ---------------------------------------------------------------------------
# EgressScenario
# ---------------------------------------------------------------------------

class TestEgressScenario:
    def _make_scenario(self):
        return EgressScenario(
            fds_chid="hotel_fire",
            t_start_evac=60.0,
            exits=[
                ExitZone("EXIT_N", (9.9, 10.0, 2.0, 4.0, 0.0, 3.0)),
                ExitZone("EXIT_S", (9.9, 10.0, 6.0, 8.0, 0.0, 3.0)),
            ],
            occupant_groups=[
                OccupantGroup("FLOOR1", 50, (0, 10, 0, 10, 0, 3)),
            ],
            hazard_channels=["TC_01", "CO_DEVC"],
            tenability_limits={"TEMPERATURE": 60.0},
        )

    def test_basic_creation(self):
        s = self._make_scenario()
        assert s.fds_chid == "hotel_fire"
        assert s.t_start_evac == 60.0

    def test_total_occupants(self):
        s = self._make_scenario()
        assert s.total_occupants == 50

    def test_total_occupants_multiple_groups(self):
        s = EgressScenario(
            fds_chid="x",
            occupant_groups=[
                OccupantGroup("A", 30, (0, 1, 0, 1, 0, 1)),
                OccupantGroup("B", 20, (0, 1, 0, 1, 0, 1)),
            ],
        )
        assert s.total_occupants == 50

    def test_exit_ids(self):
        s = self._make_scenario()
        assert "EXIT_N" in s.exit_ids
        assert "EXIT_S" in s.exit_ids

    def test_to_dict_fds_chid(self):
        d = self._make_scenario().to_dict()
        assert d["fds_chid"] == "hotel_fire"

    def test_to_dict_total_occupants(self):
        d = self._make_scenario().to_dict()
        assert d["total_occupants"] == 50

    def test_to_dict_exits_list(self):
        d = self._make_scenario().to_dict()
        assert len(d["exits"]) == 2

    def test_to_dict_hazard_channels(self):
        d = self._make_scenario().to_dict()
        assert "TC_01" in d["hazard_channels"]

    def test_to_dict_tenability_limits(self):
        d = self._make_scenario().to_dict()
        limits = d["tenability_limits"]
        assert any(item["quantity"] == "TEMPERATURE" for item in limits)

    def test_from_dict_roundtrip(self):
        orig = self._make_scenario()
        d = orig.to_dict()
        restored = EgressScenario.from_dict(d)
        assert restored.fds_chid == orig.fds_chid
        assert restored.t_start_evac == orig.t_start_evac
        assert len(restored.exits) == len(orig.exits)
        assert len(restored.occupant_groups) == len(orig.occupant_groups)

    def test_from_dict_tenability_limits_restored(self):
        orig = self._make_scenario()
        d = orig.to_dict()
        restored = EgressScenario.from_dict(d)
        assert "TEMPERATURE" in restored.tenability_limits

    def test_description_excluded_when_empty(self):
        s = EgressScenario(fds_chid="x")
        d = s.to_dict()
        assert "description" not in d

    def test_description_included_when_set(self):
        s = EgressScenario(fds_chid="x", description="hotel scenario")
        d = s.to_dict()
        assert d["description"] == "hotel scenario"

    def test_defaults_empty_lists(self):
        s = EgressScenario(fds_chid="x")
        assert s.exits == []
        assert s.occupant_groups == []
        assert s.hazard_channels == []
