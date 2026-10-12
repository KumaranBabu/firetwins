"""
Tunnel Fire Engineering
========================
Critical velocity, back-layering, and BRE spill-plume calculations.

References
----------
- Kennedy, W.D. et al. (1996). Derivation and application of the SES critical
  velocity equations. ASHRAE Transactions 102(2):40–44.
- NFPA 502 (2020). Standard for Road Tunnels, Bridges, and Other Limited Access
  Highways. Annex D.
- Heselden, A.J.M. (1976). Studies of fire and smoke behaviour relevant to
  tunnels. Proc. 2nd Int. Symp. Aerodynamics and Ventilation of Vehicle Tunnels.
- Morgan, H.P. (1986). Smoke control in shopping malls and atria.
  BRE Report 186.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Standard ambient conditions
G:   float = 9.81   # m/s²
RHO: float = 1.2    # kg/m³
CP:  float = 1.0    # kJ/(kg·K)
T_0: float = 293.0  # K

# Kennedy dimensionless factor (SI units)
K_G: float = 0.606


@dataclass(frozen=True)
class CriticalVelocityResult:
    """Output of :func:`critical_velocity`."""
    v_c: float          # m/s — critical longitudinal velocity
    q_kw: float         # kW
    height: float       # m — tunnel height H
    area: float         # m² — tunnel cross-section A
    froude_ri: float    # Richardson number (inverse Froude²)
    T_fire: float       # K — estimated fire-zone temperature


def critical_velocity(
    q_kw: float,
    H: float,
    A: float,
    T_amb: float = T_0,
    chi_r: float = 0.30,
    k_z: float = 1.0,
    max_iter: int = 50,
    tol: float = 1e-4,
) -> CriticalVelocityResult:
    """
    Kennedy (1996) / NFPA 502 critical longitudinal ventilation velocity.

    Solves the implicit equation iteratively:

        V_c = k_g · k_z · [g · H · Q_c / (ρ₀ · c_p · T_f · A · V_c)]^(1/3)

    where T_f = T_amb + Q_c / (ρ₀ · c_p · V_c · A)

    Parameters
    ----------
    q_kw:   Total heat release rate [kW].
    H:      Tunnel height [m].
    A:      Tunnel cross-sectional area [m²].
    T_amb:  Ambient temperature [K].
    chi_r:  Radiative fraction.
    k_z:    Height factor (1.0 for H ≥ 4 m; NFPA 502 Annex D).
    """
    q_c = q_kw * (1.0 - chi_r)

    # Initial estimate: simplified (isothermal plume gases)
    v = K_G * k_z * (G * H * q_c / (RHO * CP * T_amb * A)) ** (1.0 / 3.0)

    for _ in range(max_iter):
        q_mass = RHO * CP * v * A           # kW/K — mass flow × c_p
        T_fire = T_amb + q_c / max(q_mass, 1e-6)
        v_new  = K_G * k_z * (G * H * q_c / (RHO * CP * T_fire * A * v)) ** (1.0 / 3.0)
        if abs(v_new - v) < tol:
            v = v_new
            break
        v = 0.5 * v + 0.5 * v_new   # damped update for stability

    q_mass = RHO * CP * v * A
    T_fire = T_amb + q_c / max(q_mass, 1e-6)
    ri     = (G * H * q_c) / (RHO * CP * T_fire * A * v ** 3)

    return CriticalVelocityResult(
        v_c=v, q_kw=q_kw, height=H, area=A,
        froude_ri=ri, T_fire=T_fire,
    )


@dataclass(frozen=True)
class BackLayeringResult:
    """Extent of smoke back-layering upstream of fire."""
    L_back: float   # m — back-layering length (0 if V ≥ V_c)
    v_applied: float  # m/s — applied longitudinal velocity
    v_critical: float  # m/s — critical velocity
    suppressed: bool    # True if back-layering is eliminated


def back_layering_length(
    q_kw: float,
    H: float,
    A: float,
    v_applied: float,
    T_amb: float = T_0,
    chi_r: float = 0.30,
) -> BackLayeringResult:
    """
    Estimate back-layering length [m] for *v_applied* < *V_c*.

    Uses the Ingason (2012) correlation (simplified):
        L_back / H = 18.5 · ln(0.81 · Ri^(1/3) / Fr_d)

    For engineering scoping, a simpler linear approximation is used:
        L_back ≈ H · (V_c / V - 1) · K_back
    where K_back ≈ 15 (empirical, conservative).
    """
    vc_result  = critical_velocity(q_kw, H, A, T_amb, chi_r)
    v_c        = vc_result.v_c
    suppressed = v_applied >= v_c

    if suppressed:
        L_back = 0.0
    else:
        K_back = 15.0
        L_back = H * max(0.0, (v_c / max(v_applied, 1e-6) - 1.0)) * K_back

    return BackLayeringResult(
        L_back=L_back,
        v_applied=v_applied,
        v_critical=v_c,
        suppressed=suppressed,
    )


# ── BRE spill plume (horizontal projecting geometry) ─────────────────────────

@dataclass(frozen=True)
class SpillPlumeResult:
    """Morgan/BRE horizontal spill plume entrainment."""
    z: float          # m — height above spill edge
    M_dot: float      # kg/s — mass flow rate in plume at height z
    Q_c: float        # kW — convective HRR
    b_spill: float    # m — spill width


def bré_spill_plume(
    q_kw: float,
    W: float,
    z: float,
    chi_r: float = 0.30,
) -> SpillPlumeResult:
    """
    BRE (Morgan, 1986) horizontal spill-plume mass-flow rate.

    For smoke spilling from a balcony edge of width *W* [m] rising a
    height *z* [m] above the spill edge.

        ṁ = 0.36 · (Q_c · W)^(1/3) · z

    Parameters
    ----------
    q_kw: Convective heat release rate reaching spill edge [kW].
    W:    Width of spill edge [m].
    z:    Height above spill edge to smoke layer interface [m].
    """
    q_c   = q_kw * (1.0 - chi_r)
    m_dot = 0.36 * (q_c * W) ** (1.0 / 3.0) * z
    return SpillPlumeResult(z=z, M_dot=m_dot, Q_c=q_c, b_spill=W)


# ── Axisymmetric atrium plume (Thomas, 1987 / CIBSE TM19) ────────────────────

def atrium_plume_mass_flow(
    q_kw: float,
    z: float,
    chi_r: float = 0.30,
) -> float:
    """
    Mass flow rate [kg/s] in an axisymmetric atrium plume at height *z* [m].

    Uses the Heskestad-based formula as adopted by CIBSE TM19 (2003):

        ṁ = 0.071 · Q_c^(1/3) · z^(5/3)

    Parameters
    ----------
    q_kw: Total HRR [kW].
    z:    Clear-layer height above fire base [m].
    """
    q_c = q_kw * (1.0 - chi_r)
    return 0.071 * q_c ** (1.0 / 3.0) * z ** (5.0 / 3.0)


def smoke_filling_time(
    q_kw: float,
    volume: float,
    A_floor: float,
    H_room: float,
    z_interface: float,
    chi_r: float = 0.30,
) -> float:
    """
    Time [s] for smoke layer to descend to *z_interface* [m] above floor.

    Uses the SFPE / NFPA 92 power-law filling equation (Thomas et al.):

        t = (A_f / (0.071 · Q_c^(1/3))) · ∫ z^(-5/3) dz  from H to z_i

    Parameters
    ----------
    q_kw:        Total HRR [kW].
    volume:      Room volume [m³] (used to check consistency).
    A_floor:     Floor area [m²].
    H_room:      Ceiling height [m].
    z_interface: Target interface height [m].
    """
    q_c = q_kw * (1.0 - chi_r)
    if q_c <= 0 or z_interface >= H_room:
        return 0.0
    # Integrating dz/dt = -0.071·Qc^(1/3)·z^(5/3) / (ρ·A_f) from H down to z_i:
    # t = (A_f / (0.071·Qc^(1/3))) · 3/2 · (z_i^(-2/3) − H^(-2/3))
    integral = (3.0 / 2.0) * (z_interface ** (-2.0 / 3.0) - H_room ** (-2.0 / 3.0))
    t = (A_floor / (0.071 * q_c ** (1.0 / 3.0))) * integral
    return max(0.0, t)
