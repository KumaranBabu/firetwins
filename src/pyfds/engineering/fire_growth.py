"""
Fire Growth Models
==================
t-squared fire growth curves, HRR sizing, and RAMP generation for FDS.

References
----------
- SFPE Handbook of Fire Protection Engineering, 5th ed., Chapter 26 (Karlsson)
- NFPA 72 (2019), Table A.2.3.1.1 — t-squared growth coefficients
- Babrauskas, V. (2002). SFPE Chapter on ignition.

Growth coefficients α [kW/s²] are defined so that Q = α·t² reaches
Q_ref = 1055 kW (= 1000 BTU/s) at the characteristic time t_g [s].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class GrowthRate(str, Enum):
    SLOW       = "slow"
    MEDIUM     = "medium"
    FAST       = "fast"
    ULTRA_FAST = "ultra_fast"


# α = Q_ref / t_g²  where Q_ref = 1055 kW
_Q_REF: float = 1055.0  # kW (= 1000 BTU/s)

_T_G: dict[GrowthRate, float] = {
    GrowthRate.SLOW:       600.0,
    GrowthRate.MEDIUM:     300.0,
    GrowthRate.FAST:       150.0,
    GrowthRate.ULTRA_FAST:  75.0,
}

ALPHA: dict[GrowthRate, float] = {
    gr: _Q_REF / (t ** 2) for gr, t in _T_G.items()
}

# Typical HRRPUA values [kW/m²] from Babrauskas / SFPE Handbook
HRRPUA_DEFAULTS: dict[str, float] = {
    "wood_crib":         250.0,
    "cardboard":         300.0,
    "upholstered_chair": 400.0,
    "office_workstation": 350.0,
    "passenger_car":     1500.0,  # total HRR ~5-8 MW, per m² basis
    "retail_rack":       500.0,
    "hotel_room":        300.0,
}

# Convective fraction (1 - radiative); FDS default χ_r = 0.30
DEFAULT_RADIATIVE_FRACTION: float = 0.30
DEFAULT_CONVECTIVE_FRACTION: float = 1.0 - DEFAULT_RADIATIVE_FRACTION


@dataclass(frozen=True)
class FireGrowthResult:
    """Output of :func:`t_squared_hrr` or :func:`generate_hrr_curve`."""
    growth: GrowthRate
    alpha: float          # kW/s²
    t_g: float            # s — time to reach 1055 kW
    q_max: float          # kW
    t_at_q_max: float     # s
    fire_area: float      # m² (requires hrrpua)
    fire_diameter: float  # m
    hrr_convective: float # kW


def t_squared_hrr(
    t: float,
    growth: GrowthRate,
    q_max: Optional[float] = None,
) -> float:
    """
    HRR [kW] at time *t* [s] for a t-squared fire.

    Parameters
    ----------
    t:      Time [s] from ignition.
    growth: One of :class:`GrowthRate`.
    q_max:  Peak HRR cap [kW].  None → uncapped.
    """
    if t < 0:
        return 0.0
    q = ALPHA[growth] * t ** 2
    return min(q, q_max) if q_max is not None else q


def time_to_hrr(hrr_kw: float, growth: GrowthRate) -> float:
    """Time [s] for t-squared fire to reach *hrr_kw* [kW]."""
    if hrr_kw <= 0:
        return 0.0
    return math.sqrt(hrr_kw / ALPHA[growth])


def fire_area(hrr_kw: float, hrrpua: float) -> float:
    """Required fire area [m²] for *hrr_kw* [kW] at *hrrpua* [kW/m²]."""
    if hrrpua <= 0:
        raise ValueError("hrrpua must be > 0")
    return hrr_kw / hrrpua


def equivalent_diameter(area_m2: float) -> float:
    """Equivalent circular fire diameter [m] from plan area [m²]."""
    return math.sqrt(4.0 * area_m2 / math.pi)


def characterise_fire(
    hrr_kw: float,
    growth: GrowthRate = GrowthRate.FAST,
    hrrpua: float = 250.0,
    chi_r: float = DEFAULT_RADIATIVE_FRACTION,
) -> FireGrowthResult:
    """
    Compute key fire parameters from HRR and growth classification.

    Parameters
    ----------
    hrr_kw:  Peak heat release rate [kW].
    growth:  t-squared growth rate classification.
    hrrpua:  Heat release rate per unit area [kW/m²].
    chi_r:   Radiative fraction (default 0.30).
    """
    a = ALPHA[growth]
    t_peak = time_to_hrr(hrr_kw, growth)
    area = fire_area(hrr_kw, hrrpua)
    return FireGrowthResult(
        growth=growth,
        alpha=a,
        t_g=_T_G[growth],
        q_max=hrr_kw,
        t_at_q_max=t_peak,
        fire_area=area,
        fire_diameter=equivalent_diameter(area),
        hrr_convective=hrr_kw * (1.0 - chi_r),
    )


def generate_hrr_curve(
    growth: GrowthRate,
    q_max: float,
    t_end: float,
    t_steady: Optional[float] = None,
    t_decay_start: Optional[float] = None,
    t_decay_end: Optional[float] = None,
    dt: float = 10.0,
) -> List[Tuple[float, float]]:
    """
    Generate ``(time [s], HRR [kW])`` pairs suitable for an FDS RAMP entry.

    Growth phase: Q = α·t²  until Q_max is reached.
    Steady phase: Q = Q_max from *t_steady* onward (optional; default is
                  the time when the t² curve hits Q_max).
    Decay phase:  Linear decay from Q_max to 0 between *t_decay_start*
                  and *t_decay_end* (optional).
    """
    t_rise = time_to_hrr(q_max, growth)
    t_steady = t_steady or t_rise

    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    t = dt
    while t <= t_end:
        if t <= t_rise:
            q = t_squared_hrr(t, growth)
        elif t_decay_start is not None and t >= t_decay_start:
            if t_decay_end and t_decay_end > t_decay_start:
                frac = (t - t_decay_start) / (t_decay_end - t_decay_start)
                q = q_max * max(0.0, 1.0 - frac)
            else:
                q = 0.0
        else:
            q = q_max
        points.append((round(t, 2), round(q, 4)))
        t += dt

    if not points or points[-1][0] < t_end:
        points.append((t_end, 0.0 if (t_decay_end and t_end >= t_decay_end) else q_max))

    return points


def hrr_curve_for_fds_ramp(
    growth: GrowthRate,
    q_max: float,
    t_end: float,
    ramp_id: str = "HRR_RAMP",
    dt: float = 10.0,
) -> str:
    """
    Return an FDS-ready RAMP block string for the t-squared fire.

    Normalises HRR to 1.0 (use with HRRPUA or HEAT_OF_COMBUSTION).
    """
    curve = generate_hrr_curve(growth, q_max, t_end, dt=dt)
    lines = []
    for t, q in curve:
        f = q / q_max if q_max > 0 else 0.0
        lines.append(f"&RAMP ID='{ramp_id}', T={t:.1f}, F={f:.6f} /")
    return "\n".join(lines)
