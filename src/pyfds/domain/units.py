"""SI / English unit conversion (UI-10).

The model always stores SI values (the units FDS reads). A unit *system* is a display and entry
choice: ``to_display`` turns a stored value into what the user sees, ``from_display`` turns what they
typed back into SI. Pure functions, no project or Qt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

SI = "SI"
ENGLISH = "EN"
SYSTEMS = (SI, ENGLISH)


@dataclass(frozen=True)
class Quantity:
    """One kind of quantity: SI label, English label, and ``english = si * factor + offset``."""
    si: str
    en: str
    factor: float
    offset: float = 0.0


_FT = 0.3048
_LB = 0.45359237
_BTU_KJ = 1.055056

QUANTITIES: Dict[str, Quantity] = {
    "length":            Quantity("m", "ft", 1 / _FT),
    "area":              Quantity("m2", "ft2", 1 / _FT ** 2),
    "volume":            Quantity("m3", "ft3", 1 / _FT ** 3),
    "temperature":       Quantity("C", "F", 9 / 5, 32.0),
    "temperature_delta": Quantity("K", "R", 9 / 5),
    "velocity":          Quantity("m/s", "ft/s", 1 / _FT),
    "acceleration":      Quantity("m/s2", "ft/s2", 1 / _FT),
    "pressure":          Quantity("Pa", "psi", 1 / 6894.757293168),
    "power":             Quantity("kW", "Btu/s", 1 / _BTU_KJ),
    "heat_flux":         Quantity("kW/m2", "Btu/s/ft2", _FT ** 2 / _BTU_KJ),
    "energy":            Quantity("kJ", "Btu", 1 / _BTU_KJ),
    "mass":              Quantity("kg", "lb", 1 / _LB),
    "mass_flow":         Quantity("kg/s", "lb/s", 1 / _LB),
    "density":           Quantity("kg/m3", "lb/ft3", _FT ** 3 / _LB),
    "volume_flow":       Quantity("m3/s", "ft3/s", 1 / _FT ** 3),
    "conductivity":      Quantity("W/m/K", "Btu/h/ft/F", 1 / 1.730734666),
    "specific_heat":     Quantity("kJ/kg/K", "Btu/lb/F", 0.238845896627),
    "time":              Quantity("s", "s", 1.0),
}


#: Units a value may be typed in, with the factor to the SI unit of its kind (``cfm`` = cubic feet per minute, accepted for
#: volumetric flow as in PyroSim 2025.1). Lower-case keys; a leading ``^`` as in ``m^3/s`` is ignored.
UNIT_ALIASES: Dict[str, Dict[str, float]] = {
    "volume_flow": {"m3/s": 1.0, "l/s": 1e-3, "m3/h": 1 / 3600.0, "m3/min": 1 / 60.0, "ft3/s": _FT ** 3, "cfs": _FT ** 3,
                    "ft3/min": _FT ** 3 / 60.0, "cfm": _FT ** 3 / 60.0, "ft3/h": _FT ** 3 / 3600.0},
    "length": {"m": 1.0, "mm": 1e-3, "cm": 1e-2, "ft": _FT, "in": 0.0254},
    "velocity": {"m/s": 1.0, "ft/s": _FT, "ft/min": _FT / 60.0, "fpm": _FT / 60.0},
}


def parse_with_unit(text: str, kind: str, system: str = SI) -> float:
    """A typed value such as ``"500 cfm"`` or ``"3 ft"`` as SI. A bare number is read in *system* (like ``from_display``)."""
    import re
    m = re.fullmatch(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-z0-9/^]*)\s*", str(text))
    if not m:
        raise ValueError(f"cannot read {text!r} as a number with an optional unit")
    value, unit = float(m.group(1)), m.group(2).lower().replace("^", "")
    if not unit:
        return from_display(value, kind, system)
    table = UNIT_ALIASES.get(kind, {})
    if unit not in table:
        raise ValueError(f"unknown unit {m.group(2)!r} for {kind}; use one of: " + ", ".join(table) if table else
                         f"no typed units are defined for {kind}")
    return value * table[unit]


def kinds() -> List[str]:
    return sorted(QUANTITIES)


def _q(kind: str) -> Quantity:
    try:
        return QUANTITIES[kind]
    except KeyError:
        raise KeyError(f"unknown quantity kind {kind!r}; known: {', '.join(kinds())}") from None


def _check(system: str) -> str:
    s = (system or "").upper()
    if s in ("ENGLISH", "IMPERIAL", "US"):
        s = ENGLISH
    if s not in SYSTEMS:
        raise ValueError("unit system must be 'SI' or 'EN'")
    return s


def label(kind: str, system: str) -> str:
    q = _q(kind)
    return q.si if _check(system) == SI else q.en


def to_display(value: float, kind: str, system: str) -> float:
    """SI value -> value in *system*."""
    q = _q(kind)
    return float(value) if _check(system) == SI else float(value) * q.factor + q.offset


def from_display(value: float, kind: str, system: str) -> float:
    """Value typed in *system* -> SI."""
    q = _q(kind)
    return float(value) if _check(system) == SI else (float(value) - q.offset) / q.factor


def convert(value: float, kind: str, from_system: str, to_system: str) -> float:
    return to_display(from_display(value, kind, from_system), kind, to_system)
