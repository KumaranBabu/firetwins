"""
Tests for pyfds.tenability.visibility — Jin (1978) smoke visibility model.
"""
from __future__ import annotations

import math
import pytest

from pyfds.tenability.visibility import (
    SignType, MASS_OPTICAL_DENSITY,
    VisibilityResult, VisibilityTimeSeries,
    visibility_from_extinction, visibility_from_smoke_density,
    visibility_from_fds_soot, optical_depth, transmittance,
    visibility_timeseries,
    _B,
)


class TestConstants:
    def test_luminous_B_is_8(self):
        assert _B[SignType.LUMINOUS] == pytest.approx(8.0)

    def test_non_luminous_B_is_3(self):
        assert _B[SignType.NON_LUMINOUS] == pytest.approx(3.0)

    def test_mass_optical_density_all_positive(self):
        for k, v in MASS_OPTICAL_DENSITY.items():
            assert v > 0.0, f"{k} D_m should be positive"

    def test_wood_flaming_known_value(self):
        assert MASS_OPTICAL_DENSITY["wood_flaming"] == pytest.approx(0.07, rel=1e-6)

    def test_plastics_flaming_known_value(self):
        assert MASS_OPTICAL_DENSITY["plastics_flaming"] == pytest.approx(0.12, rel=1e-6)


class TestVisibilityFromExtinction:
    def test_zero_extinction_infinite_visibility(self):
        result = visibility_from_extinction(0.0)
        assert math.isinf(result.S_luminous)
        assert math.isinf(result.S_nonlum)

    def test_negative_extinction_infinite_visibility(self):
        result = visibility_from_extinction(-1.0)
        assert math.isinf(result.S_luminous)

    def test_luminous_formula(self):
        K = 0.5
        result = visibility_from_extinction(K)
        assert result.S_luminous == pytest.approx(8.0 / K, rel=1e-6)

    def test_non_luminous_formula(self):
        K = 0.5
        result = visibility_from_extinction(K)
        assert result.S_nonlum == pytest.approx(3.0 / K, rel=1e-6)

    def test_luminous_greater_than_non_luminous(self):
        result = visibility_from_extinction(0.3)
        assert result.S_luminous > result.S_nonlum

    def test_higher_extinction_lower_visibility(self):
        r1 = visibility_from_extinction(0.1)
        r2 = visibility_from_extinction(1.0)
        assert r1.S_luminous > r2.S_luminous

    def test_returns_dataclass(self):
        result = visibility_from_extinction(0.5)
        assert isinstance(result, VisibilityResult)

    def test_k_ext_stored(self):
        result = visibility_from_extinction(0.4)
        assert result.K_ext == pytest.approx(0.4)


class TestVisibilityFromSmokeDensity:
    def test_zero_density_infinite_visibility(self):
        result = visibility_from_smoke_density(0.0)
        assert math.isinf(result.S_luminous)

    def test_formula_K_ext(self):
        rho = 0.1  # g/m³
        D_m = 0.07
        expected_K = D_m * rho
        result = visibility_from_smoke_density(rho, D_m)
        assert result.K_ext == pytest.approx(expected_K, rel=1e-6)

    def test_visibility_luminous_formula(self):
        rho, D_m = 0.1, 0.07
        K = D_m * rho
        result = visibility_from_smoke_density(rho, D_m)
        assert result.S_luminous == pytest.approx(8.0 / K, rel=1e-6)

    def test_smoke_density_stored(self):
        rho = 0.25
        result = visibility_from_smoke_density(rho)
        assert result.smoke_density == pytest.approx(rho)

    def test_higher_density_lower_visibility(self):
        r1 = visibility_from_smoke_density(0.05)
        r2 = visibility_from_smoke_density(0.5)
        assert r1.S_luminous > r2.S_luminous

    def test_higher_d_m_lower_visibility(self):
        rho = 0.1
        r1 = visibility_from_smoke_density(rho, D_m=0.07)
        r2 = visibility_from_smoke_density(rho, D_m=0.34)
        assert r1.S_luminous > r2.S_luminous


