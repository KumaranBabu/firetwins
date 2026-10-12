"""Unit tests — pyfds.domain.hvac_solver (HvacNetworkSolver)."""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pyfds.domain.hvac_solver import (
    HvacNetworkSolver,
    NetworkSolveResult,
    DuctFlowResult,
    NodePressureResult,
)


# ---------------------------------------------------------------------------
# Minimal project factory
# ---------------------------------------------------------------------------

def _node(name, ambient=False):
    return SimpleNamespace(name=name, ambient=ambient)


def _duct(name, n1, n2, diameter=0.3, length=5.0, roughness=0.0001, loss=None):
    return SimpleNamespace(
        name=name,
        node_id_1=n1,
        node_id_2=n2,
        diameter=diameter,
        length=length,
        roughness=roughness,
        loss=loss or (0.0, 0.0),
        duct_id=name,
    )


def _fan(duct_id, max_pressure=100.0, max_flow=1.0,
         volume_flow=None, pressure=None):
    return SimpleNamespace(
        duct_id=duct_id,
        max_pressure=max_pressure,
        max_flow=max_flow,
        volume_flow=volume_flow,
        pressure=pressure,
        volume_flow_rate=None,
    )


def _project(nodes, ducts, fans=None):
    return SimpleNamespace(
        hvac_nodes=nodes,
        hvac_ducts=ducts,
        fans=fans or [],
    )


# ---------------------------------------------------------------------------
# Empty / degenerate networks
# ---------------------------------------------------------------------------

class TestEmptyNetwork:
    def test_no_nodes_returns_converged(self):
        p = _project([], [])
        result = HvacNetworkSolver(p).solve()
        assert result.converged
        assert result.iterations == 0

    def test_no_nodes_warning(self):
        p = _project([], [])
        result = HvacNetworkSolver(p).solve()
        assert any("HVAC" in w or "nodes" in w.lower() for w in result.warnings)

    def test_no_ambient_node_warning(self):
        nodes = [_node("N1", ambient=False), _node("N2", ambient=False)]
        ducts = [_duct("D1", "N1", "N2")]
        p = _project(nodes, ducts)
        result = HvacNetworkSolver(p).solve()
        assert any("AMBIENT" in w.upper() or "ambient" in w.lower()
                   for w in result.warnings)


# ---------------------------------------------------------------------------
# Simple 2-node, 1-duct network (passive)
# ---------------------------------------------------------------------------

