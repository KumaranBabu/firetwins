"""Which tab each field goes on, per surface type and for materials (PyroSim's Edit Surfaces / Edit Materials), free of Qt.

A type's tabs show the fields that matter for it. Every field not placed on a tab lands on **Advanced**, so choosing
a type never hides data: a Burner's leftover layers are still reachable there, and the editor shows a warning when
the combination contradicts itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .model import FieldSpec

ADVANCED = "Advanced"

_GENERAL = ["name", "enabled", "tags"]
_APPEARANCE = ["color", "rgb", "transparency", "texture_map", "texture_width", "texture_height"]
_THERMAL = ["emissivity", "backing", "heat_transfer_coefficient", "adiabatic", "external_flux", "ignition_temperature",
            "burn_away"]
_HEAT_RELEASE = ["heat_release_rate", "tau_q", "ramp_q"]
_FLOW = ["vel", "volume_flow", "mass_flux", "mass_flux_total", "ramp_v", "ramp_mf", "spec_id_surf"]
_TEMPERATURE = ["tmp_front", "tmp_back", "tau_t", "ramp_t"]
_LAYERS = ["layers", "matl_id"]
_LEAK = ["leak_path"]
_GEOMETRY = ["geometry", "inner_radius", "roughness", "free_slip", "no_slip"]
_PARTICLES = ["part_id"]

# kind -> ordered (tab, fields)
SURFACE_LAYOUTS: Dict[str, List] = {
    "basic": [("General", _GENERAL), ("Appearance", _APPEARANCE), ("Thermal", _THERMAL), ("Geometry", _GEOMETRY)],
    "burner": [("General", _GENERAL), ("Heat Release", _HEAT_RELEASE), ("Thermal", _THERMAL), ("Geometry", _GEOMETRY),
               ("Particle Injection", _PARTICLES), ("Appearance", _APPEARANCE)],
    "supply": [("General", _GENERAL), ("Flow", _FLOW), ("Thermal", _THERMAL), ("Appearance", _APPEARANCE)],
    "exhaust": [("General", _GENERAL), ("Flow", _FLOW), ("Thermal", _THERMAL), ("Appearance", _APPEARANCE)],
    "heater_cooler": [("General", _GENERAL), ("Temperature", _TEMPERATURE), ("Thermal", _THERMAL),
                      ("Appearance", _APPEARANCE)],
    "layered": [("General", _GENERAL), ("Layers", _LAYERS), ("Thermal", _THERMAL), ("Geometry", _GEOMETRY),
                ("Appearance", _APPEARANCE)],
    "air_leak": [("General", _GENERAL), ("Leak", _LEAK), ("Appearance", _APPEARANCE)],
    "general": [("General", _GENERAL), ("Heat Release", _HEAT_RELEASE), ("Flow", _FLOW), ("Temperature", _TEMPERATURE),
                ("Layers", _LAYERS), ("Leak", _LEAK), ("Thermal", _THERMAL), ("Geometry", _GEOMETRY),
                ("Particle Injection", _PARTICLES), ("Appearance", _APPEARANCE)],
}

MATERIAL_LAYOUT: List = [
    ("General", ["name", "enabled", "tags"]),
    ("Thermal Properties", ["density", "conductivity", "specific_heat", "emissivity", "absorption_coefficient",
                            "conductivity_ramp", "specific_heat_ramp", "boiling_temperature"]),
    ("Pyrolysis", ["heat_of_reaction", "heat_of_combustion", "a", "e", "n_s", "reference_temperature",
                   "reference_rate", "pyrolysis_range", "n_reactions"]),
    ("Reactions", ["reactions"]),
]
BYPRODUCT_FIELDS = ("nu_residue", "nu_gases", "spec_ids")      # edited together on the Byproducts tab


@dataclass
class Layout:
    tabs: Dict[str, List[str]] = field(default_factory=dict)         # tab -> field names, in order
    hidden: Set[str] = field(default_factory=set)                    # fields a custom widget edits instead


def _place(plan: List, specs: List[FieldSpec], hidden: Set[str]) -> Layout:
    names = [s.name for s in specs]
    tabs: Dict[str, List[str]] = {}
    used: Set[str] = set(hidden)
    for tab, wanted in plan:
        here = [n for n in wanted if n in names and n not in used]
        if here:
            tabs[tab] = here
            used.update(here)
    rest = [n for n in names if n not in used]
    if rest:
        tabs[ADVANCED] = rest
    return Layout(tabs, set(hidden))


def surface_layout(kind: str, specs: List[FieldSpec]) -> Layout:
    if kind not in SURFACE_LAYOUTS:
        raise ValueError(f"unknown surface type {kind!r}")
    return _place(SURFACE_LAYOUTS[kind], specs, set())


def material_layout(specs: List[FieldSpec]) -> Layout:
    return _place(MATERIAL_LAYOUT, specs, set(BYPRODUCT_FIELDS))


def layout_for(attr: str, specs: List[FieldSpec], kind: Optional[str] = None) -> Optional[Layout]:
    """The custom layout for a collection, or None to use the generic category tabs."""
    if attr == "surfaces":
        return surface_layout(kind or "general", specs)
    if attr == "materials":
        return material_layout(specs)
    return None
