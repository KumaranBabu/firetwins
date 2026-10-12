"""HVAC network tools (NODE / DUCT / FAN / DAMPER / FILTER / LEAK)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec, _remove_from


TOOLS: List[ToolSpec] = [

    # ── HVAC network (NODE/DUCT/FAN/DAMPER/FILTER/LEAK) ─────────────────────
    ToolSpec(
        name="add_hvac_node",
        description="Add an HVAC network connection point (&NODE) — a duct endpoint, optionally tied to a VENT or marked ambient (outside air).",
        input_schema={
            "type": "object",
            "properties": {
                "xyz": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "vent_id": {"type": "string", "description": "Optional VENT this node is attached to."},
                "ambient": {"type": "boolean", "default": False, "description": "Outside-air boundary node."},
                "name": {"type": "string"},
            },
            "required": ["xyz"],
        },
        handler=lambda api, xyz, vent_id=None, ambient=False, name=None: api.hvac_nodes.add_node(
            xyz=xyz, vent_id=vent_id, ambient=ambient, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_hvac_nodes",
        description="List all HVAC nodes in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.hvac_nodes.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_hvac_node",
        description="Remove an HVAC node by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.hvac_nodes, name),
    ),
    ToolSpec(
        name="add_hvac_duct",
        description="Add an HVAC duct segment (&DUCT) connecting two existing HVAC nodes.",
        input_schema={
            "type": "object",
            "properties": {
                "node_id_1": {"type": "string"},
                "node_id_2": {"type": "string"},
                "diameter": {"type": "number", "default": 0.5, "description": "Duct diameter, m."},
                "name": {"type": "string"},
            },
            "required": ["node_id_1", "node_id_2"],
        },
        handler=lambda api, node_id_1, node_id_2, diameter=0.5, name=None: api.hvac_ducts.add_duct(
            node_id_1=node_id_1, node_id_2=node_id_2, diameter=diameter, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_hvac_ducts",
        description="List all HVAC ducts in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.hvac_ducts.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_hvac_duct",
        description="Remove an HVAC duct by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.hvac_ducts, name),
    ),
    ToolSpec(
        name="add_fan",
        description="Add a fan (&FAN) driving flow through an existing HVAC duct.",
        input_schema={
            "type": "object",
            "properties": {
                "duct_id": {"type": "string"},
                "volume_flow_rate": {"type": "number", "description": "Nominal volume flow rate, m3/s."},
                "name": {"type": "string"},
            },
            "required": ["duct_id"],
        },
        handler=lambda api, duct_id, volume_flow_rate=None, name=None: api.fans.add_fan(
            duct_id=duct_id, volume_flow_rate=volume_flow_rate, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_fans",
        description="List all HVAC fans in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.fans.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_fan",
        description="Remove an HVAC fan by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.fans, name),
    ),
    ToolSpec(
        name="add_damper",
        description="Add a damper (&DAMPER) on an existing HVAC duct, controlled by a CTRL logic entity.",
        input_schema={
            "type": "object",
            "properties": {
                "duct_id": {"type": "string"},
                "ctrl_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["duct_id", "ctrl_id"],
        },
        handler=lambda api, duct_id, ctrl_id, name=None: api.dampers.add_damper(
            duct_id=duct_id, ctrl_id=ctrl_id, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_dampers",
        description="List all HVAC dampers in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.dampers.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_damper",
        description="Remove an HVAC damper by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.dampers, name),
    ),
    ToolSpec(
        name="add_hvac_filter",
        description="Add a particulate filter (&FILTER) on an existing HVAC duct.",
        input_schema={
            "type": "object",
            "properties": {
                "duct_id": {"type": "string"},
                "efficiency": {"type": "number", "default": 0.9, "description": "Filtration efficiency, 0-1."},
                "name": {"type": "string"},
            },
            "required": ["duct_id"],
        },
        handler=lambda api, duct_id, efficiency=0.9, name=None: api.hvac_filters.add_filter(
            duct_id=duct_id, efficiency=efficiency, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_hvac_filters",
        description="List all HVAC filters in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.hvac_filters.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_hvac_filter",
        description="Remove an HVAC filter by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.hvac_filters, name),
    ),
    ToolSpec(
        name="add_hvac_leakage",
        description="Add a duct leakage path (&LEAK) between two pressure zones.",
        input_schema={
            "type": "object",
            "properties": {
                "zone_id_1": {"type": "string"},
                "zone_id_2": {"type": "string"},
                "area": {"type": "number", "default": 0.001, "description": "Leakage area, m2."},
                "name": {"type": "string"},
            },
            "required": ["zone_id_1", "zone_id_2"],
        },
        handler=lambda api, zone_id_1, zone_id_2, area=0.001, name=None: api.hvac_leakages.add_leakage(
            zone_id_1=zone_id_1, zone_id_2=zone_id_2, area=area, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="add_hvac_aircoil",
        description="Add a duct heat exchanger (&AIRCOIL) to an existing duct.",
        input_schema={
            "type": "object",
            "properties": {
                "duct_id": {"type": "string"},
                "effectiveness": {"type": "number", "default": 0.8},
                "coolant_temperature": {"type": "number", "description": "deg C"},
                "coolant_specific_heat": {"type": "number", "description": "kJ/kg/K"},
                "coolant_mass_flow": {"type": "number", "description": "kg/s"},
                "name": {"type": "string"},
            },
            "required": ["duct_id"],
        },
        handler=lambda api, duct_id, name=None, **kw: api.hvac_aircoils.add_aircoil(
            duct_id, **kw, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_hvac_aircoils",
        description="List all duct heat exchangers (&AIRCOIL).",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.hvac_aircoils.all(),
        mutates=False,
    ),
    ToolSpec(
        name="list_hvac_leakages",
        description="List all HVAC duct leakage paths in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.hvac_leakages.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_hvac_leakage",
        description="Remove an HVAC duct leakage path by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.hvac_leakages, name),
    ),
]
