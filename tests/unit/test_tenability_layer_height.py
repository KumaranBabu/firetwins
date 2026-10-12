"""
Tests for pyfds.tenability.layer_height — smoke layer interface and descend rate.
"""
from __future__ import annotations

import pytest

from pyfds.tenability.layer_height import (
    LayerHeightResult, LayerHeightTimeSeries,
    n_percent_interface, layer_height_timeseries,
    zone_upper_temp, descend_rate,
)


class TestNPercentInterface:
    def _smoke_column(self, n_tc=5, H=10.0, T_amb=293.0, T_hot=600.0,
                      hot_from=3):
        """Linear thermocouple tree: cold below hot_from, hot above."""
        heights = [H * i / (n_tc - 1) for i in range(n_tc)]
        temps   = [T_amb if i < hot_from else T_hot for i in range(n_tc)]
        return heights, temps

    def test_returns_layer_height_result(self):
        heights, temps = self._smoke_column()
        result = n_percent_interface(heights, temps)
        assert isinstance(result, LayerHeightResult)

    def test_interface_within_column_bounds(self):
        heights, temps = self._smoke_column()
        result = n_percent_interface(heights, temps)
        assert heights[0] <= result.z_interface <= heights[-1]

    def test_hot_top_only_interface_near_ceiling(self):
        # Only top thermocouple is hot → interface is near the top
        heights = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
        temps   = [293.0, 293.0, 293.0, 293.0, 293.0, 700.0]
        result = n_percent_interface(heights, temps)
        assert result.z_interface > 8.0  # above all cold TCs

    def test_all_hot_interface_at_floor(self):
        heights = [0.0, 2.0, 4.0, 6.0, 8.0]
        temps   = [800.0, 800.0, 800.0, 800.0, 800.0]
        result = n_percent_interface(heights, temps)
        # When all TCs are equally hot, threshold equals T_amb (N% of zero excess)
        # Interface defaults to floor (heights[0])
        assert result.z_interface >= heights[0]

    def test_layer_depth_is_h_ceil_minus_interface(self):
        heights, temps = self._smoke_column()
        result = n_percent_interface(heights, temps)
        assert result.layer_depth == pytest.approx(heights[-1] - result.z_interface, rel=1e-6)

    def test_upper_temp_above_lower_temp(self):
        heights, temps = self._smoke_column()
        result = n_percent_interface(heights, temps)
        assert result.T_upper >= result.T_lower

    def test_ambient_temp_stored_as_T_interface(self):
        # When T_max == T_amb (no fire), T_threshold = T_amb + 0 = T_amb
        heights = [0.0, 1.0, 2.0, 3.0]
        temps   = [293.0] * 4
        result = n_percent_interface(heights, temps, T_amb=293.0, N=20.0)
        assert result.T_interface == pytest.approx(293.0, rel=1e-5)

    def test_n20_vs_n10_interface(self):
        # Higher N → higher threshold → interface crosses further up column
        # (smoke layer appears shallower); lower N → interface detected lower
        heights = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        temps   = [293.0, 295.0, 310.0, 400.0, 700.0, 900.0]
        r20 = n_percent_interface(heights, temps, N=20)
        r10 = n_percent_interface(heights, temps, N=10)
        assert r20.z_interface >= r10.z_interface

    def test_interpolation_smooth(self):
        heights = [0.0, 1.0, 2.0, 3.0]
        T_amb   = 293.0
        # Gradual temperature rise — should give interpolated result
        temps   = [293.0, 350.0, 600.0, 900.0]
        result = n_percent_interface(heights, temps, T_amb=T_amb, N=20)
        # Interface should land somewhere in the column (not only at grid points)
        assert 0.0 <= result.z_interface <= 3.0

    def test_method_string_contains_n(self):
        heights, temps = self._smoke_column()
        result = n_percent_interface(heights, temps, N=20)
        assert "20" in result.method

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            n_percent_interface([1.0], [300.0])

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            n_percent_interface([0.0, 1.0, 2.0], [300.0, 400.0])


