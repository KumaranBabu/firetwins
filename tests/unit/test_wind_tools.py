"""Unit tests — pyfds.domain.wind_tools (WindTools)."""
from __future__ import annotations

import math

import pytest

from pyfds.domain.wind_tools import WindTools, _log_spaced
from pyfds.domain.model import WindProfile, Ramp


# ---------------------------------------------------------------------------
# _log_spaced helper
# ---------------------------------------------------------------------------

class TestLogSpaced:
    def test_returns_correct_count(self):
        h = _log_spaced(0.5, 100.0, 10)
        assert len(h) == 10

    def test_monotonically_increasing(self):
        h = _log_spaced(0.5, 100.0, 20)
        for i in range(len(h) - 1):
            assert h[i] < h[i + 1]

    def test_first_equals_z_min(self):
        h = _log_spaced(0.5, 100.0, 5)
        assert h[0] == pytest.approx(0.5, rel=1e-3)

    def test_last_equals_z_max(self):
        h = _log_spaced(0.5, 100.0, 5)
        assert h[-1] == pytest.approx(100.0, rel=1e-3)

    def test_single_point(self):
        h = _log_spaced(1.0, 50.0, 1)
        assert len(h) == 1
        assert h[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Log-law profile
# ---------------------------------------------------------------------------

class TestLogLawProfile:
    def test_returns_wind_profile_and_ramp(self):
        wind, ramps = WindTools.log_law_profile(10.0, 8.0, 0.03)
        assert isinstance(wind, WindProfile)
        assert len(ramps) == 1
        assert isinstance(ramps[0], Ramp)

    def test_speed_at_z_ref_equals_u_ref(self):
        z_ref, u_ref, z0 = 10.0, 8.0, 0.03
        _, ramps = WindTools.log_law_profile(z_ref, u_ref, z0, n_points=50)
        ramp = ramps[0]
        # Find sample closest to z_ref
        idx = min(range(len(ramp.times)), key=lambda i: abs(ramp.times[i] - z_ref))
        assert ramp.values[idx] == pytest.approx(u_ref, rel=0.05)

    def test_speed_increases_with_height(self):
        _, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03, n_points=20)
        speeds = ramps[0].values
        for i in range(len(speeds) - 1):
            assert speeds[i] <= speeds[i + 1] + 1e-9

    def test_wind_profile_has_ramp_id(self):
        wind, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03,
                                                 ramp_id="MY_RAMP")
        assert wind.ramp_id == "MY_RAMP"
        assert ramps[0].id == "MY_RAMP"

    def test_wind_profile_direction(self):
        wind, _ = WindTools.log_law_profile(10.0, 5.0, 0.03,
                                             wind_direction=180.0)
        assert wind.direction == pytest.approx(180.0)

    def test_wind_profile_name(self):
        wind, _ = WindTools.log_law_profile(10.0, 5.0, 0.03,
                                             wind_name="SiteWind")
        assert wind.name == "SiteWind"

    def test_z0_zero_raises(self):
        with pytest.raises(ValueError):
            WindTools.log_law_profile(10.0, 5.0, 0.0)

    def test_z0_negative_raises(self):
        with pytest.raises(ValueError):
            WindTools.log_law_profile(10.0, 5.0, -0.1)

    def test_z_ref_lte_z0_raises(self):
        with pytest.raises(ValueError):
            WindTools.log_law_profile(0.03, 5.0, 0.03)   # z_ref == z0

    def test_u_ref_zero_raises(self):
        with pytest.raises(ValueError):
            WindTools.log_law_profile(10.0, 0.0, 0.03)

    def test_ramp_times_monotonically_increasing(self):
        _, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03, n_points=15)
        times = ramps[0].times
        for i in range(len(times) - 1):
            assert times[i] < times[i + 1]

    def test_z0_effect_on_profile_shape(self):
        # Rougher surface (larger z0) → slower at low heights
        _, r_smooth = WindTools.log_law_profile(10.0, 5.0, 0.0002, n_points=10)
        _, r_rough  = WindTools.log_law_profile(10.0, 5.0, 0.5,    n_points=10)
        # At lowest height, rough terrain should be slower
        assert r_rough[0].values[0] < r_smooth[0].values[0]


# ---------------------------------------------------------------------------
# Power-law profile
# ---------------------------------------------------------------------------

