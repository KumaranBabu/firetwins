"""
Tests for pyfds.engineering.fire_growth — t-squared fire growth model.
"""
from __future__ import annotations

import math
import pytest

from pyfds.engineering.fire_growth import (
    GrowthRate, ALPHA, _Q_REF, _T_G,
    t_squared_hrr, time_to_hrr, fire_area, equivalent_diameter,
    characterise_fire, generate_hrr_curve, hrr_curve_for_fds_ramp,
    HRRPUA_DEFAULTS,
)


class TestGrowthCoefficients:
    def test_alpha_slow(self):
        assert ALPHA[GrowthRate.SLOW] == pytest.approx(_Q_REF / 600 ** 2, rel=1e-6)

    def test_alpha_medium(self):
        assert ALPHA[GrowthRate.MEDIUM] == pytest.approx(_Q_REF / 300 ** 2, rel=1e-6)

    def test_alpha_fast(self):
        assert ALPHA[GrowthRate.FAST] == pytest.approx(_Q_REF / 150 ** 2, rel=1e-6)

    def test_alpha_ultrafast(self):
        assert ALPHA[GrowthRate.ULTRA_FAST] == pytest.approx(_Q_REF / 75 ** 2, rel=1e-6)

    def test_all_growth_rates_present(self):
        for gr in GrowthRate:
            assert gr in ALPHA

    def test_alpha_ordering(self):
        assert (ALPHA[GrowthRate.SLOW] < ALPHA[GrowthRate.MEDIUM]
                < ALPHA[GrowthRate.FAST] < ALPHA[GrowthRate.ULTRA_FAST])


class TestTSquaredHRR:
    def test_zero_at_ignition(self):
        for gr in GrowthRate:
            assert t_squared_hrr(0.0, gr) == pytest.approx(0.0)

    def test_negative_time_returns_zero(self):
        assert t_squared_hrr(-10.0, GrowthRate.FAST) == 0.0

    def test_q_ref_at_tg(self):
        for gr in GrowthRate:
            q = t_squared_hrr(_T_G[gr], gr)
            assert q == pytest.approx(_Q_REF, rel=1e-4)

    def test_quadratic_growth(self):
        t = 100.0
        q1 = t_squared_hrr(t, GrowthRate.FAST)
        q2 = t_squared_hrr(2 * t, GrowthRate.FAST)
        assert q2 == pytest.approx(4.0 * q1, rel=1e-6)

    def test_cap_respected(self):
        q = t_squared_hrr(1000.0, GrowthRate.FAST, q_max=500.0)
        assert q == pytest.approx(500.0)

    def test_cap_not_applied_below(self):
        # At t=1s, fast fire: Q = 0.04689 kW — well below cap of 500 kW
        q = t_squared_hrr(1.0, GrowthRate.FAST, q_max=500.0)
        assert q == pytest.approx(ALPHA[GrowthRate.FAST] * 1.0, rel=1e-6)

    def test_ultra_fast_faster_than_fast(self):
        t = 60.0
        assert t_squared_hrr(t, GrowthRate.ULTRA_FAST) > t_squared_hrr(t, GrowthRate.FAST)


class TestTimeToHRR:
    def test_zero_hrr(self):
        assert time_to_hrr(0.0, GrowthRate.FAST) == pytest.approx(0.0)

    def test_round_trip_tg(self):
        for gr in GrowthRate:
            t = time_to_hrr(_Q_REF, gr)
            assert t == pytest.approx(_T_G[gr], rel=1e-4)

    def test_1mw_fast_fire(self):
        t = time_to_hrr(1000.0, GrowthRate.FAST)
        assert t == pytest.approx(math.sqrt(1000.0 / ALPHA[GrowthRate.FAST]), rel=1e-6)

    def test_ultrafast_reaches_1mw_faster(self):
        t_fast  = time_to_hrr(1000.0, GrowthRate.FAST)
        t_ultra = time_to_hrr(1000.0, GrowthRate.ULTRA_FAST)
        assert t_ultra < t_fast


