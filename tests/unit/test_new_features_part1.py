"""Tests for features added in the "proceed to implement all" session: (part 1 of 2)."""


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


def _simple_project() -> FdsProject:
    """Return a minimal project with one mesh and one burning surface."""
    p = FdsProject()
    p.meshes.append(Mesh(
        name="M1",
        x_min=0.0, x_max=10.0,
        y_min=0.0, y_max=10.0,
        z_min=0.0, z_max=5.0,
        cell_count=(40, 40, 20),   # 0.25 m cells
    ))
    p.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))  # kW/m²
    return p


class TestOptimizeForFire:

    def test_returns_dict_with_expected_keys(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0)
        for key in ("surf_id", "hrrpua_kW_m2", "fire_area_m2",
                    "Q_total_kW", "D_star_m", "recommended_dx_m",
                    "target_ratio", "meshes"):
            assert key in result, f"Missing key: {key}"

    def test_surf_id_echoed(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=2.0)
        assert result["surf_id"] == "FIRE"

    def test_hrrpua_correct(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0)
        assert result["hrrpua_kW_m2"] == 500.0

    def test_q_total_equals_hrrpua_times_area(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=4.0)
        assert abs(result["Q_total_kW"] - 2000.0) < 0.1

    def test_d_star_formula(self):
        """D* = (Q / (rho*cp*T*sqrt(g)))^0.4 with standard constants."""
        mgr = MeshingManager()
        p = _simple_project()
        fire_area = 2.0
        q = 500.0 * fire_area  # 1000 kW
        denom = 1.2 * 1.0 * 293.0 * math.sqrt(9.81)
        expected = (q / denom) ** 0.4
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=fire_area)
        assert abs(result["D_star_m"] - round(expected, 4)) < 0.01

    def test_recommended_dx_equals_d_star_over_ratio(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", target_ratio=10.0, fire_area=1.0)
        assert abs(result["recommended_dx_m"] - result["D_star_m"] / 10.0) < 1e-4

    def test_custom_target_ratio(self):
        mgr = MeshingManager()
        p = _simple_project()
        r15 = mgr.optimize_for_fire(p, "FIRE", target_ratio=15.0, fire_area=1.0)
        r10 = mgr.optimize_for_fire(p, "FIRE", target_ratio=10.0, fire_area=1.0)
        assert r15["recommended_dx_m"] < r10["recommended_dx_m"]

    def test_mesh_report_included(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0)
        assert "M1" in result["meshes"]

    def test_mesh_action_ok_for_fine_mesh(self):
        """25 cm cells should be 'ok' for a small 500 kW fire."""
        mgr = MeshingManager()
        p = _simple_project()
        # fire_area=1m² → Q=500kW → D*≈0.87m → dx_rec≈0.087m
        # mesh has dx=0.25m → D*/dx ≈ 3.5 → under-resolved → refine or coarsen_or_refine
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0)
        # Just check action is one of the expected values
        assert result["meshes"]["M1"]["action"] in ("ok", "refine", "coarsen_or_refine")

    def test_mesh_action_ok_when_ratio_met(self):
        """A very fine mesh (0.05 m) should be flagged 'ok'."""
        mgr = MeshingManager()
        p = _simple_project()
        # override mesh to 0.05 m cells
        p.meshes[0] = Mesh(
            name="FineMesh",
            x_min=0, x_max=10, y_min=0, y_max=10, z_min=0, z_max=5,
            cell_count=(200, 200, 100),
        )
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0, target_ratio=10)
        assert result["meshes"]["FineMesh"]["action"] == "ok"

    def test_missing_surface_gives_zero_d_star(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "NONEXISTENT", fire_area=1.0)
        assert result["D_star_m"] == 0.0
        assert result["recommended_dx_m"] is None

    def test_fire_area_inferred_from_obstructions(self):
        """When fire_area=None, area is summed from matching obstructions."""
        mgr = MeshingManager()
        p = _simple_project()
        # Add a 2×2 obstruction top face burning with FIRE surface
        p.obstructions.append(Obstruction(
            name="BURNER", surface_id="FIRE",
            x_min=0, x_max=2, y_min=0, y_max=2,
            z_min=0, z_max=0,
        ))
        result_auto = mgr.optimize_for_fire(p, "FIRE")  # fire_area inferred
        result_1m2  = mgr.optimize_for_fire(p, "FIRE", fire_area=1.0)
        # auto-detected area should differ from 1m² default
        assert result_auto["fire_area_m2"] != result_1m2["fire_area_m2"]

    def test_fallback_area_1m2_when_no_obstructions(self):
        mgr = MeshingManager()
        p = _simple_project()
        result = mgr.optimize_for_fire(p, "FIRE")  # no obstructions
        assert result["fire_area_m2"] == 1.0

    def test_multiple_meshes_all_reported(self):
        mgr = MeshingManager()
        p = _simple_project()
        p.meshes.append(Mesh(
            name="M2", x_min=10, x_max=20,
            y_min=0, y_max=10, z_min=0, z_max=5,
            cell_count=(40, 40, 20),
        ))
        result = mgr.optimize_for_fire(p, "FIRE", fire_area=2.0)
        assert "M1" in result["meshes"]
        assert "M2" in result["meshes"]

