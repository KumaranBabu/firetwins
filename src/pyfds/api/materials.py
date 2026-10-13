"""Surfaces, materials, ramps, reactions and particles.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .base import _CollectionManager
from .material_tools import MaterialTools

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

    def _reaction(self, reaction_or_name):
        r = self.get(reaction_or_name) if isinstance(reaction_or_name, str) else reaction_or_name
        if r is None:
            raise KeyError(f"reaction {reaction_or_name!r} not found")
        return r

    def stoichiometry(self, reaction_or_name) -> dict:
        """The reaction as a table (RXN-03): ``{"type", "reactants": [{"species", "coefficient"}],
        "products": [...], "exponents": {species: n}}``. Simple chemistry has no table: it returns the
        fuel, its formula and ``type: "simple"``."""
        r = self._reaction(reaction_or_name)
        if not r.spec_id_nu:
            return {"type": "simple", "fuel": r.fuel, "formula": r.formula, "reactants": [], "products": [],
                    "exponents": {}}
        rows = list(zip(r.spec_id_nu, r.nu or []))
        return {"type": "complex",
                "reactants": [{"species": s, "coefficient": -v} for s, v in rows if v < 0],
                "products": [{"species": s, "coefficient": v} for s, v in rows if v > 0],
                "exponents": dict(zip(r.spec_id_n_s or [], r.n_s or []))}

    def set_stoichiometry(self, reaction_or_name, reactants: dict, products: dict, exponents: dict = None):
        """Replace the species table of a reaction (one undo step); checks species and mass balance first."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        from pyfds.domain import reaction_checks
        from pyfds.domain.model import Reaction
        r = self._reaction(reaction_or_name)
        if not reactants or not products:
            raise ValueError("a reaction needs at least one reactant and one product")
        if any(v <= 0 for v in (*reactants.values(), *products.values())):
            raise ValueError("give stoichiometric coefficients as positive numbers")
        if set(reactants) & set(products):
            raise ValueError("a species cannot be both reactant and product")
        new = dict(spec_id_nu=[*reactants, *products],
                   nu=[-float(v) for v in reactants.values()] + [float(v) for v in products.values()],
                   spec_id_n_s=list(exponents) if exponents else None,
                   n_s=[float(v) for v in exponents.values()] if exponents else None)
        trial = Reaction(**{**r.model_dump(), **new})
        bad = reaction_checks.problems(self._project, trial)
        if bad:
            raise ValueError("; ".join(bad))
        self._api.history.execute(GroupCommand([ModifyPropertyCommand(r, k, v) for k, v in new.items()],
                                               label=f"edit stoichiometry of {r.name}"))
        return r

    # -- custom smoke (RXN-05) ---------------------------------------------------------
    def smoke(self) -> dict:
        """Smoke settings now in the project: soot yield of each reaction, the SOOT species' mass extinction
        coefficient (FDS default 8700 m2/kg) and the visibility settings."""
        soot = next((s for s in self._project.species if s.name == "SOOT"), None)
        misc = self._project.misc
        return {"mass_extinction_coefficient": soot.mass_extinction_coefficient if soot else None,
                "soot_yield": {r.name: r.soot_yield for r in self.all()},
                "visibility_factor": misc.visibility_factor, "maximum_visibility": misc.maximum_visibility}

    def set_smoke(self, mass_extinction_coefficient: float = None, soot_yield: float = None, reaction=None,
                  visibility_factor: float = None, maximum_visibility: float = None) -> dict:
        """Customise smoke (one undo step): the mass extinction coefficient Km (m2/kg, written on the
        SOOT species as a lumped component), a reaction's soot yield (kg/kg), and the visibility
        factor C (3 = reflecting sign, 8 = light-emitting) and maximum visibility reported (m)."""
        from pyfds.automation.commands import AddEntityCommand, ModifyPropertyCommand
        from pyfds.domain.model import Species
        for label, v in (("mass_extinction_coefficient", mass_extinction_coefficient),
                         ("visibility_factor", visibility_factor), ("maximum_visibility", maximum_visibility)):
            if v is not None and v <= 0:
                raise ValueError(f"{label} must be positive")
        if soot_yield is not None and not 0.0 <= soot_yield < 1.0:
            raise ValueError("soot_yield must be between 0 and 1")
        r = None
        if soot_yield is not None:
            r = self._reaction(reaction) if reaction is not None else (self.all() or [None])[0]
            if r is None:
                raise ValueError("there is no reaction to set the soot yield on; add one first")
        with self._api.history.transaction("set smoke properties"):
            if mass_extinction_coefficient is not None:
                soot = next((s for s in self._project.species if s.name == "SOOT"), None)
                if soot is None:
                    self._api.history.execute(AddEntityCommand(self._project, Species(
                        name="SOOT", lumped_component_only=True,
                        mass_extinction_coefficient=mass_extinction_coefficient)))
                else:
                    self._api.history.execute(ModifyPropertyCommand(
                        soot, "mass_extinction_coefficient", mass_extinction_coefficient))
            if r is not None:
                self._api.history.execute(ModifyPropertyCommand(r, "soot_yield", soot_yield))
            for key, v in (("visibility_factor", visibility_factor), ("maximum_visibility", maximum_visibility)):
                if v is not None:
                    self._api.history.execute(ModifyPropertyCommand(self._project.misc, key, v))
        return self.smoke()

    def reaction_type(self, reaction_or_name) -> str:
        """``simple`` or ``complex`` (RXN-01)."""
        r = self.get(reaction_or_name) if isinstance(reaction_or_name, str) else reaction_or_name
        if r is None:
            raise KeyError(f"reaction {reaction_or_name!r} not found")
        return r.reaction_type


