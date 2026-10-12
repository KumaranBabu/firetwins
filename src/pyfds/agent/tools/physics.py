"""Typed surfaces, liquid fuels, complex reactions, environment and gravity (P0 partial rows)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}

_KINDS = ["air_leak", "basic", "burner", "exhaust", "general", "heater_cooler", "layered", "supply"]


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


TOOLS: List[ToolSpec] = [
    _spec("add_typed_surface", "Add a surface of one of the eight types (burner needs heat_release_rate kW/m2; supply/exhaust "
          "need flow m/s or volume_flow m3/s as positive magnitudes; heater_cooler needs tmp_front; air_leak needs leak_path).",
          {"kind": {"type": "string", "enum": _KINDS}, "name": _STR, "heat_release_rate": _NUM, "tau_q": _NUM,
           "flow": _NUM, "volume_flow": _NUM, "tmp_front": _NUM, "leak_path": {"type": "array", "items": _STR},
           "color": _STR}, ["kind"],
          lambda api, kind, name=None, **kw: api.surfaces.add_typed(kind, name, **kw).name),
    _spec("surface_kind", "Which of the eight surface types a surface is.", {"surface": _STR}, ["surface"],
          lambda api, surface: api.surfaces.kind(surface), mutates=False),
    _spec("add_liquid_fuel", "Add a liquid-fuel material for pool fires.",
          {"name": _STR, "fuel_species": _STR, "boiling_temperature": {**_NUM, "description": "deg C"},
           "heat_of_vaporization": {**_NUM, "description": "kJ/kg"}, "density": _NUM,
           "specific_heat": {**_NUM, "description": "kJ/kg/K"}, "conductivity": _NUM, "absorption_coefficient": _NUM},
          ["name", "fuel_species", "boiling_temperature", "heat_of_vaporization", "density", "specific_heat"],
          lambda api, **kw: api.materials.add_liquid_fuel(**kw).name),
    _spec("add_complex_reaction", "Reaction with explicit stoichiometry: reactants/products map species to positive coefficients; "
          "mass must balance.",
          {"reactants": {"type": "object", "additionalProperties": _NUM},
           "products": {"type": "object", "additionalProperties": _NUM},
           "exponents": {"type": "object", "additionalProperties": _NUM}, "name": _STR,
           "heat_of_combustion": _NUM, "soot_yield": _NUM, "co_yield": _NUM},
          ["reactants", "products"],
          lambda api, **kw: api.reactions.add_complex_reaction(**kw).name),
    _spec("get_environment", "Ambient temperature, pressure, humidity and gravity (with ramps).", {}, [],
          lambda api: api.environment.get(), mutates=False),
    _spec("set_ambient_conditions", "Set ambient temperature (deg C), pressure (Pa) and/or humidity (%).",
          {"temperature": _NUM, "pressure": _NUM, "humidity": _NUM}, [],
          lambda api, **kw: api.environment.set_ambient(**kw)),
    _spec("set_gravity", "Set the gravity vector and/or per-axis time ramps (ramp ids; empty string clears).",
          {"vector": {"type": "array", "items": _NUM, "minItems": 3, "maxItems": 3},
           "ramp_x": _STR, "ramp_y": _STR, "ramp_z": _STR}, [],
          lambda api, vector=None, **kw: api.environment.set_gravity(
              vector, **{k: (v or None) for k, v in kw.items()})),
]
