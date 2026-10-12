"""The eight PyroSim surface types, expressed over the one generic ``Surface`` (SRF-01).

``kind_of`` says which type a surface is; ``problems`` lists contradictions; ``build`` makes the
field values for a surface of a chosen type from the few values that type needs. Pure functions.
"""
from __future__ import annotations

from typing import Any, Dict, List

KINDS = {
    "air_leak": "Air Leak - leaks between two pressure zones",
    "basic": "Basic - inert wall, no heat or flow",
    "burner": "Burner - fixed heat release rate per area",
    "exhaust": "Exhaust - flow out of the domain",
    "general": "General Surface - any mix of the fields",
    "heater_cooler": "Heater/Cooler - fixed surface temperature",
    "layered": "Layered - material layers (conduction / pyrolysis)",
    "supply": "Supply - flow into the domain",
}

_FLOW_KEYS = ("vel", "volume_flow", "mass_flux", "mass_flux_total")


def _flows(s) -> List[str]:
    return [k for k in _FLOW_KEYS if getattr(s, k, None) is not None]


def kind_of(s) -> str:
    """The type a surface falls under; ``general`` when it mixes several behaviours."""
    flags = []
    if getattr(s, "leak_path", None):
        flags.append("air_leak")
    if getattr(s, "layers", None):
        flags.append("layered")
    if getattr(s, "heat_release_rate", None) is not None:
        flags.append("burner")
    flow = _flows(s)
    if flow:
        value = getattr(s, flow[0])
        if flow[0] in ("mass_flux", "mass_flux_total"):
            flags.append("supply")             # a mass flux injects gas
        elif value > 0:
            flags.append("exhaust")
        elif value < 0:
            flags.append("supply")
        else:
            flags.append("general")
    if getattr(s, "tmp_front", None) is not None:
        flags.append("heater_cooler")
    if not flags:
        return "basic"
    return flags[0] if len(set(flags)) == 1 else "general"


def problems(s) -> List[str]:
    """Contradictory or incomplete settings on a surface."""
    out: List[str] = []
    flow = _flows(s)
    hrr = getattr(s, "heat_release_rate", None)
    if len(flow) > 1:
        out.append(f"more than one flow specification ({', '.join(flow)}); FDS accepts only one")
    if hrr is not None and getattr(s, "tmp_front", None) is not None:
        out.append("both a heat release rate and a fixed temperature are set")
    if hrr is not None and hrr < 0:
        out.append("heat release rate per area is negative")
    if getattr(s, "layers", None) and (flow or hrr is not None):
        out.append("layers cannot be combined with a prescribed flow or burner heat release")
    if getattr(s, "leak_path", None) and len(s.leak_path) != 2:
        out.append("an air-leak path needs exactly two pressure zones")
    return out


def build(kind: str, **f) -> Dict[str, Any]:
    """Field values for a surface of *kind*; raises ``ValueError`` when a required value is missing.

    ``flow`` is a magnitude in m/s (or give ``volume_flow`` in m3/s); the sign is chosen for the
    type (supply = into the domain). Other keyword arguments pass straight through."""
    if kind not in KINDS:
        raise ValueError(f"unknown surface type {kind!r}; choose from {', '.join(KINDS)}")
    out = dict(f)
    flow = out.pop("flow", None)
    if kind == "burner":
        if not out.get("heat_release_rate") or out["heat_release_rate"] <= 0:
            raise ValueError("a burner needs heat_release_rate (kW/m2) > 0")
    elif kind in ("supply", "exhaust"):
        sign = -1.0 if kind == "supply" else 1.0
        if flow is not None:
            if flow <= 0:
                raise ValueError("flow is a magnitude and must be positive")
            out["vel"] = sign * flow
        elif out.get("volume_flow") is not None:
            if out["volume_flow"] <= 0:
                raise ValueError("volume_flow is a magnitude and must be positive")
            out["volume_flow"] = sign * out["volume_flow"]
        elif not (out.get("mass_flux") is not None and kind == "supply"):
            raise ValueError(f"a {kind} surface needs flow (m/s) or volume_flow (m3/s)")
    elif kind == "heater_cooler":
        if out.get("tmp_front") is None:
            raise ValueError("a heater/cooler needs tmp_front (deg C)")
    elif kind == "layered":
        if not out.get("layers"):
            raise ValueError("a layered surface needs layers")
    elif kind == "air_leak":
        lp = out.get("leak_path")
        if not lp or len(lp) != 2:
            raise ValueError("an air-leak surface needs leak_path=[zone1, zone2]")
    elif kind == "basic":
        bad = [k for k in ("heat_release_rate", "tmp_front", "leak_path", "layers") + _FLOW_KEYS if out.get(k)]
        if bad:
            raise ValueError(f"a basic surface has no {', '.join(bad)}; use another type")
    return out