class MaterialManager(MaterialTools, _CollectionManager):
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

    def kind(self, particle_or_name) -> str:
        """``tracer``, ``solid`` or ``droplet`` (PRT-01)."""
        p = self.get(particle_or_name) if isinstance(particle_or_name, str) else particle_or_name
        if p is None:
            raise KeyError(f"particle class {particle_or_name!r} not found")
        return p.kind

    def add_tracer(self, name: str = None, color: str = "BLACK", **kwargs) -> Any:
        """Massless tracer particles (for visualising flow); they carry no mass, so no species or surface."""
        if kwargs.get("spec_id") or kwargs.get("surf_id"):
            raise ValueError("a massless tracer cannot have a species (it cannot evaporate) or a surface")
        return self.add_particle_class(**{"name": name or f"TRACER_{self.count() + 1}", "color": color,
                                          "massless": True, **kwargs})

    def add_droplet(self, name: str = None, diameter: float = 500.0, spec_id: str = "WATER VAPOR",
                    **kwargs) -> Any:
        """Liquid droplets that evaporate into species *spec_id* (diameter in micron). Set
        ``gamma``/``sigma`` for a Rosin-Rammler/log-normal size spread, or ``monodisperse=True``."""
        if diameter <= 0:
            raise ValueError("diameter must be positive")
        if kwargs.get("massless"):
            raise ValueError("evaporating droplets cannot be massless")
        with self._api.history.transaction("add droplet particles"):
            if self._api.species.get(spec_id) is None:     # FDS needs a SPEC line for the evaporating species
                self._api.species.add_species(spec_id)
            return self.add_particle_class(diameter=diameter, **{
                "name": name or f"DROPLET_{self.count() + 1}", "spec_id": spec_id, "color": "BLUE", **kwargs})

    def add_solid_particle(self, surf_id: str, name: str = None, diameter: float = 1000.0, **kwargs) -> Any:
        """Solid particles that carry the properties of surface *surf_id* (subgrid objects: clutter, embers,
        vegetation). Diameter in micron."""
        if not surf_id:
            raise ValueError("solid particles need a surface (surf_id)")
        if kwargs.get("massless") or kwargs.get("spec_id"):
            raise ValueError("solid particles cannot be massless or evaporate")
        return self.add_particle_class(diameter=diameter, **{
            "name": name or f"SOLID_{self.count() + 1}", "surf_id": surf_id, "color": "BROWN", **kwargs})
