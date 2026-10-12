"""
PyFDS Material Library
======================
Pre-defined material property sets sourced from FDS literature and
the SFPE Handbook. Use these as starting points; always verify
against project-specific material test data.

Usage::

    from pyfds.domain.materials import MATERIAL_LIBRARY

    concrete = MATERIAL_LIBRARY.get("Concrete")
    api.materials.add(Material(**concrete.to_kwargs()))  # from pyfds.domain.model import Material
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MaterialPreset:
    """A named set of thermal and kinetic properties for a &MATL namelist."""
    name: str
    description: str
    density: float                       # kg/m³
    conductivity: float                  # W/(m·K)
    specific_heat: float                 # kJ/(kg·K)
    emissivity: float = 0.9
    # Pyrolysis / reaction
    reference_temperature: Optional[float] = None   # °C
    heat_of_reaction: Optional[float] = None         # kJ/kg
    heat_of_combustion: Optional[float] = None       # kJ/kg
    a: Optional[float] = None                        # Arrhenius pre-exp
    e: Optional[float] = None                        # Activation energy J/mol
    n_s: Optional[float] = None                      # Reaction order
    nu_residue: Optional[float] = None               # Mass fraction remaining
    source: str = "SFPE Handbook / FDS Validation"

    def to_kwargs(self) -> Dict[str, Any]:
        """Return kwargs suitable for ``Material(...)``."""
        d = {
            "name": self.name,
            "density": self.density,
            "conductivity": self.conductivity,
            "specific_heat": self.specific_heat,
            "emissivity": self.emissivity,
        }
        for k in ("reference_temperature", "heat_of_reaction",
                  "heat_of_combustion", "a", "e", "n_s", "nu_residue"):
            v = getattr(self, k, None)
            if v is not None:
                d[k] = v
        return d


class MaterialLibrary:
    """Repository of named material presets with CRUD-style access."""

    def __init__(self) -> None:
        self._presets: Dict[str, MaterialPreset] = {}

    def add(self, preset: MaterialPreset) -> None:
        self._presets[preset.name] = preset

    def get(self, name: str) -> Optional[MaterialPreset]:
        return self._presets.get(name)

    def names(self) -> List[str]:
        return sorted(self._presets.keys())

    def all(self) -> List[MaterialPreset]:
        return list(self._presets.values())

    def find(self, keyword: str) -> List[MaterialPreset]:
        kw = keyword.lower()
        return [p for p in self._presets.values()
                if kw in p.name.lower() or kw in p.description.lower()]

    def categories(self) -> Dict[str, List[str]]:
        cats: Dict[str, List[str]] = {}
        for name, preset in self._presets.items():
            tag = name.split("_")[0]
            cats.setdefault(tag, []).append(name)
        return cats

    def __len__(self) -> int:
        return len(self._presets)

    def __repr__(self) -> str:
        return f"<MaterialLibrary presets={len(self._presets)}>"


# ---------------------------------------------------------------------------
# Built-in material presets
# ---------------------------------------------------------------------------

def _build_library() -> MaterialLibrary:
    lib = MaterialLibrary()

    presets = [
        # ── Structural ─────────────────────────────────────────────────────
        MaterialPreset("Concrete",          "Normal-weight reinforced concrete",
                       density=2300.0, conductivity=1.6, specific_heat=0.88,
                       emissivity=0.9),
        MaterialPreset("Concrete_HPC",      "High-performance concrete",
                       density=2400.0, conductivity=2.0, specific_heat=0.88),
        MaterialPreset("Steel",             "Structural steel (mild)",
                       density=7850.0, conductivity=45.0, specific_heat=0.46,
                       emissivity=0.85),
        MaterialPreset("StainlessSteel",    "Stainless steel 304",
                       density=7900.0, conductivity=16.0, specific_heat=0.50),
        MaterialPreset("Aluminum",          "6061-T6 aluminium alloy",
                       density=2700.0, conductivity=160.0, specific_heat=0.896,
                       emissivity=0.1),
        MaterialPreset("Cast_Iron",         "Grey cast iron",
                       density=7200.0, conductivity=50.0, specific_heat=0.46),
        MaterialPreset("Brick",             "Dense clay brick",
                       density=1800.0, conductivity=0.72, specific_heat=0.84),
        MaterialPreset("Plasterboard",      "Gypsum plasterboard (drywall)",
                       density=700.0, conductivity=0.16, specific_heat=1.09),
        MaterialPreset("Glass",             "Soda-lime float glass",
                       density=2500.0, conductivity=1.0, specific_heat=0.84,
                       emissivity=0.84),

        # ── Insulation ──────────────────────────────────────────────────────
        MaterialPreset("Mineral_Wool",      "Rock/glass mineral wool insulation",
                       density=30.0, conductivity=0.04, specific_heat=0.8),
        MaterialPreset("Polystyrene_EPS",   "Expanded polystyrene (EPS) insulation",
                       density=25.0, conductivity=0.035, specific_heat=1.3,
                       reference_temperature=350.0, heat_of_combustion=40000.0,
                       heat_of_reaction=900.0, nu_residue=0.0),
        MaterialPreset("Polyurethane_Foam", "Flexible PU foam",
                       density=30.0, conductivity=0.036, specific_heat=1.5,
                       reference_temperature=380.0, heat_of_combustion=25000.0,
                       heat_of_reaction=1500.0, nu_residue=0.05),

        # ── Wood / cellulosic ───────────────────────────────────────────────
        MaterialPreset("Wood_Pine",         "Pine (dry, clear)",
                       density=500.0, conductivity=0.12, specific_heat=1.7,
                       emissivity=0.9,
                       reference_temperature=350.0, heat_of_reaction=418.0,
                       heat_of_combustion=17700.0, nu_residue=0.2),
        MaterialPreset("Wood_Oak",          "Oak (dry)",
                       density=700.0, conductivity=0.17, specific_heat=1.7,
                       reference_temperature=360.0, heat_of_reaction=418.0,
                       heat_of_combustion=17700.0, nu_residue=0.25),
        MaterialPreset("MDF",               "Medium density fibreboard",
                       density=750.0, conductivity=0.13, specific_heat=1.7,
                       reference_temperature=330.0, heat_of_reaction=250.0,
                       heat_of_combustion=16000.0, nu_residue=0.1),
        MaterialPreset("Plywood",           "Structural plywood",
                       density=600.0, conductivity=0.12, specific_heat=1.7,
                       reference_temperature=340.0, heat_of_reaction=300.0,
                       heat_of_combustion=17000.0, nu_residue=0.15),

        # ── Plastics / polymers ─────────────────────────────────────────────
        MaterialPreset("PMMA",              "Polymethyl methacrylate (acrylic)",
                       density=1190.0, conductivity=0.19, specific_heat=1.42,
                       reference_temperature=380.0, heat_of_reaction=870.0,
                       heat_of_combustion=25200.0, nu_residue=0.0,
                       a=3.2e19, e=2.0e5, n_s=1.0),
        MaterialPreset("PVC",               "Rigid PVC",
                       density=1380.0, conductivity=0.15, specific_heat=0.9,
                       reference_temperature=250.0, heat_of_reaction=200.0,
                       heat_of_combustion=16400.0, nu_residue=0.15),
        MaterialPreset("Nylon_PA6",         "Polyamide 6 (Nylon 6)",
                       density=1130.0, conductivity=0.25, specific_heat=1.67,
                       reference_temperature=400.0, heat_of_reaction=700.0,
                       heat_of_combustion=30000.0, nu_residue=0.0),
        MaterialPreset("Polypropylene",     "Isotactic polypropylene (PP)",
                       density=900.0, conductivity=0.22, specific_heat=1.9,
                       reference_temperature=400.0, heat_of_reaction=900.0,
                       heat_of_combustion=43400.0, nu_residue=0.0),
        MaterialPreset("Polyethylene",      "High-density polyethylene (HDPE)",
                       density=960.0, conductivity=0.44, specific_heat=1.9,
                       reference_temperature=420.0, heat_of_reaction=900.0,
                       heat_of_combustion=43300.0, nu_residue=0.0),

        # ── Composite / textiles ────────────────────────────────────────────
        MaterialPreset("Carpet_Nylon",      "Nylon pile carpet",
                       density=200.0, conductivity=0.06, specific_heat=1.3,
                       reference_temperature=400.0, heat_of_combustion=28000.0),
        MaterialPreset("Cotton_Fabric",     "Woven cotton fabric",
                       density=300.0, conductivity=0.06, specific_heat=1.4,
                       reference_temperature=350.0, heat_of_combustion=16500.0,
                       nu_residue=0.05),

        # ── Liquids (pool fire surfaces) ────────────────────────────────────
        MaterialPreset("Heptane",           "n-Heptane pool fuel",
                       density=684.0, conductivity=0.14, specific_heat=2.24,
                       reference_temperature=98.4, heat_of_combustion=44600.0,
                       heat_of_reaction=318.0),
        MaterialPreset("Ethanol",           "Ethanol pool fuel",
                       density=789.0, conductivity=0.17, specific_heat=2.44,
                       reference_temperature=78.3, heat_of_combustion=26800.0,
                       heat_of_reaction=838.0),

        # ── Soil / ground ───────────────────────────────────────────────────
        MaterialPreset("Soil_Dry",          "Dry sandy soil",
                       density=1600.0, conductivity=0.3, specific_heat=0.84),
        MaterialPreset("Soil_Moist",        "Moist loam soil",
                       density=1800.0, conductivity=1.0, specific_heat=2.0),

        # ── Additional structural ───────────────────────────────────────────
        MaterialPreset("Concrete_Aerated",  "Autoclaved aerated concrete (AAC)",
                       density=500.0, conductivity=0.16, specific_heat=1.0,
                       emissivity=0.9,
                       source="EN 1991-1-2 / SFPE"),
        MaterialPreset("Limestone",         "Dense limestone",
                       density=2600.0, conductivity=1.3, specific_heat=0.84),
        MaterialPreset("Granite",           "Granite rock",
                       density=2700.0, conductivity=2.9, specific_heat=0.79),
        MaterialPreset("Copper",            "Electrolytic copper",
                       density=8940.0, conductivity=385.0, specific_heat=0.385,
                       emissivity=0.05),
        MaterialPreset("HighStrengthSteel", "High-strength structural steel (S355)",
                       density=7850.0, conductivity=50.0, specific_heat=0.46,
                       emissivity=0.85,
                       source="EN 1993-1-2"),

        # ── Additional insulation ───────────────────────────────────────────
        MaterialPreset("Cellulose_Insul",   "Blown cellulose insulation",
                       density=55.0, conductivity=0.04, specific_heat=1.34),
        MaterialPreset("Vermiculite",       "Expanded vermiculite board",
                       density=200.0, conductivity=0.07, specific_heat=0.84),
        MaterialPreset("Perlite_Board",     "Perlite fire-protection board",
                       density=300.0, conductivity=0.06, specific_heat=1.0),
        MaterialPreset("Intumescent",       "Intumescent coating (pre-reaction)",
                       density=1200.0, conductivity=0.2, specific_heat=1.0,
                       reference_temperature=150.0, heat_of_reaction=100.0,
                       source="Typical intumescent product data"),

        # ── Additional wood / cellulosic ───────────────────────────────────
        MaterialPreset("Wood_Spruce",       "Norway spruce (structural)",
                       density=430.0, conductivity=0.11, specific_heat=1.7,
                       reference_temperature=350.0, heat_of_reaction=418.0,
                       heat_of_combustion=17700.0, nu_residue=0.2),
        MaterialPreset("OSB",               "Oriented strand board",
                       density=620.0, conductivity=0.13, specific_heat=1.7,
                       reference_temperature=330.0, heat_of_reaction=250.0,
                       heat_of_combustion=16500.0, nu_residue=0.1),
        MaterialPreset("Particle_Board",    "Particle board / chipboard",
                       density=680.0, conductivity=0.14, specific_heat=1.7,
                       reference_temperature=320.0, heat_of_reaction=200.0,
                       heat_of_combustion=15500.0, nu_residue=0.08),
        MaterialPreset("Cork",              "Natural cork",
                       density=120.0, conductivity=0.04, specific_heat=1.9,
                       reference_temperature=300.0, heat_of_combustion=26800.0,
                       nu_residue=0.1),

        # ── Additional plastics ─────────────────────────────────────────────
        MaterialPreset("ABS",               "Acrylonitrile butadiene styrene (ABS)",
                       density=1050.0, conductivity=0.17, specific_heat=1.4,
                       reference_temperature=380.0, heat_of_reaction=800.0,
                       heat_of_combustion=35000.0, nu_residue=0.0),
        MaterialPreset("Polycarbonate",     "Polycarbonate (PC)",
                       density=1200.0, conductivity=0.20, specific_heat=1.25,
                       reference_temperature=420.0, heat_of_reaction=750.0,
                       heat_of_combustion=29000.0, nu_residue=0.0),
        MaterialPreset("Polystyrene_XPS",   "Extruded polystyrene insulation (XPS)",
                       density=35.0, conductivity=0.035, specific_heat=1.3,
                       reference_temperature=350.0, heat_of_combustion=40000.0,
                       heat_of_reaction=900.0, nu_residue=0.0),
        MaterialPreset("PTFE",              "Polytetrafluoroethylene (Teflon) — non-combustible",
                       density=2200.0, conductivity=0.25, specific_heat=1.0,
                       emissivity=0.9),
        MaterialPreset("PET",               "Polyethylene terephthalate (PET)",
                       density=1380.0, conductivity=0.24, specific_heat=1.35,
                       reference_temperature=430.0, heat_of_reaction=600.0,
                       heat_of_combustion=22000.0, nu_residue=0.0),

        # ── Textiles / upholstery ───────────────────────────────────────────
        MaterialPreset("Wool_Fabric",       "Woven wool fabric",
                       density=280.0, conductivity=0.05, specific_heat=1.36,
                       reference_temperature=600.0, heat_of_combustion=21000.0,
                       nu_residue=0.3,
                       source="SFPE / ISO 5657"),
        MaterialPreset("PU_Foam_Rigid",     "Rigid polyurethane foam",
                       density=40.0, conductivity=0.025, specific_heat=1.5,
                       reference_temperature=360.0, heat_of_combustion=27000.0,
                       heat_of_reaction=1200.0, nu_residue=0.1),

        # ── Additional pool fire fuels ──────────────────────────────────────
        MaterialPreset("Methanol",          "Methanol pool fuel",
                       density=791.0, conductivity=0.20, specific_heat=2.5,
                       reference_temperature=64.7, heat_of_combustion=19900.0,
                       heat_of_reaction=1100.0),
        MaterialPreset("Gasoline",          "Gasoline (petrol) pool fuel — representative",
                       density=730.0, conductivity=0.14, specific_heat=2.0,
                       reference_temperature=40.0, heat_of_combustion=43700.0,
                       heat_of_reaction=330.0),
        MaterialPreset("Diesel",            "Diesel fuel pool fire — representative",
                       density=840.0, conductivity=0.14, specific_heat=2.0,
                       reference_temperature=200.0, heat_of_combustion=42500.0,
                       heat_of_reaction=240.0),
        MaterialPreset("Kerosene",          "Kerosene (Jet A-1) pool fire",
                       density=800.0, conductivity=0.14, specific_heat=2.1,
                       reference_temperature=150.0, heat_of_combustion=43200.0,
                       heat_of_reaction=230.0),
        MaterialPreset("Acetone",           "Acetone pool fuel",
                       density=791.0, conductivity=0.16, specific_heat=2.17,
                       reference_temperature=56.0, heat_of_combustion=29100.0,
                       heat_of_reaction=518.0),
    ]

    for preset in presets:
        lib.add(preset)

    return lib


MATERIAL_LIBRARY: MaterialLibrary = _build_library()
