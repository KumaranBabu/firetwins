"""
Tests for pyfds.engineering.plumes — Alpert ceiling jet and Heskestad plume.
"""
from __future__ import annotations

import math
import pytest

from pyfds.engineering.plumes import (
    alpert_ceiling_jet, alpert_detector_r_max,
    heskestad_flame_height, heskestad_virtual_origin, heskestad_plume,
    sprinkler_rti, G, RHO, CP, T_AMB, CHI_R,
)


class TestAlpertCeilingJet:
    """Alpert (1972) ceiling jet — temperature and velocity."""

    def test_near_field_zone_label(self):
        result = alpert_ceiling_jet(q_kw=1000.0, H=3.0, r=0.1)
        assert result.zone == "near"

    def test_far_field_zone_label(self):
        # r/H = 1.0 > 0.18
        result = alpert_ceiling_jet(q_kw=1000.0, H=3.0, r=3.5)
        assert result.zone == "jet"

    def test_boundary_near_0_18(self):
        # r/H clearly below 0.18 → near; clearly above → jet
        result_near = alpert_ceiling_jet(q_kw=1000.0, H=4.0, r=4.0 * 0.15)
        assert result_near.zone == "near"
        result_jet = alpert_ceiling_jet(q_kw=1000.0, H=4.0, r=4.0 * 0.20)
        assert result_jet.zone == "jet"

    def test_near_field_delta_T_formula(self):
        q_kw, H = 1000.0, 3.0
        q_c = q_kw * (1.0 - CHI_R)
        expected = 16.9 * q_c ** (2 / 3) / H ** (5 / 3)
        result = alpert_ceiling_jet(q_kw, H, r=0.1)
        assert result.delta_T == pytest.approx(expected, rel=1e-6)

    def test_far_field_delta_T_formula(self):
        q_kw, H, r = 1000.0, 3.0, 5.0
        q_c = q_kw * (1.0 - CHI_R)
        expected = 5.38 * (q_c / r) ** (2 / 3) / H
        result = alpert_ceiling_jet(q_kw, H, r)
        assert result.delta_T == pytest.approx(expected, rel=1e-6)

    def test_near_field_velocity_formula(self):
        q_kw, H = 1000.0, 3.0
        q_c = q_kw * (1.0 - CHI_R)
        expected = 0.96 * (q_c / H) ** (1 / 3)
        result = alpert_ceiling_jet(q_kw, H, r=0.1)
        assert result.u_max == pytest.approx(expected, rel=1e-6)

    def test_delta_T_decreases_with_r(self):
        q_kw, H = 2000.0, 4.0
        prev = None
        for r in [2.0, 3.0, 5.0, 8.0]:
            res = alpert_ceiling_jet(q_kw, H, r)
            if prev is not None:
                assert res.delta_T < prev
            prev = res.delta_T

    def test_delta_T_increases_with_q(self):
        H, r = 3.0, 0.1
        r1 = alpert_ceiling_jet(500.0, H, r)
        r2 = alpert_ceiling_jet(2000.0, H, r)
        assert r2.delta_T > r1.delta_T

    def test_negative_H_raises(self):
        with pytest.raises(ValueError):
            alpert_ceiling_jet(1000.0, H=-1.0, r=1.0)

    def test_negative_r_raises(self):
        with pytest.raises(ValueError):
            alpert_ceiling_jet(1000.0, H=3.0, r=-0.5)

    def test_physics_1mw_3m_ceiling_near_axis(self):
        # 1 MW fire, 3 m ceiling, near axis: ΔT should be hundreds of K
        res = alpert_ceiling_jet(1000.0, H=3.0, r=0.5 * 3.0 * 0.18)
        assert res.delta_T > 100.0
        assert res.delta_T < 2000.0  # physically bounded

    def test_convective_fraction_applied(self):
        res_default = alpert_ceiling_jet(1000.0, H=3.0, r=0.1)
        res_no_rad  = alpert_ceiling_jet(1000.0, H=3.0, r=0.1, chi_r=0.0)
        # No radiation → higher convective HRR → higher ΔT
        assert res_no_rad.delta_T > res_default.delta_T


class TestAlpertDetectorRange:
    def test_returns_positive(self):
        r_max = alpert_detector_r_max(1000.0, H=3.0, delta_T_threshold=20.0)
        assert r_max > 0.0

    def test_higher_q_larger_range(self):
        r1 = alpert_detector_r_max(500.0,  H=3.0, delta_T_threshold=20.0)
        r2 = alpert_detector_r_max(2000.0, H=3.0, delta_T_threshold=20.0)
        assert r2 > r1

    def test_higher_threshold_smaller_range(self):
        r1 = alpert_detector_r_max(1000.0, H=3.0, delta_T_threshold=10.0)
        r2 = alpert_detector_r_max(1000.0, H=3.0, delta_T_threshold=50.0)
        assert r1 > r2


