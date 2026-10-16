"""F5: the Edit Activation Controls dialog (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.activation_controls import ActivationControlsDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.devices.add_device("TEMPERATURE", [1, 1, 1], name="TC1")
    a.devices.add_device("TEMPERATURE", [2, 1, 1], name="TC2")
    a.controls.add_control("ANY", ["TC1"], name="ALARM")
    a.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="door")
    return a


@pytest.fixture
def dlg(api, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = ActivationControlsDialog(api)
    d.warned = warned
    yield d
    d.close()


def test_shows_the_control_its_kind_function_inputs_and_status(dlg):
    assert dlg.names() == ["ALARM"] and dlg.kind_combo.currentText() == "Detector-based"
    assert dlg.function_combo.currentText() == "ANY" and dlg.checked_inputs() == ["TC1"]
    assert dlg.problems_label.text() == "This control is complete."
    assert dlg.delay_box.isHidden() and not dlg.latch_check.isHidden()      # delay only matters for TIME_DELAY


def test_changing_kind_and_function_shows_the_right_parameters(dlg):
    dlg.kind_combo.setCurrentText("Time-based")
    dlg._on_kind()
    assert dlg.function_combo.currentText() == "TIME_DELAY" and not dlg.delay_box.isHidden()
    assert dlg.setpoint_box.isHidden() and "delay" in dlg.description.text().lower()
    dlg.set_function("DEADBAND")
    assert dlg.kind_combo.currentText() == "Deadband-based" and not dlg.deadband_low.isHidden()
    dlg.set_function("ONLY")
    assert not dlg.n_box.isHidden()
    dlg.set_function("PID")
    assert not dlg.setpoint_box.isHidden()


def test_problems_are_live_and_block_saving(dlg, api):
    dlg.set_inputs(["TC1", "TC2"])
    dlg.set_function("TIME_DELAY")                                          # needs exactly one input
    assert "exactly one INPUT_ID" in dlg.problems_label.text() and dlg.problems_label.text().startswith("!")
    assert dlg.is_dirty()
    with pytest.raises(ValueError, match="exactly one INPUT_ID"):
        dlg.apply()
    assert api.controls.get("ALARM").function_type == "ANY"                 # nothing saved
    assert not dlg._apply_quietly() and dlg.warned
    dlg.set_inputs(["TC2"])
    dlg.delay_box.setValue(5.0)
    assert dlg.problems_label.text() == "This control is complete."
    assert dlg.apply()
    c = api.controls.get("ALARM")
    assert (c.function_type, c.delay, c.input_ids) == ("TIME_DELAY", 5.0, ["TC2"])
    api.history.undo()
    c = api.controls.get("ALARM")
    assert (c.function_type, c.input_ids) == ("ANY", ["TC1"])                # one undo step


def test_inputs_never_offer_a_loop(dlg, api):
    other = dlg.new_control("SECOND")
    dlg.set_function("ANY")
    dlg.set_inputs(["ALARM"])
    dlg.apply()
    assert api.controls.inputs_of(other) == ["ALARM"]
    dlg.select("ALARM")
    offered = [dlg.inputs.item(i).text() for i in range(dlg.inputs.count())]
    assert "SECOND" not in offered and "ALARM" not in offered and "TC1" in offered


def test_new_clone_rename_delete(dlg, api):
    c = dlg.new_control("FRESH")
    assert dlg.names() == ["ALARM", "FRESH"] and dlg.list.currentItem().text() == "FRESH"
    dlg.select("ALARM")
    api.controls.assign("ALARM", api.obstructions.get("door"))
    dlg.clone_control("ALARM2")
    copy = api.controls.get("ALARM2")
    assert copy.function_type == "ANY" and api.controls.inputs_of(copy) == ["TC1"] and not api.controls.controlled(copy)
    dlg.select("ALARM")
    dlg.rename_control("MAIN")
    assert api.obstructions.get("door").ctrl_id == "MAIN" and "MAIN" in dlg.names()      # references follow
    assert dlg.rename_control("FRESH") is None and dlg.warned                          # a duplicate is refused
    dlg.select("MAIN")
    assert dlg.delete_control(confirm=False)
    assert api.controls.get("MAIN") is None and api.obstructions.get("door").ctrl_id is None
    api.history.undo()
    assert api.controls.get("MAIN") is not None and api.obstructions.get("door").ctrl_id == "MAIN"


def test_objects_a_control_switches(dlg, api):
    door = api.obstructions.get("door")
    dlg.add_object(door)
    assert door.ctrl_id == "ALARM" and dlg.driven.count() == 1 and "door  (Obstruction)" in dlg.driven.item(0).text()
    dlg.driven.item(0).setSelected(True)
    assert dlg.remove_selected_objects() == 1
    assert door.ctrl_id is None and dlg.driven.count() == 0


def test_used_as_input_note_and_missing_inputs(dlg, api):
    api.controls.add_control("ALL", ["TC1", "ALARM"], name="BOTH")
    dlg.refresh_list("BOTH")
    assert "Not used" in dlg.used_label.text()
    dlg.select("ALARM")
    assert "BOTH" in dlg.used_label.text()
    c = api.controls.get("BOTH")
    c.input_ids = ["TC1", "GONE"]                                            # an imported file may name something missing
    dlg.select("ALARM")
    dlg.select("BOTH")
    texts = [dlg.inputs.item(i).text() for i in range(dlg.inputs.count())]
    assert "GONE (missing)" in texts and "GONE" in dlg.checked_inputs()


def test_unsaved_edits_are_kept_or_refused_when_switching(dlg, api):
    dlg.new_control("B")
    dlg.select("ALARM")
    dlg.latch_check.setChecked(False)
    dlg.select("B")                                                          # leaving saves the valid edit
    assert api.controls.get("ALARM").latch is False


def test_ok_and_menu_entry(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    d = ActivationControlsDialog(api, None, "ALARM")
    d.set_inputs([])
    d._on_ok()
    assert d.result() == 0                                                   # ANY with no input: refused, stays open
    d.set_inputs(["TC1", "TC2"])
    d._on_ok()
    assert d.result() == 1 and api.controls.get("ALARM").input_ids == ["TC1", "TC2"]
    d.close()
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(ActivationControlsDialog, "exec", lambda self: 0)
    w = MainWindow(api)
    w.explorer.select_entity("controls", api.controls.get("ALARM"))
    w.action_registry.action("model.edit.activation").trigger()
    assert w._activation_dialog.list.currentItem().text() == "ALARM"
    w.close()
