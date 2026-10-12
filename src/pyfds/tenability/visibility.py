"""
Smoke Visibility
================
Visibility through smoke using the Jin (1978) extinction-coefficient model
and mass optical density approach.

References
----------
- Jin, T. (1978). Visibility through fire smoke. Journal of Fire &
  Flammability 9:135–157.
- Jin, T. (1997). Studies on human behaviour and tenability in fire smoke.
  Proc. 5th Int. Symp. on Fire Safety Science, pp. 3–21.
- SFPE Handbook, 5th ed., Chapter 64 (Mulholland & Croarkin).
- BS 7974-6:2004, §7.4 — Visibility.
- NFPA 92 (2021), Annex A — Visibility.

Visibility Model
----------------
S = B / K_ext   [m]

where:
  B      = illuminance constant (8 for light-emitting signs,
            3 for light-reflecting signs / non-luminous objects)
  K_ext  = light extinction coefficient [m⁻¹]

The extinction coefficient is related to smoke concentration by:
  K_ext = D_m · ρ_smoke   [m⁻¹]

where:
  D_m      = mass optical density [m²/g]
  ρ_smoke  = smoke density [g/m³]

Typical D_m values (SFPE Handbook, Table 64.1):
  Flaming combustion (wood):  0.07 m²/g
  Flaming combustion (plastics): 0.12 m²/g
  Smoldering (wood):          0.10 m²/g
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence


class SignType(str, Enum):
    """Illuminance constant B for the Jin visibility model."""
    LUMINOUS     = "luminous"      # B = 8 (self-illuminated exit signs)
    NON_LUMINOUS = "non_luminous"  # B = 3 (non-illuminated objects/signs)


_B: dict[SignType, float] = {
    SignType.LUMINOUS:     8.0,
    SignType.NON_LUMINOUS: 3.0,
}

# Mass optical density [m²/g] — SFPE Handbook Table 64.1
MASS_OPTICAL_DENSITY: dict[str, float] = {
    "wood_flaming":       0.07,
    "wood_smoldering":    0.10,
    "plastics_flaming":   0.12,
    "polyurethane_foam":  0.19,
    "polystyrene":        0.34,
    "pmma":               0.10,
}


@dataclass(frozen=True)
class VisibilityResult:
    """Visibility calculation output."""
    K_ext: float       # m⁻¹ — extinction coefficient
    S_luminous: float  # m — visibility to luminous signs
    S_nonlum:   float  # m — visibility to non-luminous signs / objects
    smoke_density: float  # g/m³


def visibility_from_extinction(K_ext: float) -> VisibilityResult:
    """
    Compute visibility [m] from extinction coefficient *K_ext* [m⁻¹].

    Returns visibility for both sign types.
    """
    if K_ext <= 0:
        inf = float("inf")
        return VisibilityResult(K_ext=0.0, S_luminous=inf, S_nonlum=inf,
                                smoke_density=0.0)
    return VisibilityResult(
        K_ext=K_ext,
        S_luminous=_B[SignType.LUMINOUS]     / K_ext,
        S_nonlum  =_B[SignType.NON_LUMINOUS] / K_ext,
        smoke_density=float("nan"),
    )


def visibility_from_smoke_density(
    rho_smoke: float,
    D_m: float = MASS_OPTICAL_DENSITY["wood_flaming"],
) -> VisibilityResult:
    """
    Compute visibility from smoke concentration.

    Parameters
    ----------
    rho_smoke: Smoke density [g/m³] (soot or total particulate).
    D_m:       Mass optical density [m²/g].
    """
    K_ext = D_m * rho_smoke
    result = visibility_from_extinction(K_ext)
    return VisibilityResult(
        K_ext=result.K_ext,
        S_luminous=result.S_luminous,
        S_nonlum=result.S_nonlum,
        smoke_density=rho_smoke,
    )


def visibility_from_fds_soot(
    soot_density_kg_m3: float,
    D_m: float = MASS_OPTICAL_DENSITY["wood_flaming"],
) -> VisibilityResult:
    """
    Visibility from FDS SOOT DENSITY output [kg/m³].

    Converts kg/m³ → g/m³ before applying the Jin model.
    """
    return visibility_from_smoke_density(soot_density_kg_m3 * 1000.0, D_m)


# ── Optical depth / path length ───────────────────────────────────────────────

def optical_depth(K_ext: float, path_length: float) -> float:
    """
    Optical depth (Beer-Lambert law): τ = K_ext · L.

    Parameters
    ----------
    K_ext:       Extinction coefficient [m⁻¹].
    path_length: Light path length [m].
    """
    return K_ext * path_length


def transmittance(K_ext: float, path_length: float) -> float:
    """Fractional transmittance: T = exp(−K_ext · L)."""
    return math.exp(-optical_depth(K_ext, path_length))


# ── Time-series visibility from DEVC data ────────────────────────────────────

@dataclass
class VisibilityTimeSeries:
    """Time-resolved visibility from a soot-density DEVC channel."""
    times:      List[float]
    K_ext:      List[float]
    S_luminous: List[float]  # m
    S_nonlum:   List[float]  # m
    t_critical_luminous:  Optional[float]   # s when S < threshold
    t_critical_nonlum:    Optional[float]   # s
    threshold_luminous:   float             # m
    threshold_nonlum:     float             # m


def visibility_timeseries(
    times_s: Sequence[float],
    soot_kg_m3: Sequence[float],
    D_m: float = MASS_OPTICAL_DENSITY["wood_flaming"],
    threshold_luminous: float = 10.0,
    threshold_nonlum:   float = 5.0,
) -> VisibilityTimeSeries:
    """
    Compute visibility time-series from FDS soot-density DEVC output.

    Parameters
    ----------
    times_s:            Times [s].
    soot_kg_m3:         FDS SOOT DENSITY [kg/m³] at each time.
    D_m:                Mass optical density [m²/g].
    threshold_luminous: Visibility threshold for luminous signs [m] (default 10 m).
    threshold_nonlum:   Visibility threshold for non-luminous objects [m] (default 5 m).

    Notes
    -----
    NFPA 92 (2021) Annex A uses 10 m for signage and 5 m for wayfinding as
    conservative design thresholds.
    """
    K_list: List[float] = []
    S_lum:  List[float] = []
    S_nl:   List[float] = []
    t_crit_lum = None
    t_crit_nl  = None

    for i, soot in enumerate(soot_kg_m3):
        res = visibility_from_fds_soot(soot, D_m)
        K_list.append(res.K_ext)
        S_lum.append(res.S_luminous)
        S_nl.append(res.S_nonlum)

        if t_crit_lum is None and res.S_luminous < threshold_luminous:
            t_crit_lum = float(times_s[i])
        if t_crit_nl is None and res.S_nonlum < threshold_nonlum:
            t_crit_nl = float(times_s[i])

    return VisibilityTimeSeries(
        times=list(times_s),
        K_ext=K_list,
        S_luminous=S_lum,
        S_nonlum=S_nl,
        t_critical_luminous=t_crit_lum,
        t_critical_nonlum=t_crit_nl,
        threshold_luminous=threshold_luminous,
        threshold_nonlum=threshold_nonlum,
    )