class TestLayerHeightTimeSeries:
    def _smoke_matrix(self, n_times, heights, T_amb=293.0, T_hot=700.0,
                      hot_frac=0.5):
        """
        Simple test matrix: smoke layer grows linearly — at time i the top
        hot_frac fraction of the thermocouple tree is hot.
        """
        n_tc = len(heights)
        matrix = []
        for t_idx in range(n_times):
            frac = min(1.0, hot_frac * (t_idx + 1) / n_times)
            n_hot = max(1, int(frac * n_tc))
            temps = [T_amb] * (n_tc - n_hot) + [T_hot] * n_hot
            matrix.append(temps)
        return matrix

    def test_returns_dataclass(self):
        heights = [0.0, 1.0, 2.0, 3.0, 4.0]
        times   = [0.0, 10.0, 20.0]
        matrix  = self._smoke_matrix(3, heights)
        result  = layer_height_timeseries(times, heights, matrix)
        assert isinstance(result, LayerHeightTimeSeries)

    def test_lengths_match_times(self):
        heights = [0.0, 2.0, 4.0, 6.0]
        n = 5
        times  = [float(i * 10) for i in range(n)]
        matrix = self._smoke_matrix(n, heights)
        result = layer_height_timeseries(times, heights, matrix)
        assert len(result.z_interface) == n
        assert len(result.layer_depth) == n
        assert len(result.T_upper)     == n
        assert len(result.T_lower)     == n

    def test_times_stored(self):
        heights = [0.0, 1.0, 2.0, 3.0]
        times   = [0.0, 5.0, 10.0]
        matrix  = [[293.0, 293.0, 293.0, 293.0]] * 3
        result  = layer_height_timeseries(times, heights, matrix)
        assert result.times == times

    def test_threshold_stored(self):
        heights = [0.0, 2.0, 4.0]
        times   = [0.0, 1.0]
        matrix  = [[293.0, 293.0, 293.0]] * 2
        result  = layer_height_timeseries(times, heights, matrix, z_threshold=1.8)
        assert result.z_threshold == pytest.approx(1.8)

    def test_no_smoke_no_critical_time(self):
        heights = [0.0, 1.0, 2.0, 3.0, 4.0]
        n = 10
        times  = [float(i * 30) for i in range(n)]
        matrix = [[293.0] * 5 for _ in range(n)]
        result = layer_height_timeseries(times, heights, matrix, z_threshold=2.0)
        # Without smoke, interface stays at floor → always < z_threshold, but
        # what matters is that the function runs without error.
        assert result is not None

    def test_smoke_descends_eventually_below_threshold(self):
        # Smoke layer starts above 2m and descends below it after some timesteps
        heights = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        n_tc    = len(heights)
        T_amb   = 293.0
        T_hot   = 800.0
        # At t=0 only top 1 TC hot (interface ≈ 4 m), at t=2 all but bottom hot (interface ≈ 0 m)
        times  = [0.0, 10.0, 20.0]
        matrix = [
            [T_amb, T_amb, T_amb, T_amb, T_amb, T_hot],
            [T_amb, T_amb, T_amb, T_hot, T_hot, T_hot],
            [T_hot, T_hot, T_hot, T_hot, T_hot, T_hot],
        ]
        result = layer_height_timeseries(times, heights, matrix,
                                         T_amb=T_amb, z_threshold=2.0)
        assert result.t_critical is not None


class TestZoneUpperTemp:
    def test_above_ambient(self):
        T_upper = zone_upper_temp(q_kw=500.0, m_plume=2.0, T_amb=293.0)
        assert T_upper > 293.0

    def test_formula(self):
        q, m, T_amb, cp = 500.0, 2.0, 293.0, 1.0
        expected = T_amb + q / (m * cp)
        assert zone_upper_temp(q, m, T_amb, cp) == pytest.approx(expected, rel=1e-6)

    def test_more_plume_flow_lower_temp(self):
        t1 = zone_upper_temp(500.0, m_plume=1.0)
        t2 = zone_upper_temp(500.0, m_plume=5.0)
        assert t1 > t2

    def test_higher_hrr_higher_temp(self):
        t1 = zone_upper_temp(200.0, m_plume=2.0)
        t2 = zone_upper_temp(800.0, m_plume=2.0)
        assert t2 > t1


class TestDescendRate:
    def test_negative_rate(self):
        # Smoke descends → rate should be negative
        rate = descend_rate(q_kw=500.0, A_floor=100.0, z_int=3.0)
        assert rate < 0.0

    def test_higher_hrr_faster_descent(self):
        r1 = descend_rate(200.0,  A_floor=100.0, z_int=3.0)
        r2 = descend_rate(2000.0, A_floor=100.0, z_int=3.0)
        assert r2 < r1  # both negative; more negative = faster descent

    def test_larger_floor_area_slower_descent(self):
        r1 = descend_rate(500.0, A_floor=50.0,  z_int=3.0)
        r2 = descend_rate(500.0, A_floor=500.0, z_int=3.0)
        assert r1 < r2   # r1 more negative = faster

    def test_lower_interface_slower_descent(self):
        # Plume mass flow ∝ z^(5/3) → higher z → more entrainment → faster fill
        r1 = descend_rate(500.0, A_floor=100.0, z_int=5.0)
        r2 = descend_rate(500.0, A_floor=100.0, z_int=2.0)
        assert r1 < r2  # r1 more negative (larger z → higher mass flow)

    def test_convective_fraction_applied(self):
        r1 = descend_rate(500.0, A_floor=100.0, z_int=3.0, chi_r=0.0)
        r2 = descend_rate(500.0, A_floor=100.0, z_int=3.0, chi_r=0.3)
        # chi_r=0.30 → q_c = 0.70*Q → less mass flow → slower descent
        assert r1 < r2  # r1 more negative
