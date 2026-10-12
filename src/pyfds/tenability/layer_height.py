"""
Smoke Layer Height
==================
Methods for estimating the smoke–clear-air interface height from
thermocouple-tree DEVC data and zone-model approximations.

References
----------
- He, Y. et al. (1998). Determination of interface height from measured
  parameter profile in enclosure fire experiment.
  Fire Safety Journal 31(1):19–38.
- SFPE Handbook, 5th ed., Chapter 36 (two-layer zone model).
- BS 7974-3:2003 — Structural response and fire spread beyond the enclosure
  of origin. §6.2 — Layer height determination.
- NFPA 92 (2021), §4.4 — Smoke filling.

N-Percent Rule (He et al., 1998)
---------------------------------
The smoke layer interface is at the elevation where the local temperature
excess first reaches N % of the maximum excess in the thermocouple column:

    T_interface = T_amb + (N/100) × (T_max − T_amb)

The standard value is N = 20 (20 % rule), widely adopted in BS 7974 and
SFPE practice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


# ── N-percent interface detection ─────────────────────────────────────────────

@dataclass(frozen=True)
class LayerHeightResult:
    """Result of a smoke-layer-height calculation at one instant."""
    z_interface: float       # m above floor — smoke layer interface
    T_interface: float       # K — temperature at interface
    T_upper: float           # K — average upper layer temperature
    T_lower: float           # K — average lower layer temperature
    layer_depth: float       # m — depth of smoke layer from ceiling
    method: str


def n_percent_interface(
    heights: Sequence[float],
    temperatures: Sequence[float],
    T_amb: float = 293.0,
    N: float = 20.0,
) -> LayerHeightResult:
    """
    Locate smoke–clear-air interface using the N-percent rule (He et al., 1998).

    Parameters
    ----------
    heights:      Thermocouple heights above floor [m], bottom to top.
    temperatures: Temperature at each thermocouple [K].
    T_amb:        Ambient temperature [K].
    N:            Percentage of maximum excess (default 20).

    Returns
    -------
    :class:`LayerHeightResult`

    Raises
    ------
    ValueError: If fewer than 2 measurement points are provided.
    """
    if len(heights) < 2 or len(temperatures) < 2:
        raise ValueError("Need at least 2 measurement points")
    if len(heights) != len(temperatures):
        raise ValueError("heights and temperatures must be the same length")

    T_max  = max(temperatures)
    T_thr  = T_amb + (N / 100.0) * (T_max - T_amb)

    # Scan from top downward; interface is where T drops below T_thr
    h_ceil = heights[-1]
    z_int  = heights[0]   # default: interface at floor (worst case)

    for i in range(len(heights) - 1, 0, -1):
        if temperatures[i] >= T_thr and temperatures[i - 1] < T_thr:
            # Linear interpolation
            dT = temperatures[i] - temperatures[i - 1]
            dz = heights[i]      - heights[i - 1]
            if abs(dT) > 1e-6:
                z_int = heights[i - 1] + (T_thr - temperatures[i - 1]) * dz / dT
            else:
                z_int = heights[i - 1]
            break
        elif temperatures[i] >= T_thr:
            z_int = heights[i]

    # Upper/lower layer averages
    T_upper_vals = [t for h, t in zip(heights, temperatures) if h >= z_int]
    T_lower_vals = [t for h, t in zip(heights, temperatures) if h < z_int]

    T_upper = sum(T_upper_vals) / len(T_upper_vals) if T_upper_vals else T_max
    T_lower = sum(T_lower_vals) / len(T_lower_vals) if T_lower_vals else T_amb

    return LayerHeightResult(
        z_interface=z_int,
        T_interface=T_thr,
        T_upper=T_upper,
        T_lower=T_lower,
        layer_depth=h_ceil - z_int,
        method=f"N-percent (N={N})",
    )


# ── Time-series layer height ───────────────────────────────────────────────────

@dataclass
class LayerHeightTimeSeries:
    """Smoke layer height over time from a thermocouple-tree DEVC set."""
    times:        List[float]   # s
    z_interface:  List[float]   # m above floor
    layer_depth:  List[float]   # m
    T_upper:      List[float]   # K
    T_lower:      List[float]   # K
    t_critical:   Optional[float]  # s when interface drops below threshold
    z_threshold:  float            # m — design threshold


def layer_height_timeseries(
    times_s: Sequence[float],
    heights: Sequence[float],
    temp_matrix: Sequence[Sequence[float]],
    T_amb: float = 293.0,
    N: float = 20.0,
    z_threshold: float = 2.0,
) -> LayerHeightTimeSeries:
    """
    Compute smoke layer height at each timestep from a thermocouple array.

    Parameters
    ----------
    times_s:      Time values [s].
    heights:      Thermocouple heights above floor [m] (fixed for all times).
    temp_matrix:  2-D array [time × height] of temperatures [K].
    T_amb:        Ambient temperature [K].
    N:            N-percent threshold (default 20).
    z_threshold:  Critical interface height [m] (e.g. 2.0 m for 2 m ASET).

    Returns
    -------
    :class:`LayerHeightTimeSeries`
    """
    z_list:  List[float] = []
    dep_list: List[float] = []
    T_up:   List[float] = []
    T_lo:   List[float] = []
    t_crit: Optional[float] = None

    for i, t in enumerate(times_s):
        temps = temp_matrix[i]
        result = n_percent_interface(list(heights), list(temps), T_amb, N)
        z_list.append(result.z_interface)
        dep_list.append(result.layer_depth)
        T_up.append(result.T_upper)
        T_lo.append(result.T_lower)

        if t_crit is None and result.z_interface < z_threshold:
            t_crit = float(t)

    return LayerHeightTimeSeries(
        times=list(times_s),
        z_interface=z_list,
        layer_depth=dep_list,
        T_upper=T_up,
        T_lower=T_lo,
        t_critical=t_crit,
        z_threshold=z_threshold,
    )


# ── Two-layer zone model approximation ───────────────────────────────────────

def zone_upper_temp(
    q_kw: float,
    m_plume: float,
    T_amb: float = 293.0,
    cp: float = 1.0,
) -> float:
    """
    Upper layer temperature [K] from energy balance (SFPE zone model).

        T_upper = T_amb + Q_c / (ṁ_plume · c_p)

    Parameters
    ----------
    q_kw:    Convective HRR [kW].
    m_plume: Plume mass flow rate [kg/s] at the interface.
    T_amb:   Ambient temperature [K].
    cp:      Specific heat [kJ/(kg·K)].
    """
    return T_amb + q_kw / max(m_plume * cp, 1e-6)


def descend_rate(
    q_kw: float,
    A_floor: float,
    z_int: float,
    rho_amb: float = 1.204,
    T_amb: float = 293.0,
    cp: float = 1.0,
    chi_r: float = 0.30,
) -> float:
    """
    Rate of smoke layer descent [m/s] (NFPA 92 / Zukoski filling).

        dz/dt = −ṁ_plume / (ρ_smoke · A_floor)

    Uses the Heskestad-based mass flow rate:
        ṁ = 0.071 · Q_c^(1/3) · z^(5/3)

    Parameters
    ----------
    q_kw:    Total HRR [kW].
    A_floor: Floor area [m²].
    z_int:   Current smoke layer interface height [m].
    """
    q_c    = q_kw * (1.0 - chi_r)
    m_dot  = 0.071 * q_c ** (1.0 / 3.0) * z_int ** (5.0 / 3.0)  # kg/s
    T_up   = zone_upper_temp(q_c, m_dot, T_amb, cp)
    rho_up = rho_amb * T_amb / T_up
    return -m_dot / max(rho_up * A_floor, 1e-6)   # negative = descending
