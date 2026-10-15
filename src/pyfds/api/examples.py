"""Curated example models: ``api.examples`` (HLP-02).

Small, runnable models in the spirit of the chapters of the PyroSim Example Guide, each built with
the same API calls a user script would make (so they double as documentation). ``load`` replaces the
current project with the example and returns a short description of what to look at.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List


def _burner_fire(api) -> None:
    api.meshes.add_mesh([30, 30, 30], [0, 3, 0, 3, 0, 3])
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)
    burner = api.surfaces.add_burner(hrrpua=1000.0, tau_q=1.0, name="BURNER")
    api.vents.add_vent([1.0, 2.0, 1.0, 2.0, 0.0, 0.0], burner.name)
    api.vents.add_vent([0.0, 3.0, 0.0, 0.0, 0.0, 3.0], "OPEN")
    api.vents.add_vent([0.0, 3.0, 3.0, 3.0, 0.0, 3.0], "OPEN")
    api.vents.add_vent([0.0, 0.0, 0.0, 3.0, 0.0, 3.0], "OPEN")
    api.vents.add_vent([3.0, 3.0, 0.0, 3.0, 0.0, 3.0], "OPEN")
    api.vents.add_vent([0.0, 3.0, 0.0, 3.0, 3.0, 3.0], "OPEN")
    api.devices.add_thermocouple([1.5, 1.5, 2.5], "TC_ABOVE_BURNER")
    api.slices.add_slice("TEMPERATURE", "Y", 1.5)
    api.project.params.t_end = 20.0


def _air_movement(api) -> None:
    api.meshes.add_mesh([40, 20, 20], [0, 4, 0, 2, 0, 2])
    supply = api.surfaces.add_typed("supply", "SUPPLY", flow=1.0)
    api.vents.add_vent([0.0, 0.0, 0.8, 1.2, 0.8, 1.2], supply.name)
    api.vents.add_vent([4.0, 4.0, 0.8, 1.2, 0.8, 1.2], "OPEN")
    api.obstructions.add_obstruction([1.5, 2.0, 0.5, 1.5, 0.0, 1.5], name="BOX")
    api.slices.add_slice("VELOCITY", "Y", 1.0)
    api.project.params.t_end = 10.0


def _ethanol_pan_fire(api) -> None:
    api.meshes.add_mesh([30, 30, 30], [0, 3, 0, 3, 0, 3])
    api.reactions.add_simple_reaction("ETHANOL", 26800.0, soot_yield=0.008)
    api.materials.add_liquid_fuel("ETHANOL", "ETHANOL", 78.0, 837.0, 790.0, 2.44, conductivity=0.17)
    api.fires.add_pool_fire("ETHANOL", [1.0, 2.0, 1.0, 2.0, 0.0], depth=0.02, name="PAN")
    for xb in ([0, 3, 0, 0, 0, 3], [0, 3, 3, 3, 0, 3], [0, 0, 0, 3, 0, 3], [3, 3, 0, 3, 0, 3], [0, 3, 0, 3, 3, 3]):
        api.vents.add_vent([float(v) for v in xb], "OPEN")
    api.devices.add_device("HRRPUV", [1.5, 1.5, 0.5], name="FLAME_ZONE")
    api.slices.add_slice("TEMPERATURE", "Y", 1.5)
    api.project.params.t_end = 15.0


def _insulated_steel_column(api) -> None:
    from pyfds.domain.model import Layer, Material, Surface
    api.meshes.add_mesh([30, 30, 30], [0, 3, 0, 3, 0, 3])
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)
    api.materials.add(Material(name="STEEL", density=7850.0, conductivity=45.8, specific_heat=0.46))
    api.materials.add(Material(name="INSULATION", density=280.0, conductivity=0.078, specific_heat=1.0))
    api.surfaces.add(Surface(name="PROTECTED STEEL", color="GRAY",
                             layers=[Layer(material_id="INSULATION", thickness=0.02),
                                     Layer(material_id="STEEL", thickness=0.01)]))
    api.obstructions.add_obstruction([1.7, 1.9, 1.7, 1.9, 0.0, 3.0], "PROTECTED STEEL", name="COLUMN")
    burner = api.surfaces.add_burner(hrrpua=800.0, tau_q=1.0, name="BURNER")
    api.vents.add_vent([0.6, 1.4, 1.0, 2.0, 0.0, 0.0], burner.name)
    for xb in ([0, 3, 0, 0, 0, 3], [0, 3, 3, 3, 0, 3], [0, 0, 0, 3, 0, 3], [3, 3, 0, 3, 0, 3], [0, 3, 0, 3, 3, 3]):
        api.vents.add_vent([float(v) for v in xb], "OPEN")
    api.devices.add_device("WALL TEMPERATURE", [1.8, 1.6, 1.5], name="COLUMN_SURFACE", ior=-2)
    api.project.params.t_end = 30.0


def _sprinkler_suppression(api) -> None:
    api.meshes.add_mesh([40, 40, 25], [0, 4, 0, 4, 0, 2.5])
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)
    api.ramps.add_ramp("FIRE_GROWTH", [0.0, 5.0, 10.0], [0.0, 0.5, 1.0])
    burner = api.surfaces.add_burner(hrrpua=600.0, tau_q=-10.0, name="BURNER", ramp_q="FIRE_GROWTH")
    api.vents.add_vent([1.7, 2.3, 1.7, 2.3, 0.0, 0.0], burner.name)
    api.vents.add_vent([0.0, 4.0, 0.0, 0.0, 0.0, 2.5], "OPEN")
    api.vents.add_vent([0.0, 4.0, 4.0, 4.0, 0.0, 2.5], "OPEN")
    api.props.add_sprinkler("SPRINKLER", rti=50.0, activation_temperature=68.0)
    api.devices.add_sprinkler([2.0, 2.0, 2.4], "SPRINKLER", id="SPK1")
    api.devices.add_thermocouple([2.0, 2.0, 2.3], "TC_CEILING")
    api.project.params.t_end = 20.0


_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "burner_fire": {"title": "Burner fire", "build": _burner_fire,
                    "about": "A propane burner on the floor of a 3 m cube with open sides. Watch the thermocouple above "
                             "the burner and the temperature slice."},
    "air_movement": {"title": "Air movement", "build": _air_movement,
                     "about": "Supply air through a wall vent, past a box, out of an open vent. View the velocity slice."},
    "ethanol_pan_fire": {"title": "Ethanol pan fire", "build": _ethanol_pan_fire,
                         "about": "A liquid-fuel pool fire: the burning rate follows from the ethanol properties."},
    "insulated_steel_column": {"title": "Insulated steel column", "build": _insulated_steel_column,
                               "about": "A two-layer (insulation + steel) column next to a burner; read the column surface temperature."},
    "sprinkler_suppression": {"title": "Sprinkler over a growing fire", "build": _sprinkler_suppression,
                              "about": "A ramped burner under a ceiling sprinkler; check when the link activates."},
}


class ExamplesManager:
    def __init__(self, api) -> None:
        self._api = api

    def list(self) -> List[Dict[str, str]]:
        return [{"name": k, "title": v["title"], "about": v["about"]} for k, v in _EXAMPLES.items()]

    def load(self, name: str) -> Dict[str, str]:
        """Replace the current project with example *name*."""
        try:
            ex = _EXAMPLES[name]
        except KeyError:
            raise KeyError(f"unknown example {name!r}; known: {', '.join(_EXAMPLES)}") from None
        self._api.new(chid=name, title=ex["title"])
        ex["build"](self._api)
        self._api.history.clear()      # the example is the starting point; there is nothing to undo
        return {"name": name, "title": ex["title"], "about": ex["about"]}
