"""Library model (LIB-01 / MAT-05): one shape for every kind of reusable definition.

A library *category* names a kind of entity (material, surface, reaction, detector model ...).
A library *entry* is ``{"description": str, "fields": {...}}`` - the keyword values needed to
build that entity. Built-in entries come from the preset tables; user entries are kept by
``api.library`` and can be exported to / imported from JSON.
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple

LIBRARY_FORMAT = "pyfds-library"
LIBRARY_VERSION = 1


class Category(NamedTuple):
    key: str
    label: str
    collection: str     # FdsProject attribute holding the entities
    entity: str         # class name in pyfds.domain.model
    filter: str = ""    # for shared entity classes: which kind (see _kind_matches)


CATEGORIES: Dict[str, Category] = {c.key: c for c in (
    Category("reactions", "Gas-phase Reactions", "reactions", "Reaction"),
    Category("heat_detectors", "Heat Detector Models", "props", "Prop", "heat_detector"),
    Category("materials", "Materials", "materials", "Material"),
    Category("particles", "Particles", "particles", "Particle"),
    Category("smoke_detectors", "Smoke Detector Models", "props", "Prop", "smoke_detector"),
    Category("species", "Species", "species", "Species"),
    Category("spray_models", "Spray Models", "props", "Prop", "spray"),
    Category("sprinkler_links", "Sprinkler Link Models", "props", "Prop", "sprinkler_link"),
    Category("surfaces", "Surfaces", "surfaces", "Surface"),
)}

#: Layer material IDs used by the surface presets that differ from the material preset's key
MATERIAL_ALIASES = {"GYP_BOARD": "gypsum_board"}

#: Typical values, offered as starting points - edit them to match the product you model.
_BUILTIN_PROPS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "heat_detectors": {
        "heat_detector_57C": {"description": "Fixed-temperature heat detector, 57 C (typical)",
                              "fields": {"quantity": "LINK TEMPERATURE", "activation_temperature": 57.0, "rti": 5.0}},
        "heat_detector_74C": {"description": "Fixed-temperature heat detector, 74 C (typical)",
                              "fields": {"quantity": "LINK TEMPERATURE", "activation_temperature": 74.0, "rti": 5.0}},
    },
    "smoke_detectors": {
        "smoke_detector_generic": {"description": "Generic smoke detector, 3.28 %/m obscuration (FDS Guide example)",
                                   "fields": {"quantity": "CHAMBER OBSCURATION", "activation_obscuration": 3.28,
                                              "length": 1.8}},
    },
    "sprinkler_links": {
        "sprinkler_quick_68C": {"description": "Quick-response sprinkler link, 68 C, RTI 50 (typical)",
                                "fields": {"quantity": "SPRINKLER LINK TEMPERATURE", "activation_temperature": 68.0,
                                           "rti": 50.0, "c_factor": 0.7}},
        "sprinkler_standard_74C": {"description": "Standard-response sprinkler link, 74 C, RTI 100 (typical)",
                                   "fields": {"quantity": "SPRINKLER LINK TEMPERATURE", "activation_temperature": 74.0,
                                              "rti": 100.0, "c_factor": 0.7}},
    },
    "species": {
        n.lower().replace(" ", "_"): {"description": f"{n.title()} - a species FDS knows by name (its properties are built in)",
                                      "fields": {}}
        for n in ("CARBON DIOXIDE", "CARBON MONOXIDE", "WATER VAPOR", "OXYGEN", "NITROGEN", "HYDROGEN CHLORIDE",
                  "HYDROGEN CYANIDE", "METHANE", "PROPANE")
    },
    "particles": {
        "water_droplet": {"description": "Water droplets, 500 micron (typical sprinkler spray)",
                          "fields": {"diameter": 500.0, "density": 1000.0, "color": "BLUE", "spec_id": "WATER VAPOR"}},
    },
}


def builtin_entries(category: str) -> Dict[str, Dict[str, Any]]:
    """Built-in entries of *category* as ``{name: {"description", "fields"}}``."""
    if category not in CATEGORIES:
        raise KeyError(f"unknown library category {category!r}; choose from {', '.join(CATEGORIES)}")
    if category == "materials":
        from pyfds.domain.material_presets import MATERIAL_PRESETS
        return {k: {"description": v.get("description", ""), "fields": {f: x for f, x in v.items() if f != "description"}}
                for k, v in MATERIAL_PRESETS.items()}
    if category == "surfaces":
        from pyfds.domain.material_presets import SURFACE_PRESETS
        return {k: {"description": v.get("description", ""), "fields": {f: x for f, x in v.items() if f != "description"}}
                for k, v in SURFACE_PRESETS.items()}
    if category == "reactions":
        from pyfds.domain.reactions import FUEL_LIBRARY
        return {k.lower(): {"description": f"{v.get('formula', '')} - {k.title()}".strip(" -"), "fields": dict(v)}
                for k, v in FUEL_LIBRARY.items()}
    return {k: {"description": v["description"], "fields": dict(v["fields"])}
            for k, v in _BUILTIN_PROPS.get(category, {}).items()}


# -- which Prop is which kind ------------------------------------------------------------------
def prop_kinds(prop) -> set:
    """Which library categories a Prop belongs to (a sprinkler can be a link model and a spray model)."""
    q = (prop.quantity or "").upper()
    kinds = set()
    if prop.activation_obscuration is not None or "OBSCURATION" in q:
        kinds.add("smoke_detector")
    if "SPRINKLER" in q:
        kinds.add("sprinkler_link")
    if prop.part_id or prop.flow_rate is not None or prop.operating_pressure is not None:
        kinds.add("spray")
    return kinds or {"heat_detector"}


def matches(category: Category, entity) -> bool:
    return not category.filter or category.filter in prop_kinds(entity)


# -- JSON files ----------------------------------------------------------------------------------
def to_document(entries: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    return {"format": LIBRARY_FORMAT, "version": LIBRARY_VERSION, "categories": entries}


def check_document(doc: Any) -> List[str]:
    """Structural problems of a library file ([] when fine)."""
    if not isinstance(doc, dict) or doc.get("format") != LIBRARY_FORMAT:
        return [f"not a {LIBRARY_FORMAT} file"]
    if doc.get("version", 0) > LIBRARY_VERSION:
        return [f"file version {doc.get('version')} is newer than this program understands"]
    cats = doc.get("categories")
    if not isinstance(cats, dict):
        return ["missing 'categories'"]
    return []
