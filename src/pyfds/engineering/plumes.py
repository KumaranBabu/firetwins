"""
Fire Plume and Ceiling Jet Correlations
========================================
Alpert (1972) ceiling jet, Heskestad (1984) plume, and flame height models.

All correlations assume standard ambient conditions unless stated otherwise:
  T_∞ = 293 K, ρ_∞ = 1.204 kg/m³, c_p = 1.0 kJ/(kg·K), g = 9.81 m/s²

References
----------
- Alpert, R. (1972). Calculation of response time of ceiling-mounted fire
  detectors. Fire Technology 8(3):181–195.
- Heskestad, G. (1984). Engineering relations for fire plumes.
  Fire Safety Journal 7(1):25–32.
- SFPE Handbook of Fire Protection Engineering, 5th ed.,
  Chapter 14 (Alpert) and Chapter 13 (Heskestad).
- Karlsson, B. & Quintiere, J. (2000). Enclosure Fire Dynamics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── Standard ambient conditions ───────────────────────────────────────────────
T_AMB:  float = 293.0   # K
G:      float = 9.81    # m/s²
RHO:    float = 1.204   # kg/m³
CP:     float = 1.0     # kJ/(kg·K)   — consistent with Q in kW
CHI_R:  float = 0.30    # radiative fraction (FDS default)


def _q_convective(q_total: float, chi_r: float = CHI_R) -> float:
    return q_total * (1.0 - chi_r)


# ── Alpert (1972) ceiling jet ─────────────────────────────────────────────────

@dataclass(frozen=True)
class CeilingJetResult:
    """Alpert (1972) ceiling jet quantities at (r, H)."""
    r: float          # m — radial distance from fire axis
    H: float          # m — ceiling height above fire base
    delta_T: float    # K — maximum excess temperature in jet
    u_max: float      # m/s — maximum velocity in jet
    zone: str         # 'near' or 'jet'


def alpert_ceiling_jet(
    q_kw: float,
    H: float,
    r: float,
    T_amb: float = T_AMB,
    chi_r: float = CHI_R,
) -> CeilingJetResult:
    """
    Alpert (1972) ceiling-jet temperature rise and velocity.

    Parameters
    ----------
    q_kw:  Total heat release rate [kW].
    H:     Ceiling height above fire base [m].
    r:     Radial distance from fire axis [m].
    T_amb: Ambient temperature [K].
    chi_r: Radiative fraction.

    Returns
    -------
    :class:`CeilingJetResult`

    Notes
    -----
    The Alpert correlation uses convective HRR Q_c = (1 − χ_r) · Q.
    Near-field region: r/H ≤ 0.18 (stagnation zone).
    Far-field region:  r/H  > 0.18 (developed ceiling jet).
    """
    if H <= 0:
        raise ValueError("H must be > 0")
    if r < 0:
        raise ValueError("r must be ≥ 0")

    q_c = _q_convective(q_kw, chi_r)

    if r / H <= 0.18:
        delta_T = 16.9 * q_c ** (2.0 / 3.0) / H ** (5.0 / 3.0)
        u_max   = 0.96 * (q_c / H) ** (1.0 / 3.0)
        zone    = "near"
    else:
        delta_T = 5.38 * (q_c / r) ** (2.0 / 3.0) / H
        u_max   = 0.195 * (q_c / H) ** (1.0 / 3.0) * (H / r) ** (5.0 / 6.0)
        zone    = "jet"

    return CeilingJetResult(r=r, H=H, delta_T=delta_T, u_max=u_max, zone=zone)


def alpert_detector_r_max(
    q_kw: float,
    H: float,
    delta_T_threshold: float,
    chi_r: float = CHI_R,
) -> float:
    """
    Maximum radial distance [m] at which ceiling-jet ΔT exceeds *delta_T_threshold* [K].

    Uses the far-field Alpert expression (valid for r/H > 0.18).
    Useful for smoke/heat detector spacing checks per NFPA 72.
    """
    q_c = _q_convective(q_kw, chi_r)
    # ΔT_max = 5.38 (Q_c/r)^(2/3) / H  → r = (5.38 Q_c^(2/3) / (H · ΔT))^(3/2)
    r_max = (5.38 * q_c ** (2.0 / 3.0) / (H * delta_T_threshold)) ** 1.5
    return r_max


# ── Heskestad (1984) plume ────────────────────────────────────────────────────

@dataclass(frozen=True)
class HeskestadResult:
    """Heskestad (1984) centreline plume quantities."""
    z: float           # m — height above fire base
    flame_height: float  # m — mean flame height L_f
    virtual_origin: float  # m — virtual origin z_0 (above fire base)
    delta_T_cl: float  # K — centreline excess temperature (above L_f only)
    u_cl: float        # m/s — centreline velocity  (above L_f only)
    above_flame: bool  # True when z > L_f (correlation valid)


def heskestad_flame_height(q_kw: float, D: float) -> float:
    """
    Mean flame height [m] — Heskestad (1984).

    Parameters
    ----------
    q_kw: Total heat release rate [kW].
    D:    Effective fire diameter [m].
    """
    return max(0.0, -1.02 * D + 0.235 * q_kw ** 0.4)


def heskestad_virtual_origin(q_kw: float, D: float) -> float:
    """Virtual origin height above fire base [m] — Heskestad (1984)."""
    return -1.02 * D + 0.083 * q_kw ** 0.4


def heskestad_plume(
    q_kw: float,
    D: float,
    z: float,
    T_amb: float = T_AMB,
    chi_r: float = CHI_R,
) -> HeskestadResult:
    """
    Heskestad (1984) centreline plume temperature and velocity above the flame.

    Parameters
    ----------
    q_kw:  Total heat release rate [kW].
    D:     Effective fire diameter [m].
    z:     Height above fire base [m].
    T_amb: Ambient temperature [K].
    chi_r: Radiative fraction.

    Notes
    -----
    The temperature and velocity correlations are valid for z > L_f only.
    Below or at the flame height, extreme values are returned and
    ``above_flame`` is set to False.

    Centreline temperature rise (SFPE 5th ed., Eq. 13-13):
        ΔT_cl = 9.1 (T_∞/g)^(1/3) (1/(ρ c_p))^(2/3) Q_c^(2/3) (z-z_0)^(-5/3)

    Pre-computed constant for standard air: A_T ≈ 24.1 K·m^(5/3) / kW^(2/3)

    Centreline velocity (SFPE 5th ed., Eq. 13-14):
        u_cl = (g/(ρ c_p T_∞))^(1/3) Q_c^(1/3) (z-z_0)^(-1/3)

    Pre-computed constant for standard air: A_U ≈ 0.304 m^(4/3)·s^(-1) / kW^(1/3)
    """
    q_c = _q_convective(q_kw, chi_r)
    L_f = heskestad_flame_height(q_kw, D)
    z_0 = heskestad_virtual_origin(q_kw, D)

    above = z > L_f
    z_n   = z - z_0  # height above virtual origin

    if above and z_n > 0:
        # Constants for standard ambient (T=293K, ρ=1.204, c_p=1.0 kJ/kg·K, g=9.81)
        A_T = 9.1 * (T_amb / G) ** (1.0 / 3.0) * (1.0 / (RHO * CP)) ** (2.0 / 3.0)
        A_U = (G / (RHO * CP * T_amb)) ** (1.0 / 3.0)
        delta_T = A_T * q_c ** (2.0 / 3.0) * z_n ** (-5.0 / 3.0)
        u_cl    = A_U * q_c ** (1.0 / 3.0) * z_n ** (-1.0 / 3.0)
    else:
        delta_T = float("nan")
        u_cl    = float("nan")

    return HeskestadResult(
        z=z,
        flame_height=L_f,
        virtual_origin=z_0,
        delta_T_cl=delta_T,
        u_cl=u_cl,
        above_flame=above,
    )


# ── Sprinkler / detector response ─────────────────────────────────────────────

@dataclass(frozen=True)
class SprinklerResponseResult:
    """RTI-based sprinkler or heat-detector activation."""
    t_activation: Optional[float]  # s; None if threshold not reached
    T_link_final: float            # K — link temperature at end of simulation
    activation_temp: float         # K — configured activation temperature


def sprinkler_rti(
    T_link_initial: float,
    T_gas_series: list[float],
    u_gas_series: list[float],
    dt: float,
    rti: float,
    c_factor: float = 0.0,
    T_activation: float = 347.15,   # 74 °C in K (standard sprinkler)
) -> SprinklerResponseResult:
    """
    Response Time Index (RTI) model for sprinkler/heat-detector activation.

    Uses the differential equation (Heskestad & Bill, 1988):
        dT_link/dt = (u^0.5 / RTI) × (T_gas − T_link) − C × u^0.5 × (T_link − T_amb)

    Parameters
    ----------
    T_link_initial: Initial link temperature [K].
    T_gas_series:   List of gas temperatures [K] at each timestep.
    u_gas_series:   List of gas velocities [m/s] at each timestep.
    dt:             Timestep [s].
    rti:            Response Time Index [m^0.5 · s^0.5].
    c_factor:       Conduction/loss factor [m^0.5 / s^0.5] (0 for standard).
    T_activation:   Link activation temperature [K].

    Returns
    -------
    :class:`SprinklerResponseResult`
    """
    T_link = T_link_initial
    t_act  = None

    for i, (T_gas, u_gas) in enumerate(zip(T_gas_series, u_gas_series)):
        u_sqrt = math.sqrt(max(u_gas, 1e-6))
        dT = (u_sqrt / rti) * (T_gas - T_link) - c_factor * u_sqrt * (T_link - T_link_initial)
        T_link += dT * dt

        if T_link >= T_activation and t_act is None:
            t_act = (i + 1) * dt
            break

    return SprinklerResponseResult(
        t_activation=t_act,
        T_link_final=T_link,
        activation_temp=T_activation,
    )