class TestHeskestadFlameHeight:
    def test_large_fire_positive(self):
        L = heskestad_flame_height(1000.0, D=1.0)
        assert L > 0.0

    def test_very_small_fire_clipped_to_zero(self):
        L = heskestad_flame_height(0.001, D=5.0)
        assert L == pytest.approx(0.0)

    def test_increases_with_hrr(self):
        L1 = heskestad_flame_height(500.0, D=1.0)
        L2 = heskestad_flame_height(2000.0, D=1.0)
        assert L2 > L1

    def test_1mw_1m_diameter(self):
        # Heskestad: L_f = -1.02×1 + 0.235×1000^0.4 = -1.02 + 3.73 = 2.71 m
        L = heskestad_flame_height(1000.0, D=1.0)
        assert L == pytest.approx(-1.02 * 1.0 + 0.235 * 1000.0 ** 0.4, rel=1e-5)

    def test_5mw_2m_diameter(self):
        L = heskestad_flame_height(5000.0, D=2.0)
        expected = max(0.0, -1.02 * 2.0 + 0.235 * 5000.0 ** 0.4)
        assert L == pytest.approx(expected, rel=1e-5)


class TestHeskestadVirtualOrigin:
    def test_formula(self):
        q, D = 1000.0, 1.0
        z0 = heskestad_virtual_origin(q, D)
        assert z0 == pytest.approx(-1.02 * D + 0.083 * q ** 0.4, rel=1e-6)

    def test_smaller_than_flame_height(self):
        for q in [100.0, 1000.0, 5000.0]:
            L = heskestad_flame_height(q, D=1.0)
            z0 = heskestad_virtual_origin(q, D=1.0)
            assert z0 < L


class TestHeskestadPlume:
    def test_above_flame_valid(self):
        result = heskestad_plume(1000.0, D=1.0, z=6.0)
        assert result.above_flame is True
        assert not math.isnan(result.delta_T_cl)
        assert result.delta_T_cl > 0.0

    def test_below_flame_invalid(self):
        result = heskestad_plume(1000.0, D=1.0, z=0.5)
        assert result.above_flame is False
        assert math.isnan(result.delta_T_cl)

    def test_temperature_decreases_with_height(self):
        for z1, z2 in [(5.0, 8.0), (8.0, 12.0)]:
            r1 = heskestad_plume(2000.0, D=1.5, z=z1)
            r2 = heskestad_plume(2000.0, D=1.5, z=z2)
            if r1.above_flame and r2.above_flame:
                assert r1.delta_T_cl > r2.delta_T_cl

    def test_velocity_decreases_with_height(self):
        r1 = heskestad_plume(2000.0, D=1.5, z=5.0)
        r2 = heskestad_plume(2000.0, D=1.5, z=10.0)
        if r1.above_flame and r2.above_flame:
            assert r1.u_cl > r2.u_cl

    def test_flame_height_returned(self):
        result = heskestad_plume(1000.0, D=1.0, z=6.0)
        expected_lf = heskestad_flame_height(1000.0, D=1.0)
        assert result.flame_height == pytest.approx(expected_lf, rel=1e-6)

    def test_virtual_origin_returned(self):
        result = heskestad_plume(1000.0, D=1.0, z=6.0)
        expected_z0 = heskestad_virtual_origin(1000.0, D=1.0)
        assert result.virtual_origin == pytest.approx(expected_z0, rel=1e-6)

    def test_5_3_power_law(self):
        # ΔT_cl ∝ (z - z0)^(-5/3): doubling (z-z0) reduces ΔT by 2^(5/3)
        q, D = 3000.0, 1.0
        z0 = heskestad_virtual_origin(q, D)
        z1, z2 = z0 + 2.0, z0 + 4.0
        r1 = heskestad_plume(q, D, z1)
        r2 = heskestad_plume(q, D, z2)
        if r1.above_flame and r2.above_flame:
            ratio = r1.delta_T_cl / r2.delta_T_cl
            assert ratio == pytest.approx(2.0 ** (5.0 / 3.0), rel=0.02)


class TestSprinklerRTI:
    def _constant_conditions(self, T_gas, u_gas, n_steps, dt):
        return [T_gas] * n_steps, [u_gas] * n_steps

    def test_no_activation_below_threshold(self):
        T_link = 293.0  # K ambient
        T_gas_list, u_list = self._constant_conditions(340.0, 0.5, 300, 1.0)
        result = sprinkler_rti(T_link, T_gas_list, u_list, dt=1.0,
                               rti=50.0, T_activation=347.15)
        assert result.t_activation is None

    def test_activation_at_high_temp(self):
        T_link = 293.0
        T_gas_list, u_list = self._constant_conditions(500.0, 2.0, 600, 1.0)
        result = sprinkler_rti(T_link, T_gas_list, u_list, dt=1.0,
                               rti=50.0, T_activation=347.15)
        assert result.t_activation is not None
        assert result.t_activation > 0.0

    def test_higher_rti_delays_activation(self):
        T_gas_list, u_list = self._constant_conditions(450.0, 1.0, 600, 1.0)
        r1 = sprinkler_rti(293.0, T_gas_list, u_list, dt=1.0, rti=50.0)
        r2 = sprinkler_rti(293.0, T_gas_list, u_list, dt=1.0, rti=200.0)
        if r1.t_activation and r2.t_activation:
            assert r2.t_activation > r1.t_activation

    def test_link_temp_increases_monotonically_without_cooling(self):
        T_gas_list = [450.0] * 100
        u_list     = [1.0]   * 100
        result = sprinkler_rti(293.0, T_gas_list, u_list, dt=1.0,
                               rti=500.0, T_activation=1000.0)
        assert result.T_link_final > 293.0
