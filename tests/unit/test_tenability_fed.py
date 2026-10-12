"""
Tests for pyfds.tenability.fed — FED/FEC incapacitation model (ISO 13571).
"""
from __future__ import annotations

import pytest

from pyfds.tenability.fed import (
    FED_INCAPACITATION, FED_LETHALITY,
    fed_co_step, fed_hcn_step, fed_o2_step, fed_heat_step,
    calculate_fed, aset_margin, FEDResult,
    _CO_COEFF, _CO_DENOM, _HCN_COEFF, _HCN_DENOM,
    _VCO2_A, _VCO2_B, _VCO2_C,
)


class TestConstants:
    def test_incapacitation_below_lethality(self):
        assert FED_INCAPACITATION < FED_LETHALITY

    def test_incapacitation_is_0_3(self):
        assert FED_INCAPACITATION == pytest.approx(0.3)

    def test_lethality_is_1_0(self):
        assert FED_LETHALITY == pytest.approx(1.0)


class TestFedCoStep:
    def test_zero_co_returns_zero(self):
        assert fed_co_step(0.0, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_positive_co_positive_dose(self):
        assert fed_co_step(1000.0, 1.0) > 0.0

    def test_longer_exposure_higher_dose(self):
        d1 = fed_co_step(1000.0, 1.0)
        d2 = fed_co_step(1000.0, 2.0)
        assert d2 == pytest.approx(2.0 * d1, rel=1e-6)

    def test_formula_no_co2(self):
        import math
        ppm, dt = 1000.0, 5.0
        base = (ppm ** _CO_COEFF * dt) / _CO_DENOM
        vcо2 = max(1.0, math.exp(_VCO2_A * 0.0 + _VCO2_B) / _VCO2_C)
        expected = base * vcо2
        assert fed_co_step(ppm, dt) == pytest.approx(expected, rel=1e-6)

    def test_co2_hyperventilation_increases_dose(self):
        d_base = fed_co_step(1000.0, 1.0, pct_co2=0.0)
        d_co2  = fed_co_step(1000.0, 1.0, pct_co2=3.0)
        assert d_co2 > d_base

    def test_high_co_high_dose(self):
        # At 10,000 ppm CO × 30 min, FED should exceed incapacitation threshold
        dose = fed_co_step(10_000.0, 30.0)
        assert dose > FED_INCAPACITATION


class TestFedHcnStep:
    def test_zero_hcn_zero_dose(self):
        assert fed_hcn_step(0.0, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_positive_result(self):
        assert fed_hcn_step(100.0, 1.0) > 0.0

    def test_formula(self):
        ppm, dt = 50.0, 5.0
        expected = (ppm ** _HCN_COEFF * dt) / _HCN_DENOM
        assert fed_hcn_step(ppm, dt) == pytest.approx(expected, rel=1e-6)

    def test_linear_in_time(self):
        d1 = fed_hcn_step(50.0, 1.0)
        d2 = fed_hcn_step(50.0, 3.0)
        assert d2 == pytest.approx(3.0 * d1, rel=1e-6)


class TestFedO2Step:
    def test_normal_o2_no_dose(self):
        assert fed_o2_step(20.9, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_above_normal_no_dose(self):
        assert fed_o2_step(21.0, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_depleted_o2_positive_dose(self):
        assert fed_o2_step(10.0, 1.0) > 0.0

    def test_more_depleted_higher_dose(self):
        d1 = fed_o2_step(15.0, 1.0)
        d2 = fed_o2_step(10.0, 1.0)
        assert d2 > d1

    def test_linear_in_time(self):
        d1 = fed_o2_step(12.0, 1.0)
        d2 = fed_o2_step(12.0, 5.0)
        assert d2 == pytest.approx(5.0 * d1, rel=1e-6)


class TestFedHeatStep:
    def test_below_threshold_zero(self):
        assert fed_heat_step(50.0, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_at_threshold_zero(self):
        assert fed_heat_step(60.0, 1.0) == pytest.approx(0.0, abs=1e-12)

    def test_above_threshold_positive(self):
        assert fed_heat_step(100.0, 1.0) > 0.0

    def test_higher_temp_higher_dose(self):
        d1 = fed_heat_step(100.0, 1.0)
        d2 = fed_heat_step(200.0, 1.0)
        assert d2 > d1


class TestCalculateFed:
    def _constant_scenario(self, n, co_ppm, dt_s=1.0, o2_pct=20.9,
                           hcn=0.0, co2=0.0, temp=20.0):
        times  = [i * dt_s for i in range(n)]
        co     = [co_ppm] * n
        o2     = [o2_pct] * n
        hcn_l  = [hcn]    * n
        co2_l  = [co2]    * n
        temp_l = [temp]   * n
        return times, co, o2, hcn_l, co2_l, temp_l

    def test_returns_fed_result(self):
        times, co, o2, hcn, co2, temp = self._constant_scenario(10, 0.0)
        result = calculate_fed(times, co, o2, hcn, co2, temp)
        assert isinstance(result, FEDResult)

    def test_zero_co_no_incapacitation(self):
        times, co, o2, hcn, co2, temp = self._constant_scenario(3600, 0.0)
        result = calculate_fed(times, co, o2, hcn, co2, temp)
        assert result.t_incapacitation is None
        assert result.max_fed == pytest.approx(0.0, abs=1e-6)

    def test_high_co_causes_incapacitation(self):
        # 10,000 ppm CO continuously for 60 min
        times, co, o2, hcn, co2, temp = self._constant_scenario(3600, 10_000.0)
        result = calculate_fed(times, co)
        assert result.t_incapacitation is not None
        assert result.t_incapacitation > 0.0

    def test_fed_total_monotone(self):
        times, co, o2, hcn, co2, temp = self._constant_scenario(100, 5000.0)
        result = calculate_fed(times, co)
        for i in range(1, len(result.fed_total)):
            assert result.fed_total[i] >= result.fed_total[i - 1] - 1e-12

    def test_incapacitation_before_lethality(self):
        times, co, o2, hcn, co2, temp = self._constant_scenario(7200, 8000.0)
        result = calculate_fed(times, co)
        if result.t_incapacitation and result.t_lethality:
            assert result.t_incapacitation < result.t_lethality

    def test_fed_co_dominated(self):
        times = [float(i) for i in range(61)]
        co    = [5000.0] * 61
        result = calculate_fed(times, co)
        # With no O2 depletion or HCN, total FED should equal CO FED
        for i in range(len(times)):
            assert result.fed_total[i] == pytest.approx(result.fed_co[i], rel=1e-6)

    def test_o2_depletion_adds_dose(self):
        n = 1800
        times  = [float(i) for i in range(n)]
        co     = [500.0]  * n
        o2_dep = [10.0]   * n  # severe O2 depletion
        result_with    = calculate_fed(times, co, o2_pct=o2_dep)
        result_without = calculate_fed(times, co)
        assert result_with.max_fed > result_without.max_fed

    def test_times_stored(self):
        times = [0.0, 1.0, 2.0]
        result = calculate_fed(times, [0.0, 0.0, 0.0])
        assert result.times == times


class TestAsetMargin:
    def test_positive_margin(self):
        assert aset_margin(t_incapacitation=300.0, t_rset=200.0) == pytest.approx(100.0)

    def test_negative_margin(self):
        assert aset_margin(t_incapacitation=100.0, t_rset=200.0) == pytest.approx(-100.0)

    def test_none_incapacitation_infinite(self):
        import math
        assert math.isinf(aset_margin(None, t_rset=200.0))
