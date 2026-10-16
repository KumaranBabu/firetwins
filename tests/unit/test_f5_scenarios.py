"""F5: the Edit Scenarios dialog and the scenario update/override API behind it (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.scenarios import AddOverrideDialog, ScenariosDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    return a


@pytest.fixture
def dlg(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = ScenariosDialog(api)
    yield d
    d.close()


# -- backend -----------------------------------------------------------------------------------------
def test_update_renames_keeps_order_and_undoes(api):
    api.scenarios.create("a")
    api.scenarios.create("b")
    api.scenarios.update("a", new_name="z", description="d", tags=["x", " y ", ""])
    assert [s.name for s in api.scenarios.all()] == ["z", "b"]
    assert api.scenarios.get("z").description == "d" and api.scenarios.get("z").tags == ["x", "y"]
    api.history.undo()
    assert [s.name for s in api.scenarios.all()] == ["a", "b"] and api.scenarios.get("a").description == ""


def test_update_refuses_clash_blank_and_active(api):
    api.scenarios.create("a")
    api.scenarios.create("b")
    with pytest.raises(ValueError):
        api.scenarios.update("a", new_name="b")
    with pytest.raises(ValueError):
        api.scenarios.update("a", new_name="  ")
    api.scenarios.apply("a")
    with pytest.raises(RuntimeError):
        api.scenarios.update("a", new_name="c")
    assert api.scenarios.get("a") is not None


def test_overrides_list_and_remove(api):
    m = api.meshes.get("M")
    api.scenarios.create("s")
    api.scenarios.set_override("s", m, "x_max", 3.0)
    row = api.scenarios.overrides("s")[0]
    assert row["entity"] is m and row["field"] == "x_max" and row["value"] == 3.0 and row["kind"] == "Mesh"
    api.scenarios.remove_override("s", m, "x_max")
    assert api.scenarios.overrides("s") == []
    api.history.undo()
    assert len(api.scenarios.overrides("s")) == 1
    with pytest.raises(KeyError):
        api.scenarios.remove_override("s", m, "y_max")


# -- dialog -------------------------------------------------------------------------------------------
def test_create_clone_rename_delete(dlg, api):
    dlg.new_scenario("base", "the base case")
    assert dlg.names() == ["base"] and dlg.description.text() == "the base case"
    dlg.clone_scenario("variant")
    assert dlg.names() == ["base", "variant"] and dlg.list.currentItem().text() == "variant"
    dlg.rename_scenario("high")
    assert dlg.names() == ["base", "high"]
    assert dlg.new_scenario("base") is None                       # duplicate -> message, no crash
    dlg.delete_scenario(confirm=False)
    assert dlg.names() == ["base"] and api.scenarios.get("high") is None


def test_description_and_tags_are_saved_when_leaving(dlg, api):
    dlg.new_scenario("a")
    dlg.new_scenario("b")
    dlg.select("a")
    dlg.description.setText("hot case")
    dlg.tags.setText("fast, hot")
    dlg.select("b")
    s = api.scenarios.get("a")
    assert s.description == "hot case" and s.tags == ["fast", "hot"]


def test_override_table_add_remove_and_object_toggle(dlg, api):
    m = api.meshes.get("M")
    dlg.new_scenario("s")
    dlg.add_override(m, "x_max", 2.0)
    dlg.toggle_object(m, False)
    assert ("M", "x_max", "2.0") in dlg.overrides_in_table() and ("M", "enabled", "False") in dlg.overrides_in_table()
    dlg.table.selectRow(0)
    assert dlg.remove_selected() == 1 and len(dlg.overrides_in_table()) == 1


def test_add_override_dialog_converts_units(api):
    api.units.set_system("EN")
    m = api.meshes.get("M")
    d = AddOverrideDialog(api, None, m)
    d.select_field("x_max")
    d.set_value(6.56168)                                          # 2 m typed in feet
    assert d.result_value() == pytest.approx(2.0, rel=1e-4)
    assert "name" not in [d.field_combo.itemData(i) for i in range(d.field_combo.count())]
    d.close()


def test_apply_and_reset_change_the_model_and_notify(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    seen = []
    d = ScenariosDialog(api, None, lambda: seen.append(1))
    m = api.meshes.get("M")
    d.new_scenario("wide")
    d.add_override(m, "x_max", 5.0)
    assert d.apply_scenario() and m.x_max == 5.0 and "wide" in d.status.text()
    assert not d.buttons_left["delete"].isEnabled() and not d.buttons_left["rename"].isEnabled()
    d.reset_model()
    assert m.x_max == 1.0 and len(seen) == 2 and d.buttons_left["apply"].isEnabled()
    d.close()


def test_menu_opens_the_dialog(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(ScenariosDialog, "exec", lambda self: 0)
    w = MainWindow(FdsApi())
    w.action_registry.action("model.edit.scenarios").trigger()
    assert isinstance(w._scenarios_dialog, ScenariosDialog)
    w.close()
