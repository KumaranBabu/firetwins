"""
Unit tests — pydantic-introspection property editor schema
(src/pyfds/gui/property_schema.py).

Pure logic, no Qt/display dependency at all.
"""
from __future__ import annotations

import pytest

from pyfds.api import FdsApi
from pyfds.gui.property_schema import apply_edits, build_edit_schema


@pytest.fixture
def api():
    return FdsApi()


def test_obstruction_schema_exposes_simple_scalar_fields(api):
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1", color="RED")
    schema = build_edit_schema(obst)

    props = schema["properties"]
    assert props["x_max"] == {"type": "number", "default": 1.0}
    assert props["color"] == {"type": "string", "default": "RED"}
    assert props["name"]["type"] == "string"
    assert schema["required"] == []  # editing, not creating — nothing mandatory


def test_schema_skips_unsupported_list_fields(api):
    mat = api.materials.add_from_library("concrete")
    schema = build_edit_schema(mat)
    # Material.reactions is List[MaterialReaction] — a nested model list,
    # not a simple scalar/tuple; must not appear.
    assert "reactions" not in schema["properties"]
    assert "nu_gases" not in schema["properties"]  # Optional[List[float]]
    assert "density" in schema["properties"]  # a plain float field


def test_schema_exposes_fixed_length_tuple_fields_as_arrays(api):
    device = api.devices.add_thermocouple(xyz=[1.0, 2.0, 3.0], devc_id="tc1")
    schema = build_edit_schema(device)

    xyz_prop = schema["properties"]["xyz"]
    assert xyz_prop["type"] == "array"
    assert xyz_prop["minItems"] == 3
    assert xyz_prop["maxItems"] == 3
    assert xyz_prop["default"] == [1.0, 2.0, 3.0]


def test_schema_handles_unset_optional_tuple_field(api):
    # rgb is Optional[Tuple[int,int,int]] and unset by default — no "default"
    # key should be present in that case (there's nothing to prefill).
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    schema = build_edit_schema(obst)
    assert "rgb" in schema["properties"]
    assert "default" not in schema["properties"]["rgb"]


def test_schema_exposes_bool_field(api):
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1", thicken=True)
    schema = build_edit_schema(obst)
    assert schema["properties"]["thicken"] == {"type": "boolean", "default": True}


def test_apply_edits_uses_undoable_command_and_skips_unchanged(api):
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    changed = apply_edits(api, obst, {"x_max": 5.0, "name": "box1", "color": "GRAY"})

    assert changed == 1  # only x_max actually differs from current
    assert obst.x_max == 5.0

    api.history.undo()
    assert obst.x_max == 1.0


def test_apply_edits_converts_list_back_to_tuple_for_comparison(api):
    device = api.devices.add_thermocouple(xyz=[1.0, 2.0, 3.0], devc_id="tc1")

    # SchemaFormDialog.values() returns arrays as plain lists — must compare
    # correctly against the tuple-typed field and not treat it as "changed"
    # when the values are actually identical.
    changed = apply_edits(api, device, {"xyz": [1.0, 2.0, 3.0]})
    assert changed == 0

    changed2 = apply_edits(api, device, {"xyz": [9.0, 9.0, 9.0]})
    assert changed2 == 1
    assert device.xyz == (9.0, 9.0, 9.0)