class TestFireAreaAndDiameter:
    def test_fire_area_basic(self):
        assert fire_area(500.0, 250.0) == pytest.approx(2.0)

    def test_fire_area_zero_hrrpua_raises(self):
        with pytest.raises(ValueError):
            fire_area(500.0, 0.0)

    def test_diameter_from_area(self):
        area = 4.0  # m²
        d = equivalent_diameter(area)
        assert d == pytest.approx(math.sqrt(4.0 * 4.0 / math.pi), rel=1e-6)

    def test_diameter_unit_circle(self):
        # area = π/4 → d = 1 m
        assert equivalent_diameter(math.pi / 4.0) == pytest.approx(1.0, rel=1e-5)


class TestCharacteriseFire:
    def test_returns_result(self):
        r = characterise_fire(1000.0, GrowthRate.FAST)
        assert r.q_max == pytest.approx(1000.0)
        assert r.growth == GrowthRate.FAST

    def test_convective_hrr_default_chi_r(self):
        r = characterise_fire(1000.0, GrowthRate.FAST)
        assert r.hrr_convective == pytest.approx(700.0, rel=1e-5)

    def test_fire_area_matches_hrrpua(self):
        r = characterise_fire(500.0, hrrpua=250.0)
        assert r.fire_area == pytest.approx(2.0)

    def test_fire_diameter_positive(self):
        r = characterise_fire(2000.0)
        assert r.fire_diameter > 0.0

    def test_t_at_q_max_consistent(self):
        r = characterise_fire(1000.0, GrowthRate.MEDIUM)
        q_check = t_squared_hrr(r.t_at_q_max, GrowthRate.MEDIUM)
        assert q_check == pytest.approx(1000.0, rel=1e-4)


class TestGenerateHRRCurve:
    def test_starts_at_zero(self):
        curve = generate_hrr_curve(GrowthRate.FAST, 1000.0, 600.0)
        assert curve[0] == (0.0, 0.0)

    def test_growth_phase_quadratic(self):
        curve = generate_hrr_curve(GrowthRate.FAST, 5000.0, 200.0, dt=10.0)
        # At t=10s: q = α × 100
        expected_10 = ALPHA[GrowthRate.FAST] * 100.0
        t10_point = next(p for p in curve if p[0] == 10.0)
        assert t10_point[1] == pytest.approx(expected_10, rel=1e-4)

    def test_steady_phase_capped(self):
        q_max = 100.0
        curve = generate_hrr_curve(GrowthRate.ULTRA_FAST, q_max, 300.0, dt=10.0)
        # After fire reaches q_max, all points should be ≤ q_max
        for t, q in curve:
            assert q <= q_max + 1e-6

    def test_monotone_until_peak(self):
        curve = generate_hrr_curve(GrowthRate.FAST, 5000.0, 300.0, dt=10.0)
        t_peak = time_to_hrr(5000.0, GrowthRate.FAST)
        for i in range(1, len(curve)):
            if curve[i][0] <= t_peak:
                assert curve[i][1] >= curve[i - 1][1] - 1e-6

    def test_decay_reaches_zero(self):
        curve = generate_hrr_curve(
            GrowthRate.FAST, 1000.0, 600.0,
            t_decay_start=300.0, t_decay_end=600.0, dt=10.0,
        )
        final_q = curve[-1][1]
        assert final_q == pytest.approx(0.0, abs=1.0)


class TestFdsRampOutput:
    def test_ramp_string_format(self):
        s = hrr_curve_for_fds_ramp(GrowthRate.FAST, 1000.0, 200.0, ramp_id="FIRE")
        assert "&RAMP ID='FIRE'" in s
        assert "T=0.0" in s
        assert "F=0.000000" in s

    def test_normalised_to_one_at_peak(self):
        s = hrr_curve_for_fds_ramp(GrowthRate.FAST, 1000.0, 200.0)
        lines = s.strip().split("\n")
        f_values = []
        for line in lines:
            for part in line.split(","):
                if "F=" in part:
                    f_values.append(float(part.strip().split("=")[1].split()[0]))
        assert max(f_values) == pytest.approx(1.0, abs=0.01)


class TestHRRPUADefaults:
    def test_all_positive(self):
        for k, v in HRRPUA_DEFAULTS.items():
            assert v > 0, f"{k} HRRPUA should be > 0"