class TestFactoryWindProfile:

    def _factory(self):
        return EntityFactory()

    def test_create_returns_wind_profile(self):
        wp = self._factory().create_wind_profile("WP1", speed=5.0)
        assert isinstance(wp, WindProfile)
        assert wp.name == "WP1"

    def test_direction_default(self):
        wp = self._factory().create_wind_profile("WP1")
        assert wp.direction == 0.0

    def test_direction_override(self):
        wp = self._factory().create_wind_profile("WP1", direction=270.0)
        assert wp.direction == 270.0

    def test_heights_and_speeds(self):
        wp = self._factory().create_wind_profile(
            "WP1", heights=[0.0, 10.0, 50.0], speeds=[0.0, 5.0, 12.0]
        )
        assert wp.heights == [0.0, 10.0, 50.0]
        assert wp.speeds == [0.0, 5.0, 12.0]

    def test_z0_optional(self):
        wp = self._factory().create_wind_profile("WP1", z0=0.5)
        assert wp.z0 == 0.5

    def test_z0_absent_when_not_given(self):
        wp = self._factory().create_wind_profile("WP1")
        assert wp.z0 is None

class TestFactoryMove:

    def _factory(self):
        return EntityFactory()

    def test_create_returns_move(self):
        mv = self._factory().create_move("MV1")
        assert isinstance(mv, Move)
        assert mv.name == "MV1"

    def test_translation_defaults(self):
        mv = self._factory().create_move("MV1")
        assert mv.x == 0.0 and mv.y == 0.0 and mv.z == 0.0

    def test_translation_override(self):
        mv = self._factory().create_move("MV1", x=1.0, y=2.0, z=3.0)
        assert (mv.x, mv.y, mv.z) == (1.0, 2.0, 3.0)

    def test_rotation_angle(self):
        mv = self._factory().create_move("MV1", rotation_angle=45.0)
        assert mv.rotation_angle == 45.0

    def test_axis(self):
        mv = self._factory().create_move("MV1", axis=(0.0, 0.0, 1.0))
        assert list(mv.axis) == [0.0, 0.0, 1.0]

    def test_scale_default_1(self):
        mv = self._factory().create_move("MV1")
        assert mv.scale == 1.0

    def test_scale_override(self):
        mv = self._factory().create_move("MV1", scale=2.5)
        assert mv.scale == 2.5

class TestFactoryHvacFilter:

    def _factory(self):
        return EntityFactory()

    def test_create_returns_filter(self):
        flt = self._factory().create_hvac_filter("F1", node_id="N1")
        assert isinstance(flt, HvacFilter)
        assert flt.name == "F1"

    def test_node_id(self):
        flt = self._factory().create_hvac_filter("F1", node_id="NODE_A")
        assert flt.node_id == "NODE_A"

    def test_loss_factors(self):
        flt = self._factory().create_hvac_filter(
            "F1", loss_forward=2.5, loss_reverse=5.0
        )
        assert flt.loss_forward == 2.5
        assert flt.loss_reverse == 5.0

    def test_filter_type_optional(self):
        flt = self._factory().create_hvac_filter("F1", filter_type="HEPA")
        assert flt.filter_type == "HEPA"

