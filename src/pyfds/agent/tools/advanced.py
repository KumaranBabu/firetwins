"""Controls, 3-D output, mesh order/alignment and the raw additional-fields table (A1)."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_control_functions, list_quantities
from .base import ToolSpec, _find_entity_by_name, _remove_from

_NAME = {"type": "string"}
_XB = {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."}


def _extras_manager(api, entity):
    from pyfds.api.base import _CollectionManager
    return _CollectionManager(api, type(entity))


TOOLS: List[ToolSpec] = [
    ToolSpec(
        name="add_control",
        description="Add a control (&CTRL) with a known FUNCTION_TYPE. ANY/ALL/ONLY take one or more inputs, "
                    "TIME_DELAY/DEADBAND/CUSTOM/KILL/RESTART/PID exactly one; math functions take several.",
        input_schema={"type": "object", "properties": {
            "function_type": {"type": "string", "enum": list_control_functions()},
            "input_ids": {"type": "array", "items": _NAME, "description": "Device or control names."},
            "name": _NAME, "delay": {"type": "number"}, "setpoint": {"type": "number"},
            "n": {"type": "integer", "description": "Required for ONLY."},
            "ramp_id": _NAME, "latch": {"type": "boolean"}, "initial_state": {"type": "boolean"}},
            "required": ["function_type"]},
        handler=lambda api, function_type, input_ids=None, name="", **fields:
            api.controls.add_control(function_type, input_ids, name, **fields),
    ),
    ToolSpec(
        name="list_controls",
        description="List all controls (&CTRL) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.controls.all(), mutates=False,
    ),
    ToolSpec(
        name="remove_control",
        description="Remove a control by name.",
        input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.controls, name),
    ),
    ToolSpec(
        name="add_heat_detector_prop",
        description="Add a heat-detector property set (&PROP): RTI and activation temperature (C).",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "rti": {"type": "number", "default": 5.0},
            "activation_temperature": {"type": "number", "default": 74.0}}},
        handler=lambda api, name=None, rti=5.0, activation_temperature=74.0:
            api.props.add_heat_detector(name, rti=rti, activation_temperature=activation_temperature),
    ),
    ToolSpec(
        name="add_volume_slice",
        description="Add a 3-D (volumetric) slice (&SLCF with XB) of a quantity over a box.",
        input_schema={"type": "object", "properties": {
            "quantity": {"type": "string", "enum": list_quantities("SLCF")}, "xb": _XB, "name": _NAME},
            "required": ["quantity", "xb"]},
        handler=lambda api, quantity, xb, name=None:
            api.slices.add_volume_slice(quantity, xb, **({"name": name} if name else {})),
    ),
    ToolSpec(
        name="add_smoke3d",
        description="Add a 3-D smoke output request (&SM3D) for Smokeview smoke/fire rendering.",
        input_schema={"type": "object", "properties": {
            "quantity": {"type": "string", "default": "DENSITY"}, "spec_id": _NAME, "name": _NAME}},
        handler=lambda api, quantity="DENSITY", spec_id=None, name=None:
            api.smoke3ds.add_smoke3d(quantity, spec_id, name),
    ),
    ToolSpec(
        name="list_smoke3d",
        description="List all 3-D smoke output requests (&SM3D).",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.smoke3ds.all(), mutates=False,
    ),
    ToolSpec(
        name="remove_smoke3d",
        description="Remove a 3-D smoke output request by name.",
        input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.smoke3ds, name),
    ),
    ToolSpec(
        name="set_mesh_order",
        description="Set mesh priority: names listed first win where meshes overlap and are written first. "
                    "Unlisted meshes follow in their current order.",
        input_schema={"type": "object", "properties": {
            "names": {"type": "array", "items": _NAME}}, "required": ["names"]},
        handler=lambda api, names: api.meshes.set_order(names),
    ),
    ToolSpec(
        name="mesh_alignment_test",
        description="Run the mesh alignment test; returns {mesh name: 'Passed' | 'Failed'}.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.meshes.alignment_test(), mutates=False,
    ),
    ToolSpec(
        name="list_model_checks",
        description="List every model check (validation rule) with its description and whether it is enabled.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.validation.checks(), mutates=False,
    ),
    ToolSpec(
        name="set_model_check_enabled",
        description="Switch one model check on or off for this project (saved with the project).",
        input_schema={"type": "object", "properties": {
            "name": _NAME, "enabled": {"type": "boolean"}}, "required": ["name", "enabled"]},
        handler=lambda api, name, enabled: api.validation.set_enabled(name, enabled),
    ),
    ToolSpec(
        name="export_check_set",
        description="Save which model checks are on/off to a JSON file so it can be shared.",
        input_schema={"type": "object", "properties": {"filepath": _NAME, "name": _NAME},
                      "required": ["filepath"]},
        handler=lambda api, filepath, name="": api.validation.export_check_set(filepath, name),
        mutates=False,
    ),
    ToolSpec(
        name="import_check_set",
        description="Apply a shared model-check set from a JSON file; returns check names it did not recognise.",
        input_schema={"type": "object", "properties": {"filepath": _NAME}, "required": ["filepath"]},
        handler=lambda api, filepath: api.validation.import_check_set(filepath),
    ),
    ToolSpec(
        name="list_entity_extras",
        description="List the additional FDS keywords (not covered by a typed field) kept on a named entity.",
        input_schema={"type": "object", "properties": {"entity": _NAME}, "required": ["entity"]},
        handler=lambda api, entity: dict(_find_entity_by_name(api, entity).fds_extra or {}),
        mutates=False,
    ),
    ToolSpec(
        name="set_entity_extra",
        description="Add or change an additional FDS keyword on a named entity (written verbatim, so quote "
                    "strings yourself, e.g. \"'ABC'\"). Typed fields are rejected: use the edit tool.",
        input_schema={"type": "object", "properties": {
            "entity": _NAME, "key": _NAME, "value": {"description": "number, boolean or raw text"}},
            "required": ["entity", "key", "value"]},
        handler=lambda api, entity, key, value: _set_extra(api, entity, key, value),
    ),
    ToolSpec(
        name="remove_entity_extra",
        description="Remove an additional FDS keyword from a named entity.",
        input_schema={"type": "object", "properties": {"entity": _NAME, "key": _NAME},
                      "required": ["entity", "key"]},
        handler=lambda api, entity, key: _remove_extra(api, entity, key),
    ),
]


def _set_extra(api, entity_name, key, value):
    entity = _find_entity_by_name(api, entity_name)
    return _extras_manager(api, entity).set_extra(entity, key, value)


def _remove_extra(api, entity_name, key):
    entity = _find_entity_by_name(api, entity_name)
    return _extras_manager(api, entity).remove_extra(entity, key)
