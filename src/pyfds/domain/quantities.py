"""
FDS Quantity Library
=====================
Complete database of all valid FDS 6.x output quantities with their name,
short_name, units, valid output contexts, and description.

Usage::

    from pyfds.domain.quantities import (
        FdsQuantity, list_quantities, get_quantity,
        quantities_for_context, QUANTITY_DB,
    )

    q = get_quantity("TEMPERATURE")
    print(q.units)          # "C"
    print(q.valid_for_slcf) # True

    temps = quantities_for_context("BNDF")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional


# Valid output contexts
CONTEXT_DEVC = "DEVC"
CONTEXT_SLCF = "SLCF"
CONTEXT_BNDF = "BNDF"
CONTEXT_ISOF = "ISOF"
CONTEXT_PL3D = "PL3D"
CONTEXT_PROF = "PROF"
CONTEXT_PART = "PART"

_ALL_GAS   = frozenset({CONTEXT_DEVC, CONTEXT_SLCF, CONTEXT_PL3D, CONTEXT_PROF})
_ALL       = frozenset({CONTEXT_DEVC, CONTEXT_SLCF, CONTEXT_BNDF, CONTEXT_ISOF,
                        CONTEXT_PL3D, CONTEXT_PROF})
_GAS_DEVC  = frozenset({CONTEXT_DEVC, CONTEXT_SLCF, CONTEXT_PROF})
_WALL      = frozenset({CONTEXT_DEVC, CONTEXT_BNDF})
_DEVC_ONLY = frozenset({CONTEXT_DEVC})
_SLCF_ONLY = frozenset({CONTEXT_SLCF, CONTEXT_ISOF})
_ISOF_SLCF = frozenset({CONTEXT_ISOF, CONTEXT_SLCF})
_PART      = frozenset({CONTEXT_PART, CONTEXT_DEVC})


@dataclass
class FdsQuantity:
    """One entry in the FDS quantity database."""
    name: str
    short_name: str
    units: str
    contexts: FrozenSet[str]
    description: str
    fds_name: Optional[str] = None   # canonical FDS QUANTITY= string (if differs from name)

    # Convenience predicates
    @property
    def valid_for_devc(self) -> bool:
        return CONTEXT_DEVC in self.contexts

    @property
    def valid_for_slcf(self) -> bool:
        return CONTEXT_SLCF in self.contexts

    @property
    def valid_for_bndf(self) -> bool:
        return CONTEXT_BNDF in self.contexts

    @property
    def valid_for_isof(self) -> bool:
        return CONTEXT_ISOF in self.contexts

    @property
    def valid_for_pl3d(self) -> bool:
        return CONTEXT_PL3D in self.contexts

    @property
    def valid_for_prof(self) -> bool:
        return CONTEXT_PROF in self.contexts

    @property
    def valid_for_part(self) -> bool:
        return CONTEXT_PART in self.contexts

    def __repr__(self) -> str:
        ctx = ", ".join(sorted(self.contexts))
        return f"FdsQuantity({self.name!r}, units={self.units!r}, contexts=[{ctx}])"


def _q(
    name: str,
    short: str,
    units: str,
    contexts: FrozenSet[str],
    desc: str,
    fds_name: Optional[str] = None,
) -> FdsQuantity:
    return FdsQuantity(
        name=name,
        short_name=short,
        units=units,
        contexts=contexts,
        description=desc,
        fds_name=fds_name or name,
    )


# ---------------------------------------------------------------------------
# Quantity Database
# ---------------------------------------------------------------------------

QUANTITY_DB: Dict[str, FdsQuantity] = {}

def _add(*args, **kwargs) -> None:
    q = _q(*args, **kwargs)
    QUANTITY_DB[q.name] = q


# ── Thermal ─────────────────────────────────────────────────────────────────
_add("TEMPERATURE",            "TEMP",  "C",      _ALL,
     "Gas-phase temperature")
_add("ADIABATIC SURFACE TEMPERATURE", "AST", "C", frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Adiabatic surface temperature (used for structural fire analysis)")
_add("RADIATIVE HEAT FLUX",    "Q_RAD", "kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Radiative component of surface heat flux")
_add("CONVECTIVE HEAT FLUX",   "Q_CON", "kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Convective component of surface heat flux")
_add("NET HEAT FLUX",          "Q_NET", "kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Total net heat flux at surface (convective + radiative)")
_add("HEAT FLUX",              "Q",     "kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Incident heat flux at surface")
_add("BACK WALL TEMPERATURE",  "T_BACK","C",      _WALL,
     "Temperature at the back surface of a solid wall")
_add("WALL TEMPERATURE",       "T_WALL","C",      _WALL,
     "Front-face wall surface temperature")
_add("SOLID TEMPERATURE",      "T_SOLID","C",     frozenset({CONTEXT_BNDF, CONTEXT_PROF}),
     "Temperature inside a solid material (requires PROF output)")

# ── Flow / Momentum ──────────────────────────────────────────────────────────
_add("VELOCITY",               "VEL",   "m/s",    _ALL_GAS,
     "Magnitude of gas velocity vector")
_add("U-VELOCITY",             "U",     "m/s",    _ALL_GAS,
     "Gas velocity in x-direction")
_add("V-VELOCITY",             "V",     "m/s",    _ALL_GAS,
     "Gas velocity in y-direction")
_add("W-VELOCITY",             "W",     "m/s",    _ALL_GAS,
     "Gas velocity in z-direction")
_add("PRESSURE",               "P",     "Pa",     _ALL_GAS,
     "Thermodynamic (background) pressure")
_add("PRESSURE COEFFICIENT",   "CP",    "1",      frozenset({CONTEXT_SLCF, CONTEXT_DEVC}),
     "Pressure coefficient (P - P_atm) / (0.5 rho U^2)")
_add("DYNAMIC PRESSURE",       "P_DYN", "Pa",     _ALL_GAS,
     "Dynamic pressure 0.5 × rho × |u|^2")
_add("TURBULENT VISCOSITY",    "MU_T",  "kg/m/s", _ALL_GAS,
     "SGS turbulent viscosity")

# ── Density / Species ────────────────────────────────────────────────────────
_add("DENSITY",                "RHO",   "kg/m3",  _ALL_GAS,
     "Total gas mixture density")
_add("VOLUME FRACTION",        "X_SPEC", "mol/mol", _ALL_GAS, "Species volume (mole) fraction; needs SPEC_ID")
_add("MASS FRACTION",          "Y_SPEC", "kg/kg",   _ALL_GAS, "Species mass fraction; needs SPEC_ID")
_add("MIXTURE FRACTION",       "Z",     "1",      _ALL_GAS,
     "Mixture fraction (fuel–air coupling scalar)")
_add("OXYGEN",                 "O2",    "kg/kg",  _ALL_GAS,
     "Oxygen mass fraction")
_add("CARBON MONOXIDE",        "CO",    "kg/kg",  _ALL_GAS,
     "Carbon monoxide mass fraction")
_add("CARBON DIOXIDE",         "CO2",   "kg/kg",  _ALL_GAS,
     "Carbon dioxide mass fraction")
_add("SOOT",                   "SOOT",  "kg/kg",  _ALL_GAS,
     "Soot mass fraction")
_add("WATER VAPOR",            "H2O",   "kg/kg",  _ALL_GAS,
     "Water vapor mass fraction")
_add("FUEL",                   "FUEL",  "kg/kg",  _ALL_GAS,
     "Fuel species mass fraction")
_add("HYDROGEN",               "H2",    "kg/kg",  _ALL_GAS,
     "Hydrogen mass fraction")
_add("NITROGEN",               "N2",    "kg/kg",  _ALL_GAS,
     "Nitrogen mass fraction")
_add("HCN",                    "HCN",   "kg/kg",  _ALL_GAS,
     "Hydrogen cyanide mass fraction")
_add("HCL",                    "HCL",   "kg/kg",  _ALL_GAS,
     "Hydrogen chloride mass fraction")

# ── Combustion / Fire ─────────────────────────────────────────────────────────
_add("HRRPUV",                 "HRRPUV","kW/m3",  frozenset({CONTEXT_SLCF, CONTEXT_DEVC, CONTEXT_PL3D}),
     "Heat release rate per unit volume")
_add("HRRPUA",                 "HRRPUA","kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Heat release rate per unit area (burning surface)")
_add("HRR",                    "HRR",   "kW",     _DEVC_ONLY,
     "Total heat release rate (integral over domain or volume)")
_add("BURNING RATE",           "BURN",  "kg/m2/s",frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Surface burning rate (pyrolysis mass flux)")
_add("MASS FLUX",              "M_FLUX","kg/m2/s",frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Gas mass flux normal to a surface")
_add("MASS FLUX WALL NORMAL",  "MFN",   "kg/m2/s",frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Gas mass flux in wall-normal direction")
_add("FLAME TEMPERATURE",      "T_FL",  "C",      frozenset({CONTEXT_SLCF, CONTEXT_DEVC}),
     "Gas temperature clipped to regions with significant combustion")
_add("EXTINCTION COEFFICIENT", "KAPPA", "1/m",    _ALL_GAS,
     "Radiative extinction coefficient (absorption + scattering)")
_add("ABSORPTION COEFFICIENT", "ABS",   "1/m",    _ALL_GAS,
     "Radiative absorption coefficient")

# ── Visibility / Smoke ───────────────────────────────────────────────────────
_add("VISIBILITY",             "VIS",   "m",      _ALL_GAS,
     "Visibility through smoke (Purser/Jin correlation)")
_add("OPTICAL DENSITY",        "OD",    "1/m",    _ALL_GAS,
     "Smoke optical density")
_add("SOOT DENSITY",           "RHO_S", "mg/m3",  _ALL_GAS,
     "Soot mass concentration")

# ── Radiation ─────────────────────────────────────────────────────────────────
_add("INCIDENT HEAT FLUX",     "Q_INC", "kW/m2",  frozenset({CONTEXT_DEVC, CONTEXT_BNDF}),
     "Incident (incoming) radiative heat flux")
_add("RADIATIVE HEAT FLUX GAS","Q_RAD_G","kW/m2", frozenset({CONTEXT_SLCF, CONTEXT_DEVC}),
     "Radiative heat flux divergence in gas phase")
_add("RADIATION LOSS",         "Q_LOSS","kW/m2",  _WALL,
     "Radiation emitted from a hot surface")

# ── Zone / Layer ──────────────────────────────────────────────────────────────
_add("LAYER HEIGHT",           "ZLAYER","m",       _DEVC_ONLY,
     "Height of hot gas layer above floor (requires &ZONE or device at multiple heights)")
_add("UPPER TEMPERATURE",      "T_UP",  "C",       _DEVC_ONLY,
     "Mean temperature of upper hot layer")
_add("LOWER TEMPERATURE",      "T_LO",  "C",       _DEVC_ONLY,
     "Mean temperature of lower cool layer")
_add("UPPER DENSITY",          "RHO_UP","kg/m3",   _DEVC_ONLY,
     "Mean density of upper hot layer")
_add("LOWER DENSITY",          "RHO_LO","kg/m3",   _DEVC_ONLY,
     "Mean density of lower cool layer")
_add("CEILING TEMPERATURE",    "T_CEIL","C",        _DEVC_ONLY,
     "Gas temperature at ceiling (top of domain or specified height)")

# ── Control / Sprinkler / Detector ───────────────────────────────────────────
_add("CONTROL",                "CTRL_ST", "1",       _DEVC_ONLY,
     "Device that carries a control state (nozzles, vents, fans switched by a CTRL)")
_add("CONTROL VALUE",          "CTRL",  "1",        _DEVC_ONLY,
     "Control function value (0 or 1, or float for ramp-driven CTRLs)")
_add("TIME",                   "TIME",  "s",         _DEVC_ONLY,
     "Simulation time (diagnostic / reference channel)")
_add("LINK TEMPERATURE",       "T_LINK","C",         _DEVC_ONLY,
     "Sprinkler link temperature (for RTI model)")
_add("ACTIVATION TIME",        "T_ACT", "s",         _DEVC_ONLY,
     "Time at which a sprinkler or detector activates")

# ── Particle ─────────────────────────────────────────────────────────────────
_add("PARTICLE TEMPERATURE",   "P_TEMP","C",         _PART,
     "Temperature of Lagrangian particles")
_add("PARTICLE VELOCITY",      "P_VEL", "m/s",       _PART,
     "Speed of Lagrangian particles")
_add("PARTICLE DIAMETER",      "P_DIAM","m",         _PART,
     "Diameter of Lagrangian particles (droplets)")
_add("PARTICLE MASS",          "P_MASS","kg",        _PART,
     "Mass of a Lagrangian particle")
_add("PARTICLE RADIATIVE FLUX","P_Q_R", "kW/m2",     _PART,
     "Radiative flux absorbed by a particle")

# ── HVAC / Duct ───────────────────────────────────────────────────────────────
_add("DUCT VOLUME FLOW",       "Q_DUC", "m3/s",      _DEVC_ONLY,
     "Volumetric flow rate in an HVAC duct")
_add("DUCT VELOCITY",          "V_DUC", "m/s",       _DEVC_ONLY,
     "Mean velocity in an HVAC duct")
_add("DUCT PRESSURE",          "P_DUC", "Pa",        _DEVC_ONLY,
     "Static pressure in an HVAC duct")
_add("NODE PRESSURE",          "P_NOD", "Pa",        _DEVC_ONLY,
     "Pressure at an HVAC node")
_add("NODE TEMPERATURE",       "T_NOD", "C",         _DEVC_ONLY,
     "Temperature at an HVAC node")
_add("MASS FLOW RATE",         "M_RATE","kg/s",      _DEVC_ONLY,
     "Mass flow rate through a duct or vent")
_add("DUCT MASS FLOW",         "M_DUC", "kg/s",      _DEVC_ONLY, "Mass flow in a duct (needs DUCT_ID)")
_add("DUCT TEMPERATURE",       "T_DUC", "C",         _DEVC_ONLY, "Temperature of the flow in a duct (needs DUCT_ID)")
_add("DUCT DENSITY",           "RHO_DUC", "kg/m3",   _DEVC_ONLY, "Density of the flow in a duct (needs DUCT_ID)")
_add("DUCT ENTHALPY FLOW",     "H_DUC", "kW",        _DEVC_ONLY, "Enthalpy flow in a duct (needs DUCT_ID)")
_add("DUCT LOSS",              "K_DUC", "1",         _DEVC_ONLY, "Total flow loss coefficient of a duct (needs DUCT_ID)")
_add("DUCT MASS FRACTION",     "Y_DUC", "kg/kg",     _DEVC_ONLY, "Mass fraction of a species in a duct (needs DUCT_ID, SPEC_ID)")
_add("DUCT VOLUME FRACTION",   "X_DUC", "mol/mol",   _DEVC_ONLY, "Volume fraction of a species in a duct (needs DUCT_ID, SPEC_ID)")
_add("DUCT CELL DENSITY",      "RHO_DCL", "kg/m3",   _DEVC_ONLY, "Gas density in a duct cell (needs DUCT_ID, CELL_L)")
_add("DUCT CELL TEMPERATURE",  "T_DCL", "C",         _DEVC_ONLY, "Gas temperature in a duct cell (needs DUCT_ID, CELL_L)")
_add("DUCT CELL MASS FRACTION", "Y_DCL", "kg/kg",    _DEVC_ONLY, "Species mass fraction in a duct cell (needs DUCT_ID, CELL_L, SPEC_ID)")
_add("DUCT CELL VOLUME FRACTION", "X_DCL", "mol/mol", _DEVC_ONLY, "Species volume fraction in a duct cell (needs DUCT_ID, CELL_L, SPEC_ID)")
_add("NODE DENSITY",           "RHO_NOD", "kg/m3",   _DEVC_ONLY, "Density of the flow through a node (needs NODE_ID)")
_add("NODE ENTHALPY",          "H_NOD", "kJ/kg",     _DEVC_ONLY, "Enthalpy of a node (needs NODE_ID)")
_add("NODE SENSIBLE ENTHALPY", "HS_NOD", "kJ/kg",    _DEVC_ONLY, "Sensible enthalpy of a node (needs NODE_ID)")
_add("NODE MASS FRACTION",     "Y_NOD", "kg/kg",     _DEVC_ONLY, "Species mass fraction in a node (needs NODE_ID, SPEC_ID)")
_add("NODE VOLUME FRACTION",   "X_NOD", "mol/mol",   _DEVC_ONLY, "Species volume fraction in a node (needs NODE_ID, SPEC_ID)")
_add("NODE PRESSURE DIFFERENCE", "DP_NOD", "Pa",     _DEVC_ONLY, "Pressure of the second node minus the first (NODE_ID with two nodes)")
_add("FAN PRESSURE",           "P_FAN", "Pa",        _DEVC_ONLY, "Pressure rise of a fan (needs DUCT_ID)")
_add("AIRCOIL HEAT EXCHANGE",  "Q_ACL", "kW",        _DEVC_ONLY, "Heat exchange rate of an aircoil (needs DUCT_ID)")
_add("FILTER LOADING",         "LD_FLT", "kg",       _DEVC_ONLY, "Loading of a species in a filter (needs NODE_ID, SPEC_ID)")
_add("FILTER LOSS",            "K_FLT", "1",         _DEVC_ONLY, "Flow loss through a filter (needs NODE_ID)")
# ── Detectors and tenability ─────────────────────────────────────────────────
_add("PATH OBSCURATION",       "OB_PATH", "%",       _DEVC_ONLY, "Beam detector: smoke obscuration along the XB line")
_add("TRANSMISSION",           "TR_PATH", "%/m",     _DEVC_ONLY, "Beam transmission along the XB line")
_add("CHAMBER OBSCURATION",    "OB_CHAM", "%/m",     _DEVC_ONLY, "Smoke detector chamber obscuration (use with PROP_ID)")
_add("ASPIRATION",             "OB_ASP", "%/m",      _DEVC_ONLY, "Central detector of an aspiration (VESDA) system")
_add("FED",                    "FED",   "1",         _DEVC_ONLY, "Fractional effective dose, asphyxiants (PROP_ID may set FED_ACTIVITY)")
_add("FIC",                    "FIC",   "1",         _DEVC_ONLY, "Fractional incapacitating concentration, irritants")

# ── Structural / Solid ────────────────────────────────────────────────────────
_add("INSIDE WALL TEMPERATURE","T_IN",  "C",         frozenset({CONTEXT_DEVC, CONTEXT_PROF}),
     "Temperature at a point inside a solid wall (requires PROF)")
_add("INNER TEMPERATURE",      "T_INNR","C",         frozenset({CONTEXT_DEVC, CONTEXT_PROF}),
     "Interior node temperature within a solid material")
_add("SURFACE DENSITY",        "RHO_W", "kg/m2",     _WALL,
     "Integrated density of a burning surface layer")
_add("SURFACE DEPOSITION",     "DEP",   "kg/m2",     _WALL,
     "Mass deposited on a surface (e.g. soot deposition)")
_add("HEAT TRANSFER COEFFICIENT","HTC", "W/m2/K",    _WALL,
     "Convective heat transfer coefficient at the wall")

# ── Pressure solver / numerical ───────────────────────────────────────────────
_add("DIVERGENCE",             "DIV",   "1/s",       frozenset({CONTEXT_SLCF, CONTEXT_DEVC}),
     "Velocity divergence (diagnostic — should be near zero at convergence)")
_add("VELOCITY ERROR",         "ERR_V", "m/s",       _DEVC_ONLY,
     "Maximum velocity error in pressure iteration")
_add("CPU TIME",               "CPU",   "s",         _DEVC_ONLY,
     "Cumulative CPU time")
_add("TOTAL PRESSURE",         "P_TOT", "Pa",        _ALL_GAS,
     "Total (stagnation) pressure P + 0.5 rho |u|^2")

# ── Miscellaneous ─────────────────────────────────────────────────────────────
_add("RELATIVE HUMIDITY",      "RH",    "%",         _ALL_GAS,
     "Local relative humidity")
_add("ENTHALPY",               "ENTH",  "kJ/kg",     _ALL_GAS,
     "Specific enthalpy of gas mixture")
_add("GAS DENSITY",            "RHO_G", "kg/m3",     _ALL_GAS,
     "Alias for DENSITY (gas-phase mixture density)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_quantities(context: Optional[str] = None) -> List[str]:
    """Return sorted quantity names, optionally filtered by output context.

    Parameters
    ----------
    context : str, optional
        One of ``'DEVC'``, ``'SLCF'``, ``'BNDF'``, ``'ISOF'``,
        ``'PL3D'``, ``'PROF'``, ``'PART'``.
    """
    if context is None:
        return sorted(QUANTITY_DB)
    ctx = context.upper()
    return sorted(name for name, q in QUANTITY_DB.items() if ctx in q.contexts)


def get_quantity(name: str) -> FdsQuantity:
    """Look up a quantity by name (case-insensitive).

    Raises ``KeyError`` with a suggestion list if not found.
    """
    key = name.upper()
    # exact match
    for k, v in QUANTITY_DB.items():
        if k.upper() == key:
            return v
    available = ", ".join(sorted(QUANTITY_DB)[:10])
    raise KeyError(
        f"Unknown FDS quantity {name!r}. "
        f"First 10 available: {available} ..."
    )


def quantities_for_context(context: str) -> List[FdsQuantity]:
    """Return all FdsQuantity objects valid for *context*."""
    ctx = context.upper()
    return sorted(
        (q for q in QUANTITY_DB.values() if ctx in q.contexts),
        key=lambda q: q.name,
    )


def validate_quantity(name: str, context: str) -> bool:
    """Return True if *name* is a valid FDS quantity in *context*, False otherwise."""
    try:
        q = get_quantity(name)
        return context.upper() in q.contexts
    except KeyError:
        return False
