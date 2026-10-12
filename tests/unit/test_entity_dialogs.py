"""
Unit tests — generic schema-driven "Add Entity" dialog
(src/pyfds/gui/entity_dialogs.py).

Headless via QT_QPA_PLATFORM=offscreen. Verifies the dialog renders one
field per JSON-Schema property and round-trips typed values (number,
integer, array, enum) the same way ``pyfds.agent.registry`` tool handlers
expect them.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dialog(schema, title="Test", description=""):
    from pyfds.gui.entity_dialogs import SchemaFormDialog
    return SchemaFormDialog(title, description, schema)


def test_add_mesh_schema_round_trips_array_and_string_fields():
    from pyfds.agent.registry import get_tool
    tool = get_tool("add_mesh")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)

    dialog._fields["ijk"].setText("10, 10, 5")
    dialog._fields["xb"].setText("0, 4, 0, 4, 0, 2")
    dialog._fields["name"].setText("m1")

    values = dialog.values()
    assert values == {"ijk": [10, 10, 5], "xb": [0.0, 4.0, 0.0, 4.0, 0.0, 2.0], "name": "m1"}


def test_missing_required_field_raises():
    from pyfds.agent.registry import get_tool
    tool = get_tool("add_mesh")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)
    dialog._fields["xb"].setText("0, 4, 0, 4, 0, 2")
    # ijk left blank — required

    with pytest.raises(ValueError):
        dialog.values()


def test_optional_blank_field_is_omitted():
    from pyfds.agent.registry import get_tool
    tool = get_tool("add_obstruction")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)
    dialog._fields["xb"].setText("0, 1, 0, 1, 0, 1")
    # surf_id has a default in the widget already (INERT default not set here); leave name blank

    values = dialog.values()
    assert "name" not in values
    assert values["xb"] == [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]


def test_enum_field_renders_as_combo_box():
    from pyfds.agent.registry import get_tool
    tool = get_tool("characterise_fire")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)
    assert isinstance(dialog._fields["growth"], QComboBox)
    assert isinstance(dialog._fields["hrr_kw"], QLineEdit)


def test_wrong_array_length_raises():
    from pyfds.agent.registry import get_tool
    tool = get_tool("add_mesh")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)
    dialog._fields["ijk"].setText("10, 10")  # needs exactly 3
    dialog._fields["xb"].setText("0, 4, 0, 4, 0, 2")

    with pytest.raises(ValueError):
        dialog.values()


def test_boolean_field_renders_as_checkbox_and_defaults():
    from pyfds.agent.registry import get_tool
    tool = get_tool("configure_simulation_params")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)

    box = dialog._fields["restrict_time_step"]
    assert isinstance(box, QCheckBox)
    assert box.isChecked() is True  # schema default

    values = dialog.values()
    assert values["restrict_time_step"] is True

    box.setChecked(False)
    values = dialog.values()
    assert values["restrict_time_step"] is False


def test_boolean_field_always_present_never_treated_as_required_blank():
    from pyfds.agent.registry import get_tool
    tool = get_tool("configure_simulation_params")
    dialog = _dialog(tool.input_schema, tool.name, tool.description)
    dialog._fields["t_end"].setText("120")
    # t_begin/dt left blank (optional) — restrict_time_step is a checkbox,
    # never "blank", so it must always appear in values() regardless.

    values = dialog.values()
    assert values["t_end"] == 120.0
    assert "restrict_time_step" in values
    assert "dt" not in values
