"""Display units for results (View ▸ Temperature / Concentration / Mass Fraction Unit)."""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .model import Units


def convert(values, units: str, prefs: Units) -> Tuple[np.ndarray, str]:
    """Return ``(values, unit label)`` for FDS data in *units* under the user's unit choices."""
    v = np.asarray(values)
    u = (units or "").strip()
    if u in ("C", "°C", "deg C") and prefs.temperature == "F":
        return v * 9.0 / 5.0 + 32.0, "F"
    if u == "mol/mol" and prefs.concentration == "ppm":
        return v * 1.0e6, "ppm"
    if u == "kg/kg" and prefs.mass_fraction == "ppm":
        return v * 1.0e6, "ppm"
    return v, u


def label(units: str, prefs: Units) -> str:
    return convert(np.zeros(1), units, prefs)[1]


def convert_value(value: float, units: str, prefs: Units) -> Tuple[float, str]:
    v, u = convert(np.array([value]), units, prefs)
    return float(v[0]), u