class TestSimpleNetwork:
    def _make_simple(self):
        nodes = [_node("ATM", ambient=True), _node("ROOM", ambient=False)]
        ducts = [_duct("DUCT1", "ATM", "ROOM", diameter=0.4, length=2.0)]
        return _project(nodes, ducts)

    def test_converges(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        assert result.converged

    def test_duct_result_present(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        assert len(result.ducts) == 1
        dr = result.ducts[0]
        assert isinstance(dr, DuctFlowResult)

    def test_node_results_present(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        assert len(result.nodes) == 2

    def test_ambient_node_pressure_zero(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        atm = result.node("ATM")
        assert atm is not None
        assert atm.pressure == pytest.approx(0.0, abs=1e-3)
        assert atm.is_ambient

    def test_duct_has_positive_flow(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        dr = result.duct("DUCT1")
        assert dr is not None
        assert abs(dr.flow_rate) > 0

    def test_positive_reynolds(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        dr = result.duct("DUCT1")
        assert dr.reynolds >= 0

    def test_positive_friction_factor(self):
        result = HvacNetworkSolver(self._make_simple()).solve()
        dr = result.duct("DUCT1")
        assert dr.friction_factor > 0


# ---------------------------------------------------------------------------
# Fan-driven network
# ---------------------------------------------------------------------------

class TestFanNetwork:
    def _make_fan_network(self, max_pressure=200.0):
        nodes = [_node("ATM", ambient=True), _node("SUPPLY", ambient=False)]
        ducts = [_duct("SUPPLY_DUCT", "ATM", "SUPPLY")]
        fans  = [_fan("SUPPLY_DUCT", max_pressure=max_pressure, max_flow=2.0)]
        return _project(nodes, ducts, fans)

    def test_converges_with_fan(self):
        result = HvacNetworkSolver(self._make_fan_network()).solve()
        assert result.converged

    def test_higher_fan_pressure_higher_flow(self):
        r_low  = HvacNetworkSolver(self._make_fan_network(max_pressure=50.0)).solve()
        r_high = HvacNetworkSolver(self._make_fan_network(max_pressure=500.0)).solve()
        q_low  = abs(r_low.duct("SUPPLY_DUCT").flow_rate)
        q_high = abs(r_high.duct("SUPPLY_DUCT").flow_rate)
        assert q_high > q_low

    def test_pump_curve_fan(self):
        nodes = [_node("A", ambient=True), _node("B", ambient=False)]
        ducts = [_duct("D", "A", "B")]
        fan = SimpleNamespace(
            duct_id="D",
            max_pressure=100.0,
            max_flow=1.0,
            volume_flow=[0.0, 0.5, 1.0],
            pressure=[200.0, 150.0, 0.0],
            volume_flow_rate=None,
        )
        p = _project(nodes, ducts, [fan])
        result = HvacNetworkSolver(p).solve()
        assert result.converged


# ---------------------------------------------------------------------------
# Friction factor
# ---------------------------------------------------------------------------

class TestFrictionFactor:
    def test_laminar_regime(self):
        from pyfds.domain.hvac_solver import HvacNetworkSolver
        f = HvacNetworkSolver._friction_factor(1000.0, 0.001, 0.3)
        assert f == pytest.approx(64.0 / 1000.0, rel=1e-6)

    def test_near_zero_re_returns_64(self):
        f = HvacNetworkSolver._friction_factor(0.5, 0.001, 0.3)
        assert f == pytest.approx(64.0)

    def test_turbulent_regime_reasonable(self):
        f = HvacNetworkSolver._friction_factor(1e5, 0.00005, 0.3)
        assert 0.005 < f < 0.1

    def test_smooth_pipe_lower_friction(self):
        f_smooth = HvacNetworkSolver._friction_factor(1e5, 1e-6, 0.3)
        f_rough  = HvacNetworkSolver._friction_factor(1e5, 0.01, 0.3)
        assert f_smooth < f_rough


# ---------------------------------------------------------------------------
# Fan pressure model
# ---------------------------------------------------------------------------

class TestFanPressure:
    def test_linear_at_zero_flow_returns_max(self):
        fan = _fan("D", max_pressure=200.0, max_flow=2.0)
        p = HvacNetworkSolver._fan_pressure(fan, Q=0.0)
        assert p == pytest.approx(200.0)

    def test_linear_at_max_flow_returns_zero(self):
        fan = _fan("D", max_pressure=200.0, max_flow=2.0)
        p = HvacNetworkSolver._fan_pressure(fan, Q=2.0)
        assert p == pytest.approx(0.0, abs=1.0)

    def test_pump_curve_interpolation(self):
        fan = SimpleNamespace(
            duct_id="D",
            volume_flow=[0.0, 1.0, 2.0],
            pressure=[300.0, 200.0, 0.0],
            max_pressure=300.0,
            max_flow=2.0,
            volume_flow_rate=None,
        )
        p_mid = HvacNetworkSolver._fan_pressure(fan, Q=1.0)
        assert p_mid == pytest.approx(200.0, abs=1.0)

    def test_pump_curve_extrapolate_below(self):
        fan = SimpleNamespace(
            duct_id="D",
            volume_flow=[0.5, 1.0],
            pressure=[100.0, 80.0],
            max_pressure=100.0,
            max_flow=1.0,
            volume_flow_rate=None,
        )
        p = HvacNetworkSolver._fan_pressure(fan, Q=0.0)
        assert p == pytest.approx(100.0)

    def test_pump_curve_extrapolate_above(self):
        fan = SimpleNamespace(
            duct_id="D",
            volume_flow=[0.0, 1.0],
            pressure=[100.0, 0.0],
            max_pressure=100.0,
            max_flow=1.0,
            volume_flow_rate=None,
        )
        p = HvacNetworkSolver._fan_pressure(fan, Q=2.0)
        assert p == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Three-node branching network
# ---------------------------------------------------------------------------

class TestThreeNodeNetwork:
    def _make_loop(self):
        nodes = [_node("ATM", ambient=True), _node("N1"), _node("N2")]
        ducts = [
            _duct("D1", "ATM", "N1"),
            _duct("D2", "N1",  "N2"),
            _duct("D3", "N2",  "ATM"),
        ]
        return _project(nodes, ducts)

    def test_loop_converges(self):
        result = HvacNetworkSolver(self._make_loop()).solve()
        assert result.converged

    def test_loop_has_three_duct_results(self):
        result = HvacNetworkSolver(self._make_loop()).solve()
        assert len(result.ducts) == 3

    def test_loop_flow_balance_at_internal_node(self):
        result = HvacNetworkSolver(self._make_loop()).solve()
        # Mass balance at N1: flow in = flow out (±tolerance)
        d1 = result.duct("D1")
        d2 = result.duct("D2")
        assert abs(d1.flow_rate - d2.flow_rate) < 1e-3


# ---------------------------------------------------------------------------
# Friction factor — extreme Reynolds
# ---------------------------------------------------------------------------

class TestFrictionFactorExtreme:
    def test_very_high_re_stays_in_range(self):
        f = HvacNetworkSolver._friction_factor(1e7, 0.0001, 0.3)
        assert 0.001 < f < 0.05

    def test_re_zero_returns_64(self):
        # Re = 0 → laminar formula gives f = 64/Re → clamped to 64
        f = HvacNetworkSolver._friction_factor(0.0, 0.001, 0.3)
        assert f == pytest.approx(64.0)

    def test_friction_factor_monotone_with_roughness(self):
        # Higher roughness → higher friction at the same Re
        f_smooth = HvacNetworkSolver._friction_factor(1e5, 1e-7, 0.3)
        f_rough  = HvacNetworkSolver._friction_factor(1e5, 0.05, 0.3)
        assert f_rough > f_smooth


# ---------------------------------------------------------------------------
# Non-convergence path
# ---------------------------------------------------------------------------

class TestNonConvergence:
    def test_non_convergence_warning(self):
        nodes = [_node("A", ambient=True), _node("B")]
        ducts = [_duct("D", "A", "B")]
        result = HvacNetworkSolver(
            _project(nodes, ducts), max_iter=1, tol=1e-15
        ).solve()
        assert not result.converged
        assert any("converge" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_string_contains_duct_name(self):
        nodes = [_node("ATM", ambient=True), _node("R1")]
        ducts = [_duct("MAIN_DUCT", "ATM", "R1")]
        result = HvacNetworkSolver(_project(nodes, ducts)).solve()
        summary = result.summary()
        assert "MAIN_DUCT" in summary

    def test_summary_contains_node_name(self):
        nodes = [_node("ATM", ambient=True), _node("ZONE1")]
        ducts = [_duct("D1", "ATM", "ZONE1")]
        result = HvacNetworkSolver(_project(nodes, ducts)).solve()
        assert "ZONE1" in result.summary()

    def test_summary_converged_text(self):
        nodes = [_node("A", ambient=True), _node("B")]
        ducts = [_duct("D", "A", "B")]
        result = HvacNetworkSolver(_project(nodes, ducts)).solve()
        assert "CONVERGED" in result.summary()

    def test_duct_lookup_helper(self):
        nodes = [_node("A", ambient=True), _node("B")]
        ducts = [_duct("MY_DUCT", "A", "B")]
        result = HvacNetworkSolver(_project(nodes, ducts)).solve()
        assert result.duct("MY_DUCT") is not None
        assert result.duct("NONEXISTENT") is None

    def test_node_lookup_helper(self):
        nodes = [_node("A", ambient=True), _node("B")]
        ducts = [_duct("D", "A", "B")]
        result = HvacNetworkSolver(_project(nodes, ducts)).solve()
        assert result.node("A") is not None
        assert result.node("MISSING") is None
