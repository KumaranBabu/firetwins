"""Reaction, material and ramp tools."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_material_presets
from .base import ToolSpec


TOOLS: List[ToolSpec] = [

    # ── Reactions / materials / ramps ───────────────────────────────────────
    ToolSpec(
        name="add_simple_reaction",
        description="Add a combustion reaction (REAC) with a named fuel and heat of combustion.",
        input_schema={
            "type": "object",
            "properties": {
                "fuel": {"type": "string"},
                "heat_of_combustion": {"type": "number", "description": "kJ/kg"},
                "name": {"type": "string"},
            },
            "required": ["fuel", "heat_of_combustion"],
        },
        handler=lambda api, fuel, heat_of_combustion, name=None: api.reactions.add_simple_reaction(
            fuel=fuel, heat_of_combustion=heat_of_combustion, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_reactions",
        description="List all reactions (REAC) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.reactions.all(),
        mutates=False,
    ),
    ToolSpec(
        name="add_material_from_library",
        description="Add a material (MATL) from the built-in preset library.",
        input_schema={
            "type": "object",
            "properties": {"preset_name": {"type": "string", "enum": list_material_presets()}},
            "required": ["preset_name"],
        },
        handler=lambda api, preset_name: api.materials.add_from_library(preset_name),
    ),
    ToolSpec(
        name="list_materials",
        description="List all materials (MATL) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.materials.all(),
        mutates=False,
    ),
    ToolSpec(
        name="add_ramp",
        description="Add a time/value RAMP (e.g. for a fire growth curve).",
        input_schema={
            "type": "object",
            "properties": {
                "ramp_id": {"type": "string"},
                "times": {"type": "array", "items": {"type": "number"}},
                "values": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["ramp_id", "times", "values"],
        },
        handler=lambda api, ramp_id, times, values: api.ramps.add_ramp(ramp_id=ramp_id, times=times, values=values),
    ),
    ToolSpec(
        name="list_ramps",
        description="List all ramps (RAMP) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.ramps.all(),
        mutates=False,
    ),
]
