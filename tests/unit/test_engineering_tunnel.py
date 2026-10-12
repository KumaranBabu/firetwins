"""
Tests for pyfds.engineering.tunnel — critical velocity, spill plume, atrium filling.
"""
from __future__ import annotations

import pytest

from pyfds.engineering.tunnel import (
    critical_velocity, back_layering_length,
    bré_spill_plume, atrium_plume_mass_flow, smoke_filling_time,
    G, RHO, CP, T_0, K_G,
)


class TestCriticalVelocity:
    def test_positive_result(self):
        result = critical_velocity(q_kw=10_000.0, H=5.0, A=25.0)
        assert result.v_c > 0.0

    def test_returns_dataclass(self):
        from pyfds.engineering.tunnel import CriticalVelocityResult
        result = critical_velocity(1000.0, H=5.0, A=20.0)
        assert isinstance(result, CriticalVelocityResult)

    def test_larger_hrr_higher_velocity(self):
        r1 = critical_velocity(5_000.0,  H=5.0, A=25.0)
        r2 = critical_velocity(20_000.0, H=5.0, A=25.0)
        assert r2.v_c > r1.v_c

    def test_larger_area_lower_velocity(self):
        r1 = critical_velocity(10_000.0, H=5.0, A=15.0)
        r2 = critical_velocity(10_000.0, H=5.0, A=40.0)
        assert r1.v_c > r2.v_c

    def test_taller_tunnel_higher_velocity(self):
        r1 = critical_velocity(10_000.0, H=4.0, A=24.0)
        r2 = critical_velocity(10_000.0, H=6.0, A=24.0)
        assert r2.v_c > r1.v_c

    def test_typical_road_tunnel_10mw(self):
        # 10 MW fire in a 5m × 5m tunnel → Vc ≈ 2–4 m/s (NFPA 502 range)
        result = critical_velocity(q_kw=10_000.0, H=5.0, A=25.0)
        assert 1.0 < result.v_c < 6.0

    def test_fire_zone_temp_above_ambient(self):
        result = critical_velocity(10_000.0, H=5.0, A=25.0)
        assert result.T_fire > T_0

    def test_zero_q_gives_small_velocity(self):
        result = critical_velocity(q_kw=0.01, H=5.0, A=25.0)
        assert result.v_c >= 0.0

    def test_convective_fraction_applied(self):
        # chi_r=0 (all convective) → higher effective Q → higher Vc
        r1 = critical_velocity(5000.0, H=5.0, A=25.0, chi_r=0.30)
        r2 = critical_velocity(5000.0, H=5.0, A=25.0, chi_r=0.00)
        assert r2.v_c > r1.v_c


class TestBackLayering:
    def test_above_critical_no_layering(self):
        result = back_layering_length(10_000.0, H=5.0, A=25.0, v_applied=10.0)
        assert result.suppressed is True
        assert result.L_back == pytest.approx(0.0)

    def test_below_critical_positive_layering(self):
        # Ridiculously low velocity → back-layering present
        result = back_layering_length(10_000.0, H=5.0, A=25.0, v_applied=0.1)
        assert result.suppressed is False
        assert result.L_back > 0.0

    def test_layering_decreases_with_higher_v(self):
        v1_result = back_layering_length(10_000.0, H=5.0, A=25.0, v_applied=0.5)
        v2_result = back_layering_length(10_000.0, H=5.0, A=25.0, v_applied=1.5)
        if not v2_result.suppressed:
            assert v2_result.L_back < v1_result.L_back

    def test_critical_velocity_stored(self):
        result = back_layering_length(10_000.0, H=5.0, A=25.0, v_applied=1.0)
        direct = critical_velocity(10_000.0, H=5.0, A=25.0)
        assert result.v_critical == pytest.approx(direct.v_c, rel=0.01)


class TestBreSpillPlume:
    def test_positive_mass_flow(self):
        result = bré_spill_plume(q_kw=2000.0, W=10.0, z=5.0)
        assert result.M_dot > 0.0

    def test_increases_with_z(self):
        r1 = bré_spill_plume(2000.0, W=10.0, z=3.0)
        r2 = bré_spill_plume(2000.0, W=10.0, z=6.0)
        assert r2.M_dot > r1.M_dot

    def test_increases_with_width(self):
        r1 = bré_spill_plume(2000.0, W=5.0,  z=5.0)
        r2 = bré_spill_plume(2000.0, W=20.0, z=5.0)
        assert r2.M_dot > r1.M_dot

    def test_formula(self):
        q_kw, W, z = 2000.0, 10.0, 5.0
        q_c = q_kw * 0.70  # chi_r = 0.30
        expected = 0.36 * (q_c * W) ** (1 / 3) * z
        result = bré_spill_plume(q_kw, W, z)
        assert result.M_dot == pytest.approx(expected, rel=1e-5)

    def test_q_c_stored(self):
        result = bré_spill_plume(2000.0, W=10.0, z=5.0, chi_r=0.30)
        assert result.Q_c == pytest.approx(2000.0 * 0.70, rel=1e-5)


class TestAtriumPlumeMassFlow:
    def test_positive(self):
        m = atrium_plume_mass_flow(1000.0, z=5.0)
        assert m > 0.0

    def test_increases_with_z(self):
        m1 = atrium_plume_mass_flow(1000.0, z=3.0)
        m2 = atrium_plume_mass_flow(1000.0, z=6.0)
        assert m2 > m1

    def test_5_3_power_law(self):
        # ṁ ∝ z^(5/3): z doubles → ṁ × 2^(5/3)
        q_c = 1000.0 * 0.70
        m1 = atrium_plume_mass_flow(1000.0, z=2.0)
        m2 = atrium_plume_mass_flow(1000.0, z=4.0)
        assert m2 == pytest.approx(m1 * 2.0 ** (5 / 3), rel=0.02)

    def test_formula(self):
        q_kw, z = 1000.0, 5.0
        q_c = q_kw * 0.70
        expected = 0.071 * q_c ** (1 / 3) * z ** (5 / 3)
        assert atrium_plume_mass_flow(q_kw, z) == pytest.approx(expected, rel=1e-5)


class TestSmokeFilling:
    def test_positive_time(self):
        t = smoke_filling_time(500.0, volume=1000.0, A_floor=100.0,
                               H_room=10.0, z_interface=2.0)
        assert t > 0.0

    def test_interface_at_ceiling_zero_time(self):
        t = smoke_filling_time(500.0, volume=1000.0, A_floor=100.0,
                               H_room=10.0, z_interface=10.0)
        assert t == pytest.approx(0.0, abs=1e-6)

    def test_higher_hrr_faster_filling(self):
        t1 = smoke_filling_time(200.0,  volume=500.0, A_floor=50.0,
                                H_room=8.0, z_interface=2.0)
        t2 = smoke_filling_time(2000.0, volume=500.0, A_floor=50.0,
                                H_room=8.0, z_interface=2.0)
        assert t2 < t1

    def test_larger_floor_area_slower(self):
        t1 = smoke_filling_time(500.0, volume=500.0,  A_floor=50.0,
                                H_room=10.0, z_interface=2.0)
        t2 = smoke_filling_time(500.0, volume=2000.0, A_floor=200.0,
                                H_room=10.0, z_interface=2.0)
        assert t2 > t1