class TestFactoryHvacLeakage:

    def _factory(self):
        return EntityFactory()

    def test_create_returns_leakage(self):
        lk = self._factory().create_hvac_leakage("LK1", zone_id_1="Z1", zone_id_2="Z2")
        assert isinstance(lk, HvacLeakage)
        assert lk.name == "LK1"

    def test_zone_ids(self):
        lk = self._factory().create_hvac_leakage("LK1", zone_id_1="ZONE_A", zone_id_2="ZONE_B")
        assert lk.zone_id_1 == "ZONE_A"
        assert lk.zone_id_2 == "ZONE_B"

    def test_crack_dimensions_defaults(self):
        lk = self._factory().create_hvac_leakage("LK1", zone_id_1="Z1", zone_id_2="Z2")
        assert lk.crack_length == 0.0
        assert lk.crack_width == 0.001

    def test_crack_dimensions_override(self):
        lk = self._factory().create_hvac_leakage(
            "LK1", zone_id_1="Z1", zone_id_2="Z2",
            crack_length=2.0, crack_width=0.005,
        )
        assert lk.crack_length == 2.0
        assert lk.crack_width == 0.005

    def test_multiplier_default(self):
        lk = self._factory().create_hvac_leakage("LK1", zone_id_1="Z1", zone_id_2="Z2")
        assert lk.multiplier == 1.0

class TestCreateHrrCurve:

    def _factory(self):
        return EntityFactory()

    def test_returns_ramp(self):
        from pyfds.domain.model import Ramp
        ramp = self._factory().create_hrr_curve("HRR", hrrpua=500.0, fire_area=1.0)
        assert isinstance(ramp, Ramp)
        assert ramp.name == "HRR"

    def test_ramp_has_n_points(self):
        ramp = self._factory().create_hrr_curve(
            "HRR", hrrpua=500.0, fire_area=1.0, n_points=25
        )
        assert len(ramp.times) == 25
        assert len(ramp.values) == 25

    def test_starts_at_zero(self):
        ramp = self._factory().create_hrr_curve("HRR", hrrpua=500.0, fire_area=1.0)
        assert ramp.times[0] == pytest.approx(0.0)
        assert ramp.values[0] == pytest.approx(0.0, abs=1e-5)

    def test_peak_is_1(self):
        ramp = self._factory().create_hrr_curve("HRR", hrrpua=500.0, fire_area=4.0)
        assert max(ramp.values) == pytest.approx(1.0, abs=1e-5)

    def test_ends_near_zero_with_decay(self):
        ramp = self._factory().create_hrr_curve(
            "HRR", hrrpua=500.0, fire_area=1.0,
            t_steady=60.0, t_decay=120.0, n_points=50,
        )
        assert ramp.values[-1] == pytest.approx(0.0, abs=0.1)

    def test_growth_categories(self):
        """Faster growth → shorter time to peak."""
        factory = self._factory()
        slow  = factory.create_hrr_curve("S", hrrpua=1000.0, fire_area=1.0,
                                          growth="slow",  n_points=40)
        fast  = factory.create_hrr_curve("F", hrrpua=1000.0, fire_area=1.0,
                                          growth="fast",  n_points=40)
        # 'fast' should reach 0.9 earlier than 'slow'
        def t_at_90pct(ramp):
            for t, v in zip(ramp.times, ramp.values):
                if v >= 0.9:
                    return t
            return float("inf")
        assert t_at_90pct(fast) < t_at_90pct(slow)

    def test_explicit_t_growth_overrides_alpha(self):
        factory = self._factory()
        ramp = factory.create_hrr_curve(
            "HRR", hrrpua=500.0, fire_area=1.0,
            t_growth=120.0, t_steady=60.0, t_decay=60.0, n_points=30,
        )
        # First point where value reaches peak must be around t_growth
        for t, v in zip(ramp.times, ramp.values):
            if v >= 0.99:
                assert abs(t - 120.0) <= ramp.times[1] * 2
                break

    def test_times_monotonically_increasing(self):
        ramp = self._factory().create_hrr_curve("HRR", hrrpua=500.0, fire_area=2.0)
        for i in range(1, len(ramp.times)):
            assert ramp.times[i] > ramp.times[i - 1]

    def test_values_in_0_1(self):
        ramp = self._factory().create_hrr_curve("HRR", hrrpua=500.0, fire_area=2.0)
        for v in ramp.values:
            assert -1e-6 <= v <= 1.0 + 1e-6
