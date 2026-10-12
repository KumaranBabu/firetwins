"""
PyFDS HVAC Network Flow Solver
================================
Linearised duct-network pressure/flow solver for pre-run HVAC diagnostics.

Uses the Hardy-Cross iterative method:
  - Each duct obeys the quadratic resistance law:  ΔP = R × Q |Q|
  - Fan pressure is treated as a negative resistance (source term)
  - Iterations continue until the maximum node flow imbalance < tolerance

This solver is purely diagnostic: it does **not** replace FDS's own
built-in HVAC solver (which runs inside the simulation).  Use it to:
  - Verify duct network connectivity
  - Estimate initial flow rates for design
  - Detect balance issues before submitting to FDS

Usage::

    from pyfds.domain.hvac_solver import HvacNetworkSolver

    solver  = HvacNetworkSolver(project)
    result  = solver.solve()
    print(result.summary())
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Air properties at 20 °C
_RHO_AIR = 1.2          # kg/m³
_NU_AIR  = 1.5e-5       # m²/s
_SMOOTH  = 0.0001       # default roughness (m)


@dataclass
class DuctFlowResult:
    duct_name: str
    flow_rate: float          # m³/s (positive = node1→node2)
    velocity: float           # m/s
    pressure_drop: float      # Pa (across duct, signed)
    reynolds: float
    friction_factor: float


@dataclass
class NodePressureResult:
    node_name: str
    pressure: float           # Pa (gauge)
    is_ambient: bool


@dataclass
class NetworkSolveResult:
    ducts: List[DuctFlowResult] = field(default_factory=list)
    nodes: List[NodePressureResult] = field(default_factory=list)
    converged: bool = False
    iterations: int = 0
    max_imbalance: float = float("inf")
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"HVAC Network Solve: {'CONVERGED' if self.converged else 'NOT CONVERGED'} "
            f"in {self.iterations} iterations  (max_imbalance={self.max_imbalance:.4g} m³/s)",
            "",
            f"{'Duct':<20} {'Flow(m³/s)':>12} {'Vel(m/s)':>10} {'ΔP(Pa)':>10}",
            "-" * 54,
        ]
        for dr in self.ducts:
            lines.append(
                f"{dr.duct_name:<20} {dr.flow_rate:>12.4f} {dr.velocity:>10.3f} "
                f"{dr.pressure_drop:>10.2f}"
            )
        lines += [
            "",
            f"{'Node':<20} {'Pressure(Pa)':>14} {'Ambient':>8}",
            "-" * 44,
        ]
        for nr in self.nodes:
            amb = "YES" if nr.is_ambient else ""
            lines.append(f"{nr.node_name:<20} {nr.pressure:>14.2f} {amb:>8}")
        if self.warnings:
            lines += ["", "Warnings:"]
            lines += [f"  ! {w}" for w in self.warnings]
        return "\n".join(lines)

    def duct(self, name: str) -> Optional[DuctFlowResult]:
        return next((d for d in self.ducts if d.duct_name == name), None)

    def node(self, name: str) -> Optional[NodePressureResult]:
        return next((n for n in self.nodes if n.node_name == name), None)


class HvacNetworkSolver:
    """
    Solve a pyfds HVAC duct network for steady-state pressure and flow.

    Parameters
    ----------
    project : FdsProject
        The project whose ``hvac_nodes``, ``hvac_ducts``, and ``fans``
        collections define the network.
    rho : float
        Air density in kg/m³ (default 1.2).
    max_iter : int
        Maximum Hardy-Cross iterations.
    tol : float
        Convergence tolerance: maximum allowed node flow imbalance (m³/s).
    """

    def __init__(
        self,
        project: Any,
        rho: float = _RHO_AIR,
        max_iter: int = 200,
        tol: float = 1e-5,
    ) -> None:
        self._project  = project
        self._rho      = rho
        self._max_iter = max_iter
        self._tol      = tol

    # ── Public API ────────────────────────────────────────────────────────────

    def solve(self) -> NetworkSolveResult:
        """Run the network solver and return a ``NetworkSolveResult``."""
        p = self._project
        result = NetworkSolveResult()

        nodes  = {n.name: n for n in p.hvac_nodes}
        ducts  = list(p.hvac_ducts)
        fans   = {f.duct_id: f for f in p.fans}

        if not nodes or not ducts:
            result.warnings.append("No HVAC nodes or ducts defined.")
            result.converged = True
            result.iterations = 0
            return result

        # Check at least one ambient node
        ambient = [n for n in p.hvac_nodes if n.ambient]
        if not ambient:
            result.warnings.append(
                "No AMBIENT node found — network may not converge. "
                "Set at least one &NODE AMBIENT=.TRUE."
            )

        # Build index
        node_names  = list(nodes.keys())
        n_nodes     = len(node_names)
        node_idx    = {nm: i for i, nm in enumerate(node_names)}
        n_ducts     = len(ducts)

        # Initial flow guess: uniform Q=0.1 m³/s per duct (fan direction positive)
        Q = [0.1 for _ in range(n_ducts)]

        # Compute duct resistance coefficients  R  so that  ΔP = R × Q |Q|
        R, areas = self._compute_resistances(ducts)

        # Fan source pressures (keyed by duct index)
        fan_dp: Dict[int, float] = {}
        for di, duct in enumerate(ducts):
            if duct.name in fans:
                fan_dp[di] = self._fan_pressure(fans[duct.name], Q[di])
            elif duct.duct_id if hasattr(duct, "duct_id") else False:
                pass
        # Also check fans by their duct_id referencing this duct name
        for fan in p.fans:
            for di, duct in enumerate(ducts):
                if fan.duct_id == duct.name:
                    fan_dp[di] = self._fan_pressure(fan, Q[di])

        # Hardy-Cross iteration
        for iteration in range(self._max_iter):
            max_imbalance = 0.0

            for di in range(n_ducts):
                duct = ducts[di]
                n1 = node_idx.get(duct.node_id_1)
                n2 = node_idx.get(duct.node_id_2)
                if n1 is None or n2 is None:
                    continue

                q = Q[di]
                dp_resistance = R[di] * q * abs(q)
                dp_fan = fan_dp.get(di, 0.0)
                dp_net = dp_resistance - dp_fan

                # Flow correction for this duct
                denom = 2.0 * R[di] * abs(q) if abs(q) > 1e-12 else 1e-6
                dQ = -dp_net / denom
                Q[di] += dQ * 0.5   # under-relaxation
                max_imbalance = max(max_imbalance, abs(dQ))

            result.iterations = iteration + 1
            result.max_imbalance = max_imbalance
            if max_imbalance < self._tol:
                result.converged = True
                break

        if not result.converged:
            result.warnings.append(
                f"Solver did not converge after {self._max_iter} iterations "
                f"(residual={result.max_imbalance:.3e}). Results are approximate."
            )

        # Compute node pressures via BFS from ambient (P=0 at ambient)
        pressures = self._compute_pressures(
            node_names, node_idx, ducts, Q, R, fan_dp, ambient
        )

        # Assemble result
        for di, duct in enumerate(ducts):
            q = Q[di]
            area = areas[di]
            vel = abs(q) / area if area > 0 else 0.0
            dp = R[di] * q * abs(q)
            re = vel * (duct.diameter or 0.5) / _NU_AIR
            f = self._friction_factor(re, duct.roughness or _SMOOTH, duct.diameter or 0.5)
            result.ducts.append(DuctFlowResult(
                duct_name=duct.name,
                flow_rate=q,
                velocity=vel,
                pressure_drop=dp,
                reynolds=re,
                friction_factor=f,
            ))

        for nm in node_names:
            result.nodes.append(NodePressureResult(
                node_name=nm,
                pressure=pressures.get(nm, 0.0),
                is_ambient=nodes[nm].ambient,
            ))

        return result

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _compute_resistances(
        self, ducts: list
    ) -> Tuple[List[float], List[float]]:
        """Compute Darcy-Weisbach resistance R for each duct."""
        R_list: List[float] = []
        A_list: List[float] = []
        for duct in ducts:
            D = duct.diameter or 0.5
            L = duct.length if duct.length is not None else 1.0
            eps = duct.roughness or _SMOOTH
            A = math.pi * D**2 / 4.0

            # Estimate friction factor at turbulent Re≈1e5
            f = self._friction_factor(1e5, eps, D)

            # Darcy-Weisbach: ΔP = f L/D × ρ/2A² × Q²
            R = f * L / D * self._rho / (2.0 * A**2) if A > 0 else 1.0

            # Add minor losses (entry + exit)
            loss_in, loss_out = (duct.loss if duct.loss else (0.0, 0.0))
            R += (loss_in + loss_out) * self._rho / (2.0 * A**2) if A > 0 else 0.0

            R_list.append(max(R, 1e-6))  # minimum resistance prevents division-by-zero
            A_list.append(A)

        return R_list, A_list

    @staticmethod
    def _friction_factor(re: float, eps: float, D: float) -> float:
        """Swamee-Jain explicit approximation to Colebrook-White equation."""
        if re < 1.0:
            return 64.0  # effectively blocked
        if re < 2300.0:
            return 64.0 / re   # laminar
        relative_roughness = eps / D if D > 0 else 0.0
        # Swamee-Jain: valid for 5e-6 < ε/D < 0.05 and 5e3 < Re < 1e8
        arg = relative_roughness / 3.7 + 5.74 / (re ** 0.9)
        if arg <= 0:
            return 0.02
        return 0.25 / (math.log10(arg)) ** 2

    @staticmethod
    def _fan_pressure(fan: Any, Q: float) -> float:
        """
        Estimate fan pressure at flow rate *Q* from pump-curve data or
        max_pressure / max_flow linear interpolation.
        """
        if getattr(fan, "volume_flow", None) and getattr(fan, "pressure", None):
            vf = fan.volume_flow
            pr = fan.pressure
            if len(vf) >= 2 and len(vf) == len(pr):
                # Linear interpolation
                q = abs(Q)
                if q <= vf[0]:
                    return float(pr[0])
                if q >= vf[-1]:
                    return float(pr[-1])
                for i in range(len(vf) - 1):
                    if vf[i] <= q <= vf[i + 1]:
                        t = (q - vf[i]) / (vf[i + 1] - vf[i])
                        return float(pr[i] + t * (pr[i + 1] - pr[i]))
        max_q  = getattr(fan, "max_flow", None) or 1.0
        max_dp = getattr(fan, "max_pressure", None) or 100.0
        vfr    = getattr(fan, "volume_flow_rate", None)
        if vfr is not None:
            # Constant-flow fan: return max_dp regardless of Q
            return float(max_dp)
        # Simple linear fan curve: ΔP = max_dp × (1 - Q/max_q)
        q = abs(Q)
        return float(max_dp * max(0.0, 1.0 - q / max_q))

    def _compute_pressures(
        self,
        node_names: List[str],
        node_idx: Dict[str, int],
        ducts: list,
        Q: List[float],
        R: List[float],
        fan_dp: Dict[int, float],
        ambient_nodes: list,
    ) -> Dict[str, float]:
        """BFS from ambient nodes to assign gauge pressures."""
        pressures: Dict[str, float] = {}
        for n in ambient_nodes:
            pressures[n.name] = 0.0

        adj: Dict[str, List[Tuple[str, float]]] = {nm: [] for nm in node_names}
        for di, duct in enumerate(ducts):
            n1, n2 = duct.node_id_1, duct.node_id_2
            if n1 not in adj or n2 not in adj:
                continue
            q = Q[di]
            dp_duct = R[di] * q * abs(q)
            dp_fan  = fan_dp.get(di, 0.0)
            net = dp_duct - dp_fan
            adj[n1].append((n2, -net))   # pressure drops from n1→n2
            adj[n2].append((n1,  net))

        # BFS
        queue = list(pressures.keys())
        visited: Set[str] = set(pressures.keys())
        while queue:
            cur = queue.pop(0)
            for neighbour, dp in adj.get(cur, []):
                if neighbour not in visited:
                    pressures[neighbour] = pressures[cur] + dp
                    visited.add(neighbour)
                    queue.append(neighbour)

        # Any unreached nodes get NaN
        for nm in node_names:
            if nm not in pressures:
                pressures[nm] = float("nan")

        return pressures
