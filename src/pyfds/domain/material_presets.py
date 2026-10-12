"""
FDS Material Presets Library
==============================
Calibrated &MATL (material) and multi-layer &SURF (surface) configurations for
common building materials.  All property values are from FDS 6 Validation Guide
(McGrattan et al.) and SFPE Handbook references.

Usage::

    from pyfds.domain.material_presets import (
        MATERIAL_PRESETS, list_material_presets,
        get_material_preset, make_material, make_surface,
    )

    mat = make_material("concrete")           # → Material entity
    surf = make_surface("gypsum_wall_25mm")   # → Surface with Layer list
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pyfds.domain.model import Layer, Material, Surface


# ---------------------------------------------------------------------------
# Preset database — property values
# ---------------------------------------------------------------------------

MATERIAL_PRESETS: Dict[str, Dict[str, Any]] = {
    # ── Concrete ─────────────────────────────────────────────────────────────
    "concrete": {
        "description": "Normal-weight concrete (ρ~2300 kg/m³, SFPE Handbook 3rd ed.)",
        "density": 2280.0,
        "conductivity": 1.6,
        "specific_heat": 0.88,
        "emissivity": 0.94,
    },
    "lightweight_concrete": {
        "description": "Lightweight aggregate concrete (ρ~1600 kg/m³)",
        "density": 1600.0,
        "conductivity": 0.8,
        "specific_heat": 0.84,
        "emissivity": 0.94,
    },

    # ── Steel ─────────────────────────────────────────────────────────────────
    "steel": {
        "description": "Structural carbon steel (EN 1993-1-2, ambient properties)",
        "density": 7850.0,
        "conductivity": 45.8,
        "specific_heat": 0.46,
        "emissivity": 0.7,
        "conductivity_ramp": None,
        "specific_heat_ramp": None,
    },
    "stainless_steel": {
        "description": "Stainless steel 304/316 (NIST measurements)",
        "density": 7900.0,
        "conductivity": 16.0,
        "specific_heat": 0.50,
        "emissivity": 0.3,
    },

    # ── Gypsum / Plasterboard ─────────────────────────────────────────────────
    "gypsum_board": {
        "description": "Gypsum wallboard / plasterboard (Steckler et al.)",
        "density": 930.0,
        "conductivity": 0.17,
        "specific_heat": 1.09,
        "emissivity": 0.9,
    },
    "gypsum_plaster": {
        "description": "Gypsum plaster (wet-applied, higher density)",
        "density": 1100.0,
        "conductivity": 0.25,
        "specific_heat": 1.09,
        "emissivity": 0.9,
    },

    # ── Wood ─────────────────────────────────────────────────────────────────
    "pine": {
        "description": "Scots pine / generic softwood (Östman, fire properties)",
        "density": 510.0,
        "conductivity": 0.14,
        "specific_heat": 1.7,
        "emissivity": 0.9,
        "reference_temperature": 360.0,
        "heat_of_reaction": 150.0,
        "nu_residue": 0.15,
    },
    "oak": {
        "description": "Oak / generic hardwood (higher density softwood analogue)",
        "density": 700.0,
        "conductivity": 0.19,
        "specific_heat": 1.7,
        "emissivity": 0.9,
        "reference_temperature": 360.0,
        "heat_of_reaction": 150.0,
        "nu_residue": 0.15,
    },
    "mdf": {
        "description": "Medium-density fibreboard (MDF board product)",
        "density": 700.0,
        "conductivity": 0.16,
        "specific_heat": 1.7,
        "emissivity": 0.9,
        "reference_temperature": 350.0,
        "heat_of_reaction": 180.0,
        "nu_residue": 0.1,
    },
    "plywood": {
        "description": "Birch/softwood plywood (7-ply, face grain parallel)",
        "density": 600.0,
        "conductivity": 0.16,
        "specific_heat": 1.65,
        "emissivity": 0.9,
        "reference_temperature": 360.0,
        "heat_of_reaction": 150.0,
        "nu_residue": 0.15,
    },
    "char": {
        "description": "Wood char residue (generic)",
        "density": 120.0,
        "conductivity": 0.1,
        "specific_heat": 1.0,
        "emissivity": 0.9,
    },

    # ── Polymers ─────────────────────────────────────────────────────────────
    "pmma": {
        "description": "Polymethylmethacrylate / Plexiglas (Dakka & Quintiere)",
        "density": 1190.0,
        "conductivity": 0.19,
        "specific_heat": 1.42,
        "emissivity": 0.9,
        "reference_temperature": 380.0,
        "heat_of_reaction": 870.0,
        "boiling_temperature": 380.0,
        "absorption_coefficient": 2700.0,
        "nu_residue": 0.0,
    },
    "polystyrene": {
        "description": "Expanded polystyrene (EPS foam insulation)",
        "density": 22.0,
        "conductivity": 0.034,
        "specific_heat": 1.3,
        "emissivity": 0.9,
        "reference_temperature": 380.0,
        "heat_of_reaction": 900.0,
        "nu_residue": 0.0,
    },
    "polyurethane_foam": {
        "description": "Flexible polyurethane foam (furniture-grade, ρ~30 kg/m³)",
        "density": 30.0,
        "conductivity": 0.038,
        "specific_heat": 1.4,
        "emissivity": 0.9,
        "reference_temperature": 350.0,
        "heat_of_reaction": 1500.0,
        "nu_residue": 0.02,
    },
    "pvc": {
        "description": "Rigid PVC (chlorinated polymer — use with HCL species)",
        "density": 1380.0,
        "conductivity": 0.17,
        "specific_heat": 0.9,
        "emissivity": 0.9,
        "reference_temperature": 400.0,
        "heat_of_reaction": 500.0,
        "nu_residue": 0.05,
    },
    "polyethylene": {
        "description": "HDPE / polyethylene (cable insulation, pipe material)",
        "density": 950.0,
        "conductivity": 0.5,
        "specific_heat": 2.0,
        "emissivity": 0.9,
        "reference_temperature": 480.0,
        "heat_of_reaction": 900.0,
        "boiling_temperature": 480.0,
        "nu_residue": 0.0,
    },

    # ── Glass / Insulation ────────────────────────────────────────────────────
    "glass": {
        "description": "Soda-lime float glass (window glass)",
        "density": 2500.0,
        "conductivity": 1.0,
        "specific_heat": 0.84,
        "emissivity": 0.9,
    },
    "mineral_wool": {
        "description": "Mineral/rock wool insulation (high-temperature grade)",
        "density": 100.0,
        "conductivity": 0.04,
        "specific_heat": 0.84,
        "emissivity": 0.9,
    },
    "glass_wool": {
        "description": "Glass fibre insulation blanket",
        "density": 32.0,
        "conductivity": 0.034,
        "specific_heat": 0.84,
        "emissivity": 0.9,
    },

    # ── Textiles / Floor coverings ────────────────────────────────────────────
    "carpet_nylon": {
        "description": "Nylon carpet (loop pile, glued down)",
        "density": 700.0,
        "conductivity": 0.06,
        "specific_heat": 1.3,
        "emissivity": 0.9,
        "reference_temperature": 400.0,
        "heat_of_reaction": 800.0,
        "nu_residue": 0.05,
    },
    "carpet_wool": {
        "description": "Wool carpet (woven, typical hotel-grade)",
        "density": 900.0,
        "conductivity": 0.07,
        "specific_heat": 1.7,
        "emissivity": 0.9,
        "reference_temperature": 450.0,
        "heat_of_reaction": 600.0,
        "nu_residue": 0.10,
    },

    # ── Brick / Masonry ───────────────────────────────────────────────────────
    "brick": {
        "description": "Common clay brick (medium density)",
        "density": 1800.0,
        "conductivity": 0.72,
        "specific_heat": 0.84,
        "emissivity": 0.93,
    },
    "aac_block": {
        "description": "Autoclaved aerated concrete (AAC/Ytong) block",
        "density": 600.0,
        "conductivity": 0.18,
        "specific_heat": 1.0,
        "emissivity": 0.9,
    },
}


# ---------------------------------------------------------------------------
# Surface presets (multi-layer assemblies)
# ---------------------------------------------------------------------------

SURFACE_PRESETS: Dict[str, Dict[str, Any]] = {
    "gypsum_wall_12mm": {
        "description": "Single layer of 12.5 mm gypsum board on steel studs",
        "layers": [{"material_id": "GYP_BOARD", "thickness": 0.0125}],
        "color": "IVORY",
        "backing": "VOID",
    },
    "gypsum_wall_25mm": {
        "description": "Double 12.5 mm gypsum board (fire wall configuration)",
        "layers": [
            {"material_id": "GYP_BOARD", "thickness": 0.0125},
            {"material_id": "GYP_BOARD", "thickness": 0.0125},
        ],
        "color": "IVORY",
        "backing": "VOID",
    },
    "concrete_slab_150mm": {
        "description": "150 mm reinforced concrete slab / floor",
        "layers": [{"material_id": "CONCRETE", "thickness": 0.15}],
        "color": "GRAY",
        "backing": "VOID",
    },
    "timber_wall_90mm": {
        "description": "90 mm CLT / solid timber wall panel",
        "layers": [
            {"material_id": "PINE", "thickness": 0.09},
        ],
        "color": "SANDYBROWN",
        "backing": "VOID",
    },
    "insulated_wall": {
        "description": "100 mm mineral wool insulation + 12.5 mm gypsum lining",
        "layers": [
            {"material_id": "GYP_BOARD",    "thickness": 0.0125},
            {"material_id": "MINERAL_WOOL", "thickness": 0.10},
        ],
        "color": "IVORY",
        "backing": "VOID",
    },
    "steel_deck_2mm": {
        "description": "2 mm structural steel deck (unprotected)",
        "layers": [{"material_id": "STEEL", "thickness": 0.002}],
        "color": "SILVER",
        "backing": "VOID",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_material_presets() -> List[str]:
    """Return sorted list of material preset names."""
    return sorted(MATERIAL_PRESETS)


def list_surface_presets() -> List[str]:
    """Return sorted list of surface preset names."""
    return sorted(SURFACE_PRESETS)


def get_material_preset(name: str) -> Dict[str, Any]:
    """Return the raw property dict for *name* (case-insensitive).

    Raises ``KeyError`` with suggestion list if not found.
    """
    key = name.lower().replace(" ", "_").replace("-", "_")
    if key in MATERIAL_PRESETS:
        return dict(MATERIAL_PRESETS[key])
    available = ", ".join(sorted(MATERIAL_PRESETS)[:8])
    raise KeyError(
        f"Unknown material preset {name!r}. "
        f"First 8 available: {available} ..."
    )


def make_material(name: str, material_name: Optional[str] = None) -> Material:
    """Build a :class:`Material` entity from the library.

    Parameters
    ----------
    name : str
        Preset name (e.g. ``'pine'``, ``'concrete'``).
    material_name : str, optional
        Override for the FDS ``ID=`` string.  Defaults to an upper-case
        version of the preset name.
    """
    props = get_material_preset(name)
    props.pop("description", None)
    fds_id = material_name or name.upper().replace(" ", "_").replace("-", "_")
    return Material(name=fds_id, **props)


def get_surface_preset(name: str) -> Dict[str, Any]:
    """Return the raw surface preset dict for *name* (case-insensitive)."""
    key = name.lower().replace(" ", "_").replace("-", "_")
    if key in SURFACE_PRESETS:
        return dict(SURFACE_PRESETS[key])
    available = ", ".join(sorted(SURFACE_PRESETS)[:6])
    raise KeyError(
        f"Unknown surface preset {name!r}. "
        f"First 6 available: {available} ..."
    )


def make_surface(name: str, surface_name: Optional[str] = None) -> Surface:
    """Build a :class:`Surface` entity from the preset library.

    Material references in the layers use the canonical all-caps preset names
    (e.g. ``PINE``, ``CONCRETE``) — add the corresponding :func:`make_material`
    entities to the project before running FDS.

    Parameters
    ----------
    name : str
        Preset name (e.g. ``'gypsum_wall_25mm'``, ``'concrete_slab_150mm'``).
    surface_name : str, optional
        Override for the FDS ``ID=`` string.
    """
    props = get_surface_preset(name)
    props.pop("description", None)
    fds_id = surface_name or name.upper().replace(" ", "_").replace("-", "_")
    raw_layers = props.pop("layers", [])
    layers = [Layer(material_id=l["material_id"], thickness=l["thickness"]) for l in raw_layers]
    return Surface(name=fds_id, layers=layers, **props)
