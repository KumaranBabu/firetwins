"""
PyFDS Reaction Library
=======================
Predefined FDS6 fuel reactions covering all 25 fuels in the standard FDS
validation guide.  Each entry provides the minimal parameters needed to
construct a ``Reaction`` entity.

Usage
-----
>>> from pyfds.domain.reactions import get_fuel, list_fuels, FUEL_LIBRARY
>>> params = get_fuel("PROPANE")
>>> print(params["heat_of_combustion"])  # 46334 kJ/kg
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fuel database
# ---------------------------------------------------------------------------

FUEL_LIBRARY: Dict[str, Dict[str, Any]] = {
    "METHANE": {
        "fuel": "METHANE",
        "formula": "CH4",
        "heat_of_combustion": 50050.0,
        "soot_yield": 0.009,
        "co_yield": 0.001,
        "radiative_fraction": 0.15,
        "c": 1, "h": 4,
    },
    "ETHANE": {
        "fuel": "ETHANE",
        "formula": "C2H6",
        "heat_of_combustion": 47520.0,
        "soot_yield": 0.009,
        "co_yield": 0.001,
        "radiative_fraction": 0.26,
        "c": 2, "h": 6,
    },
    "PROPANE": {
        "fuel": "PROPANE",
        "formula": "C3H8",
        "heat_of_combustion": 46334.0,
        "soot_yield": 0.010,
        "co_yield": 0.005,
        "radiative_fraction": 0.29,
        "c": 3, "h": 8,
    },
    "BUTANE": {
        "fuel": "BUTANE",
        "formula": "C4H10",
        "heat_of_combustion": 45714.0,
        "soot_yield": 0.010,
        "co_yield": 0.006,
        "radiative_fraction": 0.30,
        "c": 4, "h": 10,
    },
    "ETHYLENE": {
        "fuel": "ETHYLENE",
        "formula": "C2H4",
        "heat_of_combustion": 47158.0,
        "soot_yield": 0.043,
        "co_yield": 0.013,
        "radiative_fraction": 0.36,
        "c": 2, "h": 4,
    },
    "PROPYLENE": {
        "fuel": "PROPYLENE",
        "formula": "C3H6",
        "heat_of_combustion": 45789.0,
        "soot_yield": 0.095,
        "co_yield": 0.018,
        "radiative_fraction": 0.33,
        "c": 3, "h": 6,
    },
    "ACETYLENE": {
        "fuel": "ACETYLENE",
        "formula": "C2H2",
        "heat_of_combustion": 48225.0,
        "soot_yield": 0.096,
        "co_yield": 0.040,
        "radiative_fraction": 0.40,
        "c": 2, "h": 2,
    },
    "HEPTANE": {
        "fuel": "HEPTANE",
        "formula": "C7H16",
        "heat_of_combustion": 44557.0,
        "soot_yield": 0.037,
        "co_yield": 0.006,
        "radiative_fraction": 0.32,
        "c": 7, "h": 16,
    },
    "OCTANE": {
        "fuel": "OCTANE",
        "formula": "C8H18",
        "heat_of_combustion": 44427.0,
        "soot_yield": 0.039,
        "co_yield": 0.007,
        "radiative_fraction": 0.32,
        "c": 8, "h": 18,
    },
    "DECANE": {
        "fuel": "DECANE",
        "formula": "C10H22",
        "heat_of_combustion": 44239.0,
        "soot_yield": 0.042,
        "co_yield": 0.006,
        "radiative_fraction": 0.32,
        "c": 10, "h": 22,
    },
    "DODECANE": {
        "fuel": "DODECANE",
        "formula": "C12H26",
        "heat_of_combustion": 44128.0,
        "soot_yield": 0.042,
        "co_yield": 0.007,
        "radiative_fraction": 0.30,
        "c": 12, "h": 26,
    },
    "TOLUENE": {
        "fuel": "TOLUENE",
        "formula": "C7H8",
        "heat_of_combustion": 39700.0,
        "soot_yield": 0.178,
        "co_yield": 0.025,
        "radiative_fraction": 0.42,
        "c": 7, "h": 8,
    },
    "BENZENE": {
        "fuel": "BENZENE",
        "formula": "C6H6",
        "heat_of_combustion": 39400.0,
        "soot_yield": 0.182,
        "co_yield": 0.067,
        "radiative_fraction": 0.45,
        "c": 6, "h": 6,
    },
    "METHANOL": {
        "fuel": "METHANOL",
        "formula": "CH4O",
        "heat_of_combustion": 19830.0,
        "soot_yield": 0.003,
        "co_yield": 0.001,
        "radiative_fraction": 0.18,
        "c": 1, "h": 4, "o": 1,
    },
    "ETHANOL": {
        "fuel": "ETHANOL",
        "formula": "C2H6O",
        "heat_of_combustion": 26830.0,
        "soot_yield": 0.008,
        "co_yield": 0.001,
        "radiative_fraction": 0.25,
        "c": 2, "h": 6, "o": 1,
    },
    "ACETONE": {
        "fuel": "ACETONE",
        "formula": "C3H6O",
        "heat_of_combustion": 29080.0,
        "soot_yield": 0.014,
        "co_yield": 0.003,
        "radiative_fraction": 0.29,
        "c": 3, "h": 6, "o": 1,
    },
    "WOOD": {
        "fuel": "WOOD",
        "formula": "C3.4H6.2O2.5",
        "heat_of_combustion": 17000.0,
        "soot_yield": 0.015,
        "co_yield": 0.004,
        "radiative_fraction": 0.35,
        "c": 3.4, "h": 6.2, "o": 2.5,
    },
    "POLYURETHANE": {
        "fuel": "POLYURETHANE",
        "formula": "C6H7NO",
        "heat_of_combustion": 23200.0,
        "soot_yield": 0.131,
        "co_yield": 0.031,
        "radiative_fraction": 0.36,
        "c": 6, "h": 7, "n": 1, "o": 1,
    },
    "POLYSTYRENE": {
        "fuel": "POLYSTYRENE",
        "formula": "C8H8",
        "heat_of_combustion": 39000.0,
        "soot_yield": 0.164,
        "co_yield": 0.060,
        "radiative_fraction": 0.41,
        "c": 8, "h": 8,
    },
    "POLYETHYLENE": {
        "fuel": "POLYETHYLENE",
        "formula": "C2H4",
        "heat_of_combustion": 43300.0,
        "soot_yield": 0.060,
        "co_yield": 0.024,
        "radiative_fraction": 0.36,
        "c": 2, "h": 4,
    },
    "POLYPROPYLENE": {
        "fuel": "POLYPROPYLENE",
        "formula": "C3H6",
        "heat_of_combustion": 43300.0,
        "soot_yield": 0.059,
        "co_yield": 0.024,
        "radiative_fraction": 0.36,
        "c": 3, "h": 6,
    },
    "NYLON": {
        "fuel": "NYLON",
        "formula": "C12H22N2O2",
        "heat_of_combustion": 27900.0,
        "soot_yield": 0.075,
        "co_yield": 0.016,
        "radiative_fraction": 0.34,
        "c": 12, "h": 22, "n": 2, "o": 2,
    },
    "HYDROGEN": {
        "fuel": "HYDROGEN",
        "formula": "H2",
        "heat_of_combustion": 119600.0,
        "soot_yield": 0.0,
        "co_yield": 0.0,
        "radiative_fraction": 0.17,
        "h": 2,
    },
    "CARBON_MONOXIDE": {
        "fuel": "CARBON MONOXIDE",
        "formula": "CO",
        "heat_of_combustion": 10100.0,
        "soot_yield": 0.0,
        "co_yield": 0.0,
        "radiative_fraction": 0.24,
        "c": 1, "o": 1,
    },
    "ISOPROPANOL": {
        "fuel": "ISOPROPANOL",
        "formula": "C3H8O",
        "heat_of_combustion": 30700.0,
        "soot_yield": 0.015,
        "co_yield": 0.005,
        "radiative_fraction": 0.27,
        "c": 3, "h": 8, "o": 1,
    },
}

# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------

def list_fuels() -> List[str]:
    """Return sorted list of available fuel names."""
    return sorted(FUEL_LIBRARY)


def get_fuel(fuel_name: str) -> Dict[str, Any]:
    """
    Return reaction parameters for *fuel_name*.

    Parameters
    ----------
    fuel_name:
        Case-insensitive fuel identifier (e.g. "PROPANE", "propane").

    Returns
    -------
    dict
        Keyword arguments suitable for constructing a ``Reaction`` entity.

    Raises
    ------
    KeyError
        When the fuel is not in the library.
    """
    key = fuel_name.upper().replace("-", "_").replace(" ", "_")
    if key not in FUEL_LIBRARY:
        available = ", ".join(list_fuels())
        raise KeyError(
            f"Fuel '{fuel_name}' not found. Available: {available}"
        )
    return dict(FUEL_LIBRARY[key])


def make_reaction(fuel_name: str, reaction_name: Optional[str] = None):
    """
    Convenience factory: return a fully initialised ``Reaction`` entity
    for *fuel_name* from the library.

    Parameters
    ----------
    fuel_name:
        Library fuel key (case-insensitive).
    reaction_name:
        Optional FDS ``ID=`` override; defaults to *fuel_name* in title case.
    """
    from pyfds.domain.model import Reaction
    params = get_fuel(fuel_name)
    name = reaction_name or fuel_name.replace("_", " ").title()
    fuel_str = params.pop("fuel", None)
    formula = params.pop("formula", None)
    r = Reaction(name=name, **params)
    if fuel_str:
        r.fuel = fuel_str
    if formula:
        r.formula = formula
    return r
