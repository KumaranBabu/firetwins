"""Arrhenius parameters (A, E) for a material's pyrolysis reaction (matches the FDS &MATL model).

FDS reaction rate (User Guide, "Pyrolysis"): ``r = A * Y^n * exp(-E / (R T))`` with A in 1/s, E in J/mol, T in K.
Two ways to get A and E, both from thermogravimetric (TGA) data:

* :func:`fit_arrhenius` - a measured reaction-rate curve ``r(T)`` (the mass-loss-rate curve divided by the
  remaining mass^n): a straight-line fit of ``ln r`` against ``1/T``.
* :func:`from_peak` - Kissinger's method from the peak of a TGA run (heating rate and peak temperature):
  E is given or taken from a second run; A follows from the peak condition.

FDS itself can also take ``REFERENCE_TEMPERATURE`` + ``HEATING_RATE`` (+ ``PYROLYSIS_RANGE``) and work out A and E;
use this module when you want the numbers explicitly.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

import numpy as np

R = 8.314462618       # J/(mol K)


def fit_arrhenius(temperature_c: Sequence[float], rate: Sequence[float], n: float = 1.0,
                  remaining_mass: Optional[Sequence[float]] = None) -> Dict[str, float]:
    """Least-squares A (1/s) and E (J/mol) from ``rate`` (1/s, or mass-loss per initial mass per s) at
    ``temperature_c`` (deg C). With *remaining_mass* (fraction left, 1 -> 0) the rate is divided by
    ``Y^n`` first. Points with a non-positive rate are ignored. Returns ``{"A", "E", "r2", "points"}``."""
    t = np.asarray(temperature_c, dtype=float) + 273.15
    r = np.asarray(rate, dtype=float)
    if t.shape != r.shape or t.size < 3:
        raise ValueError("give at least three (temperature, rate) pairs of equal length")
    if remaining_mass is not None:
        y = np.asarray(remaining_mass, dtype=float)
        if y.shape != t.shape:
            raise ValueError("remaining_mass needs one value per temperature")
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(y > 0, r / np.power(y, n), 0.0)
    keep = (r > 0) & (t > 0)
    if keep.sum() < 3:
        raise ValueError("fewer than three points have a positive rate")
    x, yv = 1.0 / t[keep], np.log(r[keep])
    slope, intercept = np.polyfit(x, yv, 1)
    if slope >= 0:
        raise ValueError("the rate does not increase with temperature, so no activation energy can be fitted")
    fit = slope * x + intercept
    ss_res, ss_tot = float(np.sum((yv - fit) ** 2)), float(np.sum((yv - yv.mean()) ** 2))
    return {"A": float(math.exp(intercept)), "E": float(-slope * R),
            "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0, "points": int(keep.sum())}


def kissinger_activation_energy(heating_rates_k_per_min: Sequence[float], peak_temperatures_c: Sequence[float]) -> float:
    """E (J/mol) from TGA peaks at several heating rates: slope of ``ln(beta / Tp^2)`` against ``1/Tp``."""
    b = np.asarray(heating_rates_k_per_min, dtype=float)
    tp = np.asarray(peak_temperatures_c, dtype=float) + 273.15
    if b.size < 2 or b.shape != tp.shape:
        raise ValueError("give at least two heating rates, with one peak temperature each")
    slope = np.polyfit(1.0 / tp, np.log(b / tp ** 2), 1)[0]
    if slope >= 0:
        raise ValueError("peak temperature must rise with heating rate")
    return float(-slope * R)


def from_peak(heating_rate_k_per_min: float, peak_temperature_c: float, activation_energy: float,
              n: float = 1.0) -> Dict[str, float]:
    """A (1/s) for a first-order-like peak (Kissinger): ``A = beta E exp(E/(R Tp)) / (n R Tp^2)`` with beta in
    K/s. *activation_energy* in J/mol (use :func:`kissinger_activation_energy` for two or more runs)."""
    if heating_rate_k_per_min <= 0 or activation_energy <= 0 or n <= 0:
        raise ValueError("heating rate, activation energy and n must be positive")
    tp = peak_temperature_c + 273.15
    beta = heating_rate_k_per_min / 60.0
    a = beta * activation_energy * math.exp(activation_energy / (R * tp)) / (n * R * tp * tp)
    return {"A": a, "E": activation_energy}