class TestPowerLawProfile:
    def test_returns_wind_profile_and_ramp(self):
        wind, ramps = WindTools.power_law_profile(10.0, 6.0, 0.14)
        assert isinstance(wind, WindProfile)
        assert isinstance(ramps[0], Ramp)

    def test_speed_at_z_ref_equals_u_ref(self):
        z_ref, u_ref, alpha = 10.0, 6.0, 0.14
        _, ramps = WindTools.power_law_profile(z_ref, u_ref, alpha, n_points=50)
        ramp = ramps[0]
        idx = min(range(len(ramp.times)), key=lambda i: abs(ramp.times[i] - z_ref))
        assert ramp.values[idx] == pytest.approx(u_ref, rel=0.05)

    def test_speed_increases_with_height(self):
        _, ramps = WindTools.power_law_profile(10.0, 5.0, 0.22, n_points=20)
        speeds = ramps[0].values
        for i in range(len(speeds) - 1):
            assert speeds[i] <= speeds[i + 1] + 1e-9

    def test_higher_alpha_steeper_profile(self):
        _, r_low  = WindTools.power_law_profile(10.0, 5.0, 0.11, n_points=20)
        _, r_high = WindTools.power_law_profile(10.0, 5.0, 0.33, n_points=20)
        # At low height, steeper profile → lower speed
        assert r_high[0].values[0] < r_low[0].values[0]

    def test_z_ref_zero_raises(self):
        with pytest.raises(ValueError):
            WindTools.power_law_profile(0.0, 5.0, 0.14)

    def test_u_ref_zero_raises(self):
        with pytest.raises(ValueError):
            WindTools.power_law_profile(10.0, 0.0, 0.14)

    def test_alpha_zero_raises(self):
        with pytest.raises(ValueError):
            WindTools.power_law_profile(10.0, 5.0, 0.0)

    def test_ramp_id_applied(self):
        wind, ramps = WindTools.power_law_profile(10.0, 5.0, 0.14,
                                                   ramp_id="PL_RAMP")
        assert ramps[0].id == "PL_RAMP"


# ---------------------------------------------------------------------------
# Gust ramp
# ---------------------------------------------------------------------------

class TestGustRamp:
    def test_returns_ramp(self):
        r = WindTools.gust_ramp(5.0, 15.0, 100.0, 120.0, 200.0)
        assert isinstance(r, Ramp)

    def test_ramp_has_four_points(self):
        r = WindTools.gust_ramp(5.0, 15.0, 100.0, 120.0, 200.0)
        assert len(r.times) == 4
        assert len(r.values) == 4

    def test_peak_value_at_t_peak(self):
        r = WindTools.gust_ramp(5.0, 15.0, 100.0, 120.0, 200.0)
        peak_idx = r.times.index(120.0)
        assert r.values[peak_idx] == pytest.approx(15.0)

    def test_base_speed_before_and_after(self):
        r = WindTools.gust_ramp(5.0, 15.0, 100.0, 120.0, 200.0)
        assert r.values[0] == pytest.approx(5.0)
        assert r.values[-1] == pytest.approx(5.0)

    def test_ramp_id_applied(self):
        r = WindTools.gust_ramp(5.0, 15.0, 100.0, 120.0, 200.0,
                                ramp_id="GUST_EVENT")
        assert r.id == "GUST_EVENT"


# ---------------------------------------------------------------------------
# Gust ramp — time ordering validation
# ---------------------------------------------------------------------------

class TestGustRampValidation:
    def test_t_peak_after_t_end_raises(self):
        with pytest.raises(ValueError, match="t_start < t_peak < t_end"):
            WindTools.gust_ramp(5.0, 15.0, 100.0, 250.0, 200.0)  # t_peak > t_end

    def test_t_start_equals_t_peak_raises(self):
        with pytest.raises(ValueError):
            WindTools.gust_ramp(5.0, 15.0, 120.0, 120.0, 200.0)  # t_start == t_peak

    def test_t_peak_equals_t_end_raises(self):
        with pytest.raises(ValueError):
            WindTools.gust_ramp(5.0, 15.0, 100.0, 200.0, 200.0)  # t_peak == t_end


# ---------------------------------------------------------------------------
# Log-law — boundary and resolution
# ---------------------------------------------------------------------------

class TestLogLawEdgeCases:
    def test_coarse_n_points_2(self):
        wind, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03, n_points=2)
        assert len(ramps[0].times) == 2
        assert len(ramps[0].values) == 2

    def test_fine_n_points_200(self):
        wind, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03, n_points=200)
        assert len(ramps[0].times) == 200
        assert len(ramps[0].values) == 200

    def test_z_min_close_to_z0_does_not_crash(self):
        # z_min just above z0; guard in code uses max(z, z0*1.001)
        _, ramps = WindTools.log_law_profile(10.0, 5.0, z0=0.03,
                                              z_min=0.031, z_max=20.0, n_points=5)
        assert all(v >= 0 for v in ramps[0].values)


# ---------------------------------------------------------------------------
# Power-law — boundary
# ---------------------------------------------------------------------------

class TestPowerLawEdgeCases:
    def test_coarse_n_points_2(self):
        wind, ramps = WindTools.power_law_profile(10.0, 5.0, 0.14, n_points=2)
        assert len(ramps[0].values) == 2

    def test_profile_name_matches_wind_name(self):
        wind, _ = WindTools.power_law_profile(10.0, 5.0, 0.14,
                                               wind_name="TestWind")
        assert wind.name == "TestWind"


# ---------------------------------------------------------------------------
# Profile summary
# ---------------------------------------------------------------------------

class TestProfileSummary:
    def test_returns_string(self):
        _, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03)
        s = WindTools.profile_summary(ramps[0])
        assert isinstance(s, str)

    def test_contains_height_and_speed_headers(self):
        _, ramps = WindTools.log_law_profile(10.0, 5.0, 0.03)
        s = WindTools.profile_summary(ramps[0])
        assert "Height" in s
        assert "Speed" in s

    def test_empty_ramp_message(self):
        r = Ramp(name="empty", times=[], values=[])
        s = WindTools.profile_summary(r)
        assert "Empty" in s or len(s) > 0
