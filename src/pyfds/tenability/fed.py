"""
Fractional Effective Dose (FED) and Fractional Effective Concentration (FEC)
=============================================================================
Incapacitation and lethality calculations from FDS DEVC output data.

References
----------
- FDS 6.10 User Guide, section 22.10.18 (eq. 22.42-22.49): the constants used here,
  identical to FDS's own ``QUANTITY='FED'`` device.
- Purser, D.A. & McAllister, J.L. (2016). Assessment of hazards to occupants
  from smoke, toxic gases, and heat. SFPE Handbook, 5th ed., Chapter 63.
- ISO 13571:2012 — Life-threatening components of fire. Guidelines for the
  estimation of time to compromised tenability in fires.

FED Model Summary (Purser, as in FDS)
-------------------------------------
FED_total = (FED_CO + FED_HCN) · HV_CO₂ + FED_O₂

where HV_CO₂ is the CO₂ hyperventilation factor. NOx and irritant gases, which FDS
also adds, are not tracked here.
Incapacitation is predicted when FED_total ≥ 0.3.
Lethality is predicted when FED_total ≥ 1.0 (LC₅₀).

Convected heat is a separate dose (ISO 13571; FDS leaves it out of FED too): it is
reported as ``fed_heat`` and ``t_heat_incapacitation`` and not added to FED_total.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence


# ── Threshold constants ───────────────────────────────────────────────────────

FED_INCAPACITATION: float = 0.3   # FED for incapacitation (escape impaired)
FED_LETHALITY:      float = 1.0   # FED for 50% lethality (LC₅₀)

# CO (FDS eq. 22.43): FED_CO = ∫ 2.764e-5 · C_CO^1.036 dt   [t in min, C in ppm]
_CO_COEFF:  float = 1.036
_CO_DENOM:  float = 1.0 / 2.764e-5   # ≈ 36,180 ppm^1.036 · min

# O₂ depletion (FDS eq. 22.48): t_inc [min] = exp(8.13 - 0.54 · (20.9 - C_O2))
_O2_A:  float = 8.13
_O2_B:  float = 0.54
# FDS 6.10.1's FED device adds the O₂ term only below 20 % O₂ (the User Guide states no cutoff; found by comparing
# with QUANTITY='FED' in client_demos/example_3, where humid ambient air has 20.76 % and the device stays at 0 until
# the oxygen drops below 20 %). Without it, ordinary air alone adds 0.0003 FED per minute.
_O2_CUTOFF_PCT: float = 20.0

# HCN (FDS eq. 22.44): FED_CN = ∫ (exp(C_CN / 43) / 220 - 0.0045) dt   [t in min, C in ppm]
_HCN_SCALE:  float = 43.0      # ppm
_HCN_RATE:   float = 220.0     # min
_HCN_OFFSET: float = 0.0045    # 1/min

# CO₂ hyperventilation factor (FDS eq. 22.49): HV = exp(0.1903 · %CO₂ + 2.0004) / 7.1, on CO and HCN
_VCO2_A: float = 0.1903
_VCO2_B: float = 2.0004
_VCO2_C: float = 7.1


# ── Per-step dose calculators ─────────────────────────────────────────────────

def _hv_co2_factor(pct_co2: float) -> float:
    """CO₂ hyperventilation multiplier (dimensionless, ≥ 1)."""
    return max(1.0, math.exp(_VCO2_A * pct_co2 + _VCO2_B) / _VCO2_C)


def fed_co_step(ppm_co: float, dt_min: float, pct_co2: float = 0.0) -> float:
    """
    Incremental FED_CO for one timestep (Purser, FDS eq. 22.43).

    Parameters
    ----------
    ppm_co:  CO concentration [ppm].
    dt_min:  Exposure duration [min].
    pct_co2: CO₂ concentration [%v/v] — used for hyperventilation factor.
    """
    base = (ppm_co ** _CO_COEFF * dt_min) / _CO_DENOM
    return base * _hv_co2_factor(pct_co2)


def fed_hcn_step(ppm_hcn: float, dt_min: float, pct_co2: float = 0.0) -> float:
    """
    Incremental FED_HCN for one timestep (Purser, FDS eq. 22.44).

    Parameters
    ----------
    ppm_hcn: HCN concentration [ppm] (FDS subtracts NO and NO₂ first; pass that value if known).
    dt_min:  Exposure duration [min].
    pct_co2: CO₂ concentration [%v/v] — used for hyperventilation factor.
    """
    if ppm_hcn <= 0:
        return 0.0
    rate = max(0.0, math.exp(ppm_hcn / _HCN_SCALE) / _HCN_RATE - _HCN_OFFSET)
    return rate * dt_min * _hv_co2_factor(pct_co2)


def fed_o2_step(pct_o2: float, dt_min: float) -> float:
    """
    Incremental FED_O₂ for one timestep (Purser, FDS eq. 22.48).

    Parameters
    ----------
    pct_o2:  O₂ concentration [%v/v].  Normal ambient = 20.9 % (dry air; humid air has a little less).
    dt_min:  Exposure duration [min].

    Zero at 20 % O₂ and above, as FDS's FED device does.
    """
    if pct_o2 >= _O2_CUTOFF_PCT:
        return 0.0
    # Time to incapacitation at this O₂ level [min]
    t_inc = math.exp(_O2_A - _O2_B * (20.9 - pct_o2))
    return dt_min / max(t_inc, 1e-6)


def fed_heat_step(T_gas: float, dt_min: float) -> float:
    """
    Incremental FED contribution from convected heat (Purser, SFPE 5th ed.).

    Based on skin pain / incapacitation threshold:
        FED_heat = Δt / t_inc(T)
        t_inc [min] = 5 × 10^7 × T^(-3.4)   [T in °C, for T > 60°C]

    Parameters
    ----------
    T_gas:  Gas temperature [°C].
    dt_min: Exposure duration [min].
    """
    if T_gas <= 60.0:
        return 0.0
    t_inc = 5e7 * T_gas ** (-3.4)
    return dt_min / max(t_inc, 1e-6)


# ── Cumulative FED time-series ────────────────────────────────────────────────

@dataclass
class FEDResult:
    """Cumulative FED calculation result."""
    times:          List[float]  # s
    fed_co:         List[float]
    fed_hcn:        List[float]
    fed_o2:         List[float]
    fed_heat:       List[float]  # separate dose, not part of fed_total
    fed_total:      List[float]  # gases: (CO + HCN) · HV_CO₂ + O₂
    t_incapacitation: Optional[float]  # s; None if not reached
    t_lethality:      Optional[float]  # s; None if not reached
    max_fed:        float
    t_heat_incapacitation: Optional[float] = None   # s; when fed_heat reaches 1, None if not reached


def calculate_fed(
    times_s: Sequence[float],
    co_ppm: Sequence[float],
    o2_pct: Optional[Sequence[float]] = None,
    hcn_ppm: Optional[Sequence[float]] = None,
    co2_pct: Optional[Sequence[float]] = None,
    temp_c: Optional[Sequence[float]] = None,
) -> FEDResult:
    """
    Compute cumulative FED time-series from DEVC data arrays.

    Parameters
    ----------
    times_s:  Time values [s] — must be monotonically increasing.
    co_ppm:   CO concentration [ppm] at each timestep.
    o2_pct:   O₂ concentration [%v/v] — optional (20.9 % assumed if None).
    hcn_ppm:  HCN concentration [ppm] — optional.
    co2_pct:  CO₂ concentration [%v/v] — optional (0 % assumed if None).
    temp_c:   Gas temperature [°C] — optional (heat FED disabled if None).

    Returns
    -------
    :class:`FEDResult`
    """
    n = len(times_s)
    f_co   = [0.0] * n
    f_hcn  = [0.0] * n
    f_o2   = [0.0] * n
    f_heat = [0.0] * n
    f_tot  = [0.0] * n
    t_inc  = None
    t_let  = None
    t_heat = None

    cum_co = cum_hcn = cum_o2 = cum_heat = 0.0

    for i in range(1, n):
        dt_s   = times_s[i] - times_s[i - 1]
        dt_min = dt_s / 60.0

        c_co   = co_ppm[i]
        c_o2   = o2_pct[i]  if o2_pct  else 20.9
        c_hcn  = hcn_ppm[i] if hcn_ppm else 0.0
        c_co2  = co2_pct[i] if co2_pct else 0.0
        t_gas  = temp_c[i]  if temp_c  else 20.0

        cum_co   += fed_co_step(c_co, dt_min, c_co2)
        cum_hcn  += fed_hcn_step(c_hcn, dt_min, c_co2)
        cum_o2   += fed_o2_step(c_o2, dt_min)
        cum_heat += fed_heat_step(t_gas, dt_min)

        f_co[i]   = cum_co
        f_hcn[i]  = cum_hcn
        f_o2[i]   = cum_o2
        f_heat[i] = cum_heat
        f_tot[i]  = cum_co + cum_hcn + cum_o2

        if t_inc is None and f_tot[i] >= FED_INCAPACITATION:
            t_inc = times_s[i]
        if t_let is None and f_tot[i] >= FED_LETHALITY:
            t_let = times_s[i]
        if t_heat is None and cum_heat >= 1.0:
            t_heat = times_s[i]

    return FEDResult(
        times=list(times_s),
        fed_co=f_co, fed_hcn=f_hcn, fed_o2=f_o2, fed_heat=f_heat,
        fed_total=f_tot,
        t_incapacitation=t_inc,
        t_lethality=t_let,
        max_fed=max(f_tot),
        t_heat_incapacitation=t_heat,
    )


def aset_margin(t_incapacitation: Optional[float], t_rset: float) -> float:
    """
    Available Safe Egress Time margin [s].

    Returns ASET − RSET.  Negative means untenable conditions before
    occupants have escaped.

    Parameters
    ----------
    t_incapacitation: Time to incapacitation from :class:`FEDResult` [s].
    t_rset:           Required Safe Egress Time [s].
    """
    if t_incapacitation is None:
        return float("inf")
    return t_incapacitation - t_rset
