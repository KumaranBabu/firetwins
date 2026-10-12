"""Surfaces, materials, ramps, reactions and particles.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .base import _CollectionManager

logger = logging.getLogger(__name__)


class SurfaceManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Surface
        super().__init__(api, Surface)

    def add_burner(self, hrrpua: float, tau_q: float = 1.0, **kwargs) -> Any:
        from pyfds.domain.model import Surface
        # NB: Surface's HRRPUA field is heat_release_rate, not hrrpua —
        # same extra="allow" trap as elsewhere in this file.
        surf = Surface(heat_release_rate=hrrpua, tau_q=tau_q, **kwargs)
        self.add(surf)
        return surf

    def kind(self, surface_or_name) -> str:
        """Which of the eight surface types this is (``basic``, ``burner``, ``supply`` ... ``general``)."""
        from pyfds.domain.surface_types import kind_of
        s = self.get(surface_or_name) if isinstance(surface_or_name, str) else surface_or_name
        if s is None:
            raise KeyError(f"surface {surface_or_name!r} not found")
        return kind_of(s)

    def add_typed(self, kind: str, name: str = None, **fields) -> Any:
        """Add a surface of one of the eight types, checking the fields that type needs.

        burner: ``heat_release_rate`` (kW/m2); supply/exhaust: ``flow`` (m/s magnitude) or ``volume_flow``;
        heater_cooler: ``tmp_front`` (deg C); layered: ``layers``; air_leak: ``leak_path=[zone1, zone2]``."""
        from pyfds.domain.model import Surface
        from pyfds.domain.surface_types import build
        values = build(kind, **fields)
        if kind == "air_leak":
            zones = {z.name for z in self._project.zones}
            missing = [z for z in values["leak_path"] if z not in zones]
            if missing:
                raise KeyError(f"pressure zone(s) not found: {missing}")
        surf = Surface(**({"name": name} if name else {}), **values)
        self.add(surf)
        return surf

    def add_from_library(self, preset_name: str) -> Any:
        """Add a multi-layer SURF (with its Layer list) from the built-in preset library."""
        from pyfds.domain.material_presets import make_surface
        surf = make_surface(preset_name)
        self.add(surf)
        return surf


class ReactionManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Reaction
        super().__init__(api, Reaction)

    def add_simple_reaction(self, fuel: str, heat_of_combustion: float, **kwargs) -> Any:
        from pyfds.domain.model import Reaction
        r = Reaction(fuel=fuel, heat_of_combustion=heat_of_combustion, **kwargs)
        self.add(r)
        return r

    def add_complex_reaction(self, reactants: dict, products: dict, name: str = None,
                             exponents: dict = None, **kwargs) -> Any:
        """Complex stoichiometry: ``reactants={"PROPANE": 1, "OXYGEN": 5}``, ``products={"CARBON DIOXIDE": 3,
        "WATER VAPOR": 4}`` (positive numbers; signs are applied here). *exponents* are optional rate
        exponents per species. Species must be defined (or built into FDS) and the mass must balance."""
        from pyfds.domain.model import Reaction
        from pyfds.domain import reaction_checks
        if not reactants or not products:
            raise ValueError("a reaction needs at least one reactant and one product")
        if any(v <= 0 for v in (*reactants.values(), *products.values())):
            raise ValueError("give stoichiometric coefficients as positive numbers")
        if set(reactants) & set(products):
            raise ValueError("a species cannot be both reactant and product")
        r = Reaction(spec_id_nu=[*reactants, *products],
                     nu=[-float(v) for v in reactants.values()] + [float(v) for v in products.values()],
                     spec_id_n_s=list(exponents) if exponents else None,
                     n_s=[float(v) for v in exponents.values()] if exponents else None,
                     **({"name": name} if name else {}), **kwargs)
        bad = reaction_checks.problems(self._project, r)
        if bad:
            raise ValueError("; ".join(bad))
        self.add(r)
        return r

    def reaction_type(self, reaction_or_name) -> str:
        """``simple`` or ``complex`` (RXN-01)."""
        r = self.get(reaction_or_name) if isinstance(reaction_or_name, str) else reaction_or_name
        if r is None:
            raise KeyError(f"reaction {reaction_or_name!r} not found")
        return r.reaction_type


class MaterialManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Material
        super().__init__(api, Material)

    def add_from_library(self, preset_name: str) -> Any:
        # NB: pyfds.domain.materials.MaterialLibrary is a legacy (Phase-1,
        # v0.2-compat) empty repository class — instantiating it fresh here
        # gave a KeyError for every preset name, always. The real, populated
        # registry from Phase 2c is domain/material_presets.py.
        from pyfds.domain.material_presets import make_material
        mat = make_material(preset_name)
        self.add(mat)
        return mat

    def add_liquid_fuel(self, name: str, fuel_species: str, boiling_temperature: float,
                        heat_of_vaporization: float, density: float, specific_heat: float,
                        conductivity: float = 0.2, absorption_coefficient: float = 1000.0,
                        emissivity: float = 1.0, **kwargs) -> Any:
        """Liquid fuel material (pool fire): boiling point (deg C), heat of vaporisation (kJ/kg), density
        (kg/m3), specific heat (kJ/kg/K), the species it evaporates to, and an absorption coefficient (1/m)."""
        from pyfds.domain.model import Material
        for label, v in (("boiling_temperature", boiling_temperature), ("heat_of_vaporization", heat_of_vaporization),
                         ("density", density), ("specific_heat", specific_heat)):
            if v is None or v <= 0:
                raise ValueError(f"{label} must be positive")
        mat = Material(name=name, density=density, specific_heat=specific_heat, conductivity=conductivity,
                       emissivity=emissivity, boiling_temperature=boiling_temperature,
                       heat_of_reaction=heat_of_vaporization, absorption_coefficient=absorption_coefficient,
                       spec_ids=[fuel_species], nu_gases=[1.0], **kwargs)
        self.add(mat)
        return mat

    def is_liquid_fuel(self, material_or_name) -> bool:
        m = self.get(material_or_name) if isinstance(material_or_name, str) else material_or_name
        if m is None:
            raise KeyError(f"material {material_or_name!r} not found")
        return m.boiling_temperature is not None


class RampManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Ramp
        super().__init__(api, Ramp)

    def add_ramp(self, ramp_id: str, times: List[float], values: List[float]) -> Any:
        from pyfds.domain.model import Ramp
        # NB: Ramp.id is a read-only alias for .name — same trap as Device.
        r = Ramp(name=ramp_id, times=times, values=values)
        self.add(r)
        return r


class ParticleManager(_CollectionManager):
    """Manage Lagrangian particle class definitions (&PART) — reference
    one from Init.part_id (a particle cloud) or a Device's prop_id."""
    def __init__(self, api):
        from pyfds.domain.model import Particle
        super().__init__(api, Particle)

    def add_particle_class(self, diameter: float = 500.0, **kwargs) -> Any:
        from pyfds.domain.model import Particle
        particle = Particle(diameter=diameter, **kwargs)
        self.add(particle)
        return particle
