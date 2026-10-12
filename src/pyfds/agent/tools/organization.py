"""Scenario and floor tools."""
from __future__ import annotations

from typing import List

from .base import ToolSpec, _find_entity_by_name


TOOLS: List[ToolSpec] = [

    # ── Scenarios (named simulation variants — per-entity field overrides) ──
    ToolSpec(
        name="create_scenario",
        description="Create a named simulation variant (scenario) that will later hold per-entity field overrides.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
            "required": ["name"],
        },
        handler=lambda api, name, description="": api.scenarios.create(name, description),
    ),
    ToolSpec(
        name="list_scenarios",
        description="List all scenarios in the active project, including their overrides and which one (if any) is active.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.scenarios.all(),
        mutates=False,
    ),
    ToolSpec(
        name="clone_scenario",
        description="Deep-copy an existing scenario (including its overrides) under a new name.",
        input_schema={
            "type": "object",
            "properties": {"base_name": {"type": "string"}, "new_name": {"type": "string"}},
            "required": ["base_name", "new_name"],
        },
        handler=lambda api, base_name, new_name: api.scenarios.clone(base_name, new_name),
    ),
    ToolSpec(
        name="delete_scenario",
        description="Delete a scenario by name. Fails if it is currently active — reset_scenario() first.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: api.scenarios.delete(name),
    ),
    ToolSpec(
        name="add_scenario_override",
        description=(
            "Record that entity_name's field_name should equal value whenever scenario_name is "
            "applied — does not change the project until apply_scenario() is called."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scenario_name": {"type": "string"},
                "entity_name": {"type": "string", "description": "Name of any entity already in the project."},
                "field_name": {"type": "string", "description": "Field to override, e.g. heat_release_rate."},
                "value": {"description": "New value for the field — number, string, or boolean."},
            },
            "required": ["scenario_name", "entity_name", "field_name", "value"],
        },
        handler=lambda api, scenario_name, entity_name, field_name, value: api.scenarios.set_override(
            scenario_name, _find_entity_by_name(api, entity_name), field_name, value
        ),
    ),
    ToolSpec(
        name="apply_scenario",
        description="Apply a scenario's overrides to the active project. Fails if another scenario is already active.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: api.scenarios.apply(name),
    ),
    ToolSpec(
        name="reset_scenario",
        description="Restore all entity values patched by the currently active scenario.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.scenarios.reset(),
    ),
    ToolSpec(
        name="export_scenarios",
        description=(
            "Apply each scenario in turn, write it to its own <dirpath>/<scenario_name>/<scenario_name>.fds, "
            "then reset — produces one independent .fds file per named variant."
        ),
        input_schema={"type": "object", "properties": {"dirpath": {"type": "string"}}, "required": ["dirpath"]},
        handler=lambda api, dirpath: api.scenarios.export_all(dirpath),
    ),

    # ── Floors (organise entities by building storey) ────────────────────────
    ToolSpec(
        name="define_floor",
        description="Define (or redefine) a named elevation band [z_min, z_max) used to organise entities by storey.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "z_min": {"type": "number"},
                "z_max": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["name", "z_min", "z_max"],
        },
        handler=lambda api, name, z_min, z_max, description="": api.floors.define_floor(
            name, z_min, z_max, description
        ),
    ),
    ToolSpec(
        name="list_floors",
        description="List all defined floors, sorted by elevation.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.floors.all_floors(),
        mutates=False,
    ),
    ToolSpec(
        name="delete_floor",
        description="Delete a floor by name; entities assigned to it become unassigned.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: api.floors.delete_floor(name),
    ),
    ToolSpec(
        name="assign_entity_to_floor",
        description="Manually assign a named entity to a named floor (overrides bbox-based auto-detection for it).",
        input_schema={
            "type": "object",
            "properties": {"entity_name": {"type": "string"}, "floor_name": {"type": "string"}},
            "required": ["entity_name", "floor_name"],
        },
        handler=lambda api, entity_name, floor_name: api.floors.assign(
            _find_entity_by_name(api, entity_name), floor_name
        ),
    ),
    ToolSpec(
        name="auto_assign_floors",
        description="Auto-assign every geometric entity to a floor by its bounding-box z-centre. Returns the count assigned.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.floors.auto_assign_all(),
    ),
    ToolSpec(
        name="export_floors",
        description="Serialize floor definitions and entity assignments (matched by name) to a JSON file.",
        input_schema={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]},
        handler=lambda api, filepath: api.floors.export_floors(filepath),
    ),
    ToolSpec(
        name="import_floors",
        description=(
            "Load floor definitions + assignments from a JSON file (written by export_floors), re-matching "
            "assignments to the active project's entities by name. Returns the number re-matched."
        ),
        input_schema={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]},
        handler=lambda api, filepath: api.floors.import_floors(filepath),
    ),
]