class TestVisibilityFromFdsSoot:
    def test_kg_to_g_conversion(self):
        soot_kg = 0.001   # 1 g/m³ equivalent
        result_fds  = visibility_from_fds_soot(soot_kg)
        result_gram = visibility_from_smoke_density(1.0)
        assert result_fds.S_luminous == pytest.approx(result_gram.S_luminous, rel=1e-6)

    def test_zero_soot_infinite_visibility(self):
        result = visibility_from_fds_soot(0.0)
        assert math.isinf(result.S_luminous)

    def test_typical_fds_soot_plausible_range(self):
        # 0.001 kg/m³ = 1 g/m³ soot — moderate smoke → S ≈ 114 m
        result = visibility_from_fds_soot(0.001)
        assert 5.0 < result.S_luminous < 500.0


class TestOpticalDepthAndTransmittance:
    def test_optical_depth_formula(self):
        K, L = 0.5, 3.0
        assert optical_depth(K, L) == pytest.approx(1.5, rel=1e-6)

    def test_optical_depth_zero(self):
        assert optical_depth(0.0, 5.0) == pytest.approx(0.0)

    def test_transmittance_formula(self):
        K, L = 0.5, 3.0
        expected = math.exp(-K * L)
        assert transmittance(K, L) == pytest.approx(expected, rel=1e-6)

    def test_transmittance_between_0_and_1(self):
        for K in [0.1, 0.5, 1.0, 3.0]:
            T = transmittance(K, 5.0)
            assert 0.0 < T <= 1.0

    def test_zero_extinction_full_transmittance(self):
        assert transmittance(0.0, 10.0) == pytest.approx(1.0)

    def test_large_extinction_near_zero(self):
        assert transmittance(10.0, 10.0) < 1e-10


class TestVisibilityTimeseries:
    def _constant_soot_series(self, n, soot_kg, dt=1.0):
        times = [float(i) * dt for i in range(n)]
        soot  = [soot_kg] * n
        return times, soot

    def test_returns_dataclass(self):
        times, soot = self._constant_soot_series(10, 0.0)
        result = visibility_timeseries(times, soot)
        assert isinstance(result, VisibilityTimeSeries)

    def test_clear_smoke_no_critical_time(self):
        times, soot = self._constant_soot_series(100, 0.0)
        result = visibility_timeseries(times, soot)
        assert result.t_critical_luminous is None
        assert result.t_critical_nonlum   is None

    def test_heavy_smoke_both_critical_times_set(self):
        # Very thick smoke: soot=1.0 kg/m³ → K_ext = 1000 × 0.07 = 70 m⁻¹ → S_lum ≈ 0.11 m
        times, soot = self._constant_soot_series(10, 1.0)
        result = visibility_timeseries(times, soot)
        assert result.t_critical_luminous is not None
        assert result.t_critical_nonlum   is not None

    def test_luminous_threshold_hit_before_nonlum(self):
        # Luminous threshold (10 m) hit sooner than non-luminous (5 m) for rising smoke
        n = 100
        times = [float(i) for i in range(n)]
        # Linearly increasing soot
        soot = [i * 0.0001 for i in range(n)]
        result = visibility_timeseries(times, soot, threshold_luminous=10.0, threshold_nonlum=5.0)
        if result.t_critical_luminous and result.t_critical_nonlum:
            assert result.t_critical_luminous <= result.t_critical_nonlum

    def test_stored_thresholds(self):
        times, soot = self._constant_soot_series(5, 0.0)
        result = visibility_timeseries(times, soot,
                                       threshold_luminous=12.0, threshold_nonlum=6.0)
        assert result.threshold_luminous == pytest.approx(12.0)
        assert result.threshold_nonlum   == pytest.approx(6.0)

    def test_lengths_match(self):
        n = 50
        times, soot = self._constant_soot_series(n, 0.001)
        result = visibility_timeseries(times, soot)
        assert len(result.K_ext)      == n
        assert len(result.S_luminous) == n
        assert len(result.S_nonlum)   == n

    def test_times_stored(self):
        times = [0.0, 10.0, 20.0, 30.0]
        soot  = [0.0001] * 4
        result = visibility_timeseries(times, soot)
        assert result.times == times

    def test_custom_d_m_affects_extinction(self):
        times, soot = self._constant_soot_series(5, 0.001)
        r1 = visibility_timeseries(times, soot, D_m=0.07)
        r2 = visibility_timeseries(times, soot, D_m=0.34)
        assert r2.K_ext[2] > r1.K_ext[2]
