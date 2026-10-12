"""
PyFDS Engineering — Two-Layer Zone Model
=========================================
CFAST-style algebraic two-zone model for a single compartment.

The upper layer fills with hot combustion products from the plume; the lower
layer is displaced downward.  Conservation of mass and energy gives the
quasi-steady interface height and upper-layer temperature.

Reference
---------
Karlsson & Quintiere, "Enclosure Fire Dynamics," CRC Press 2000, Ch. 7.

All inputs / outputs in SI units (m, kW, °C, kg/m³, …).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Standard air constants
_RHO0 = 1.204     # kg/m³ at 20 °C, 101325 Pa
_CP   = 1.012     # kJ/(kg·K)
_T0   = 293.15    # K  (20 °C ambient)
_G    = 9.81      # m/s²
_SIGMA = 5.67e-8  # W/(m²·K⁴)


@dataclass
class ZoneModelResult:
    """Output of ``two_layer_zone_model``."""
    z_interface_m: float          # smoke-air interface height above floor (m)
    T_upper_K: float              # upper-layer absolute temperature (K)
    T_upper_C: float              # upper-layer temperature (°C)
    m_plume_kg_s: float           # plume mass flow rate at interface (kg/s)
    heat_loss_fraction: float     # fraction of HRR lost to walls/ceiling
    hrr_convective_kw: float      # convective HRR (kW)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ZoneModelResult("
            f"z_int={self.z_interface_m:.2f}m, "
            f"T_upper={self.T_upper_C:.1f}°C, "
            f"m_plume={self.m_plume_kg_s:.3f}kg/s)"
        )


def two_layer_zone_model(
    hrr_kw: float,
    room_height_m: float,
    floor_area_m2: float,
    *,
    t_ambient_c: float = 20.0,
    radiative_fraction: float = 0.35,
    wall_loss_fraction: float = 0.1,
    z_virtual_origin_m: float = 0.0,
    z_base_m: float = 0.0,
) -> ZoneModelResult:
    """
    Quasi-steady two-layer zone model for a single room fire.

    Parameters
    ----------
    hrr_kw:
        Total heat release rate (kW).
    room_height_m:
        Clear height of the compartment (m).
    floor_area_m2:
        Floor area (m²).
    t_ambient_c:
        Ambient temperature (°C, default 20).
    radiative_fraction:
        Fraction of HRR radiated (rest is convective, default 0.35).
    wall_loss_fraction:
        Fraction of convective HRR lost to compartment walls (default 0.10).
    z_virtual_origin_m:
        Heskestad virtual origin height below burner surface (m, default 0).
    z_base_m:
        Elevation of the fuel base above the floor (m, default 0).

    Returns
    -------
    ZoneModelResult

    Notes
    -----
    The interface height is solved from the plume entrainment equation:

        m_p(z) = 0.071 · Q_c^(1/3) · (z - z_0)^(5/3)   [kg/s]

    where ``z_0 = z_base - z_virtual_origin``.  Conservation of energy in the
    upper layer gives the upper-layer temperature.
    """
    if hrr_kw <= 0:
        raise ValueError("hrr_kw must be positive")
    if room_height_m <= 0:
        raise ValueError("room_height_m must be positive")
    if floor_area_m2 <= 0:
        raise ValueError("floor_area_m2 must be positive")

    T_amb = t_ambient_c + 273.15
    Q_c = hrr_kw * (1.0 - radiative_fraction)       # convective HRR [kW]
    Q_net = Q_c * (1.0 - wall_loss_fraction)         # net to upper layer [kW]

    z0 = z_base_m - z_virtual_origin_m               # effective virtual origin

    # Iterative solution: find z_interface such that:
    #   Q_net = m_p(z) * cp * (T_upper - T_amb)
    #   rho_upper / rho_amb ≈ T_amb / T_upper  (ideal gas)
    #   volume_upper = (room_height - z_interface) * floor_area
    # Simplified approach: solve for steady-state upper layer temperature
    # from energy balance, then back-calculate mass flow.

    # Estimate interface height using NFPA 92 smoke filling (quasi-steady limit):
    #   z_i / H ≈ (1 + (Q_c / (rho0 * cp * T0 * A * g^0.5 * H^2.5))^0.4)^(-1)
    # Use Zukoski's filling fraction as first estimate:
    H = room_height_m
    A = floor_area_m2
    denom = _RHO0 * _CP * T_amb * A * (_G ** 0.5) * (H ** 2.5)
    if denom > 0:
        zeta = min(0.99, max(0.05, 1.0 - (Q_c / denom) ** 0.4))
    else:
        zeta = 0.5
    z_int = max(0.05, min(H * 0.95, zeta * H))

    # Refine with Heskestad plume mass flow:
    def plume_mass_flow(z: float) -> float:
        dz = max(0.01, z - z0)
        return 0.071 * (Q_c ** (1.0 / 3.0)) * (dz ** (5.0 / 3.0))

    # Newton iteration on energy balance: m_p * cp * (T_u - T_amb) = Q_net
    for _ in range(50):
        m_p = plume_mass_flow(z_int)
        if m_p <= 0:
            break
        T_u = T_amb + Q_net / (m_p * _CP)
        # Volume of upper layer at T_u
        rho_u = _RHO0 * T_amb / T_u
        vol_u = A * (H - z_int)
        # Mass of upper layer
        m_u = rho_u * vol_u
        # Revised interface: where rho_u * vol_u equals accumulated plume mass
        # Adjust z_int so that mass conservation is satisfied.
        # Simple update: z_int moves up if T_u is very hot (buoyancy pushes layer up).
        z_int_new = H - m_u / (rho_u * A)
        z_int_new = max(0.02 * H, min(0.98 * H, z_int_new))
        if abs(z_int_new - z_int) < 1e-4:
            z_int = z_int_new
            break
        z_int = 0.7 * z_int + 0.3 * z_int_new  # damped update

    m_plume = plume_mass_flow(z_int)
    T_upper = T_amb + (Q_net / (m_plume * _CP)) if m_plume > 0 else T_amb

    return ZoneModelResult(
        z_interface_m=z_int,
        T_upper_K=T_upper,
        T_upper_C=T_upper - 273.15,
        m_plume_kg_s=m_plume,
        heat_loss_fraction=wall_loss_fraction,
        hrr_convective_kw=Q_c,
    )


@dataclass
class DetectorResponseResult:
    """Output of ``detector_response_time``."""
    activation_time_s: Optional[float]    # None if detector never activates
    peak_jet_temp_c: float                # ceiling jet temperature at detector (°C)
    peak_jet_velocity_ms: float           # ceiling jet velocity at detector (m/s)
    rti: float                            # RTI used (m·s)^0.5
    setpoint_c: float                     # activation temperature (°C)


def detector_response_time(
    hrr_kw: float,
    ceiling_height_m: float,
    detector_radial_distance_m: float,
    *,
    rti: float = 50.0,
    setpoint_c: float = 68.0,
    c_factor: float = 0.0,
    t_ambient_c: float = 20.0,
    dt_s: float = 0.5,
    t_max_s: float = 600.0,
) -> DetectorResponseResult:
    """
    Estimate heat detector / sprinkler activation time using Alpert (1972)
    ceiling jet correlations and the RTI model.

    Parameters
    ----------
    hrr_kw:
        Steady-state (or peak) HRR (kW).
    ceiling_height_m:
        Ceiling height above fire source (m).
    detector_radial_distance_m:
        Horizontal distance from fire axis to detector (m).
    rti:
        Response Time Index (m·s)^0.5, default 50.
    setpoint_c:
        Detector activation temperature (°C), default 68.
    c_factor:
        Conduction factor (m/s)^0.5, default 0 (insulated housing).
    t_ambient_c:
        Ambient temperature (°C), default 20.
    dt_s:
        Integration time step (s), default 0.5.
    t_max_s:
        Maximum time to simulate (s), default 600.

    Returns
    -------
    DetectorResponseResult
    """
    from pyfds.engineering.plumes import alpert_ceiling_jet

    H = ceiling_height_m
    r = detector_radial_distance_m
    result = alpert_ceiling_jet(hrr_kw=hrr_kw, r=r, H=H)
    T_jet = result.temperature_c
    u_jet = result.velocity_ms

    # RTI model: dT_detector/dt = (u_jet^0.5 / rti) * (T_jet - T_det) - c_factor * u_jet^0.5 * T_det^0.5
    T_det = t_ambient_c
    activation_time: Optional[float] = None
    t = 0.0
    while t <= t_max_s:
        u_rt = math.sqrt(max(0.0, u_jet))
        dT = (u_rt / rti) * (T_jet - T_det)
        if c_factor > 0:
            dT -= c_factor * u_rt * math.sqrt(max(0.0, T_det))
        T_det += dT * dt_s
        t += dt_s
        if T_det >= setpoint_c:
            activation_time = t
            break

    return DetectorResponseResult(
        activation_time_s=activation_time,
        peak_jet_temp_c=T_jet,
        peak_jet_velocity_ms=u_jet,
        rti=rti,
        setpoint_c=setpoint_c,
    )
