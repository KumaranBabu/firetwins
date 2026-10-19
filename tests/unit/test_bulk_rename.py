"""PyroSim "Bulk Renaming": name templates with keywords, unique names, references that follow, one undo step, the dialog."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.api.renaming import KEYWORDS


@pytest.fixture
def api():
    a = FdsApi()
    a.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="Exterior56")
    a.obstructions.add_obstruction([2, 3, 0, 1, 0, 1], name="Wall7")
    a.obstructions.add_obstruction([4, 5, 0, 1, 0, 1], name="12Roof")
    return a


def _names(api):
    return [o.name for o in api.obstructions.all()]


def test_the_manuals_example_template(api):
    door = api.obstructions.get("Exterior56")
    assert api.rename.expand("${base_name}${type}_${post_num}", door).replace("Obstruction", "Door") == "ExteriorDoor_56"


def test_keywords_are_worked_out_for_each_object(api):
    objs = api.obstructions.all()
    assert api.rename.expand("${pre_num}|${base_name}|${post_num}", objs[2]) == "12|Roof|"
    assert [api.rename.expand("${sel_index}/${global_index}/${local_index}", o, i) for i, o in enumerate(objs, 1)] == ["1/1/1", "2/2/2", "3/3/3"]
    api.groups.create("Walls")
    api.groups.assign(objs[1], "Walls")
    assert api.rename.expand("${parent_name}", objs[1]) == "Walls" and api.rename.expand("${parent_name-2}", objs[1]) == ""
    assert api.rename.expand("${results_id}x", objs[0]) == "x"
    assert set(KEYWORDS) >= {"name", "base_name", "parent_name", "pre_num", "post_num", "sel_index", "global_index", "local_index", "results_id", "type"}


def test_an_unknown_keyword_is_refused_with_the_valid_ones(api):
    with pytest.raises(ValueError, match="unknown keyword.*base_name"):
        api.rename.expand("${nope}", api.obstructions.all()[0])


def test_one_name_for_many_objects_is_made_unique(api):
    plan = api.rename.preview(api.obstructions.all(), name="Box")
    assert [n for _e, n in plan] == ["Box", "Box 2", "Box 3"]


def test_a_name_used_by_an_object_that_is_not_selected_is_avoided(api):
    plan = api.rename.preview(api.obstructions.all()[:1], name="Wall7")
    assert plan[0][1] == "Wall7 2"


def test_rename_is_one_undo_step_and_references_follow(api):
    api.surfaces.add_burner(hrrpua=100.0, name="Fire")
    api.vents.add_vent(xb=(0, 1, 0, 0, 0, 1), surf_id="Fire", name="V1")
    surface = api.surfaces.get("Fire")
    assert api.rename.rename([surface], template="${name}_burner") == 1
    assert surface.name == "Fire_burner" and api.vents.get("V1").surface_id == "Fire_burner"
    api.history.undo()
    assert surface.name == "Fire" and api.vents.get("V1").surface_id == "Fire"


def test_templates_that_give_an_empty_name_or_nothing_are_refused(api):
    with pytest.raises(ValueError, match="empty name"):
        api.rename.preview([api.obstructions.get("12Roof")], template="${post_num}")      # this name has no trailing number
    with pytest.raises(ValueError):
        api.rename.preview(api.obstructions.all(), name="  ")
    with pytest.raises(ValueError):
        api.rename.preview(api.obstructions.all())


def test_the_dialog_previews_and_applies_a_template(api):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from pyfds.gui.rename_dialog import RenameDialog
    QApplication.instance() or QApplication([])
    dlg = RenameDialog(api, api.obstructions.all())
    dlg.template_check.setChecked(True)
    dlg.edit.setText("")
    dlg.insert_keyword("type")
    dlg.edit.insert("_")
    dlg.insert_keyword("sel_index")
    assert dlg.edit.text() == "${type}_${sel_index}" and dlg.preview.count() == 3
    assert dlg.preview.item(0).text() == "Exterior56  ->  Obstruction_1" and dlg.buttons.button(QDialogButtonBox.Ok).isEnabled()
    dlg.edit.setText("${bad}")
    assert "unknown keyword" in dlg.error.text() and not dlg.buttons.button(QDialogButtonBox.Ok).isEnabled()
    dlg.edit.setText("${type}_${sel_index}")
    dlg.buttons.accepted.emit()
    assert _names(api) == ["Obstruction_1", "Obstruction_2", "Obstruction_3"] and dlg.changed == 3
    dlg.close()


def test_set_as_active_reaction_disables_the_others_and_undoes_in_one_step():
    api = FdsApi()
    a = api.reactions.add_simple_reaction(fuel="PROPANE", heat_of_combustion=46000.0)
    b = api.reactions.add_simple_reaction(fuel="METHANE", heat_of_combustion=50000.0)
    api.reactions.set_active(b)
    assert (a.enabled, b.enabled) == (False, True)
    api.history.undo()
    assert (a.enabled, b.enabled) == (True, True)
    with pytest.raises(KeyError):
        api.reactions.set_active("nope")


def test_reaction_context_menu_offers_set_as_active():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    r = w.api.reactions.add_simple_reaction(fuel="PROPANE", heat_of_combustion=46000.0)
    menu = w._build_entity_context_menu("reactions", r)
    assert "Set as &Active Reaction" in [a.text() for a in menu.actions()]
    other = w.api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="o")
    assert "Set as &Active Reaction" not in [a.text() for a in w._build_entity_context_menu("obstructions", other).actions()]
    w.close()
