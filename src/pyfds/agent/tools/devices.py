"""Device (thermocouple, sprinkler, …) tools."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_quantities
from .base import ToolSpec, _remove_from


TOOLS: List[ToolSpec] = [

    # ── Devices ──────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_thermocouple",
        description="Add a temperature-sensing device at a point.",
        input_schema={
            "type": "object",
            "properties": {
                "xyz": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "devc_id": {"type": "string"},
            },
            "required": ["xyz"],
        },
        handler=lambda api, xyz, devc_id="": api.devices.add_thermocouple(xyz=xyz, devc_id=devc_id),
    ),
    ToolSpec(
        name="add_sprinkler",
        description="Add a sprinkler/heat-detector device using an existing PROP.",
        input_schema={
            "type": "object",
            "properties": {
                "xyz": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "prop_id": {"type": "string", "description": "Name of an existing PROP definition."},
                "id": {"type": "string"},
            },
            "required": ["xyz", "prop_id"],
        },
        handler=lambda api, xyz, prop_id, id=None: api.devices.add_sprinkler(
            xyz=xyz, prop_id=prop_id, **({"id": id} if id else {})
        ),
    ),
    ToolSpec(
        name="add_device",
        description=(
            "Add a generic sensor at a point using any valid FDS DEVC quantity — "
            "smoke/heat detector, nozzle, flow-measuring device, gas/solid-phase probe, "
            "beam detector, aspirator, etc. — not just the thermocouple/sprinkler shortcuts."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("DEVC"),
                             "description": "FDS DEVC output quantity."},
                "xyz": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "name": {"type": "string"},
                "prop_id": {"type": "string",
                            "description": "Optional PROP reference (activation properties)."},
            },
            "required": ["quantity", "xyz"],
        },
        handler=lambda api, quantity, xyz, name=None, prop_id=None: api.devices.add_device(
            quantity=quantity, xyz=xyz,
            **({"name": name} if name else {}),
            **({"prop_id": prop_id} if prop_id else {}),
        ),
    ),
    ToolSpec(
        name="list_devices",
        description="List all devices (DEVC) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.devices.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_device",
        description="Remove a device by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.devices, name),
    ),
]
