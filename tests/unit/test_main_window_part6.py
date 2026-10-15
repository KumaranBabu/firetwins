"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 6 of 6)."""


from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

def _make_window():
    from pyfds.gui.main_window import MainWindow
    from pyfds.api import FdsApi
    return MainWindow(FdsApi())


def test_new_scenario_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"name": "low_hrr", "description": "500kW case"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)
    window._on_new_scenario()

    assert window.api.scenarios.get("low_hrr") is not None

    def top_level_labels():
        return window.explorer.category_labels()

    assert "Scenarios (1)" in top_level_labels()
    window.close()

def test_clone_scenario_via_dialog(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.scenarios.create("low_hrr")

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"base_name": "low_hrr", "new_name": "low_hrr_clone"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)
    window._on_clone_scenario()

    assert window.api.scenarios.get("low_hrr_clone") is not None
    window.close()

def test_clone_scenario_with_no_scenarios_shows_info(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_clone_scenario()

    assert shown.get("info") is True
    window.close()

def test_apply_scenario_dialog_applies_by_name(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
    window.api.scenarios.create("low_hrr")
    window.api.scenarios.set_override("low_hrr", obst, "x_max", 3.0)

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("low_hrr", True))

    window._on_apply_scenario_dialog()

    assert obst.x_max == 3.0
    assert window.api.scenarios.active == "low_hrr"
    window.api.scenarios.reset()
    window.close()

def test_apply_scenario_already_active_shows_critical(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.scenarios.create("a")
    window.api.scenarios.create("b")
    window.api.scenarios.apply("a")

    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "critical", lambda *a, **k: shown.setdefault("crit", True))

    window._on_apply_scenario("b")

    assert shown.get("crit") is True
    window.api.scenarios.reset()
    window.close()

def test_reset_scenario_restores_values(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
    window.api.scenarios.create("low_hrr")
    window.api.scenarios.set_override("low_hrr", obst, "x_max", 3.0)
    window.api.scenarios.apply("low_hrr")

    window._on_reset_scenario()

    assert obst.x_max == 1.0
    assert window.api.scenarios.active is None
    window.close()

def test_reset_scenario_with_none_active_shows_info(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_reset_scenario()

    assert shown.get("info") is True
    window.close()

def test_set_scenario_override_via_context_menu_flow(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
    window.api.scenarios.create("low_hrr")

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"scenario": "low_hrr", "field_name": "x_max", "value": "3.0"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)
    window._on_set_scenario_override(obst)

    window.api.scenarios.apply("low_hrr")
    assert obst.x_max == pytest.approx(3.0)   # coerced to float, not left as the string "3.0"
    window.api.scenarios.reset()
    window.close()

def test_export_scenarios_writes_folder(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
    window.api.scenarios.create("low_hrr")

    out_dir = str(tmp_path / "scenario_export")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: out_dir)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_export_scenarios()

    import os
    assert os.path.exists(os.path.join(out_dir, "low_hrr", "low_hrr.fds"))
    window.close()

def test_scenario_context_menu_has_apply_clone_override_delete():
    window = _make_window()
    scenario = window.api.scenarios.create("low_hrr")

    menu = window._build_entity_context_menu("scenarios", scenario)

    texts = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
    assert any("Apply" in t for t in texts)
    assert any("Clone" in t for t in texts)
    assert any("Set Override" in t for t in texts)
    assert any("Delete" in t for t in texts)
    # Rename/Disable are unsafe for dict-keyed dataclass entities — must not appear.
    assert not any("Rename" in t for t in texts)
    window.close()

def test_delete_selected_scenario_via_generic_delete_path(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.scenarios.create("low_hrr")
    window.explorer.refresh()
    window.explorer.select_entity("scenarios", window.api.scenarios.get("low_hrr"))
    monkeypatch.setattr(main_window_mod.QMessageBox, "question", lambda *a, **k: main_window_mod.QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.scenarios.get("low_hrr") is None
    window.close()

def test_define_floor_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"name": "Ground", "z_min": 0.0, "z_max": 3.0, "description": "ground floor"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)
    window._on_define_floor()

    assert window.api.floors.get_floor("Ground") is not None

    def top_level_labels():
        return window.explorer.category_labels()

    assert "Floors (1)" in top_level_labels()
    window.close()

def test_auto_assign_floors_reports_count(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 2], name="low_obst")
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_auto_assign_floors()

    assert shown.get("info") is True
    assert window.api.floors.floor_of(window.api.obstructions.get("low_obst")).name == "Ground"
    window.close()

def test_auto_assign_floors_with_no_floors_shows_info(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_auto_assign_floors()

    assert shown.get("info") is True
    window.close()

def test_assign_to_floor_uses_tree_selection(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")
    window.explorer.refresh()
    window.explorer.select_entity("obstructions", obst)

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Ground", True))

    window._on_assign_to_floor()

    assert window.api.floors.floor_of(obst).name == "Ground"
    window.close()

def test_assign_to_floor_no_selection_shows_info(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_assign_to_floor()

    assert shown.get("info") is True
    window.close()

def test_export_then_import_floors_round_trip(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    window.api.floors.assign(obst, "Ground")

    path = str(tmp_path / "floors.json")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)
    window._on_export_floors()

    import os
    assert os.path.exists(path)

    window2 = _make_window()
    window2.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))
    window2._on_import_floors()

    assert window2.api.floors.floor_of(window2.api.obstructions.get("ground_box")).name == "Ground"
    window.close()
    window2.close()

def test_floor_context_menu_has_properties_and_delete_but_not_rename():
    window = _make_window()
    floor = window.api.floors.define_floor("Ground", 0.0, 3.0)

    menu = window._build_entity_context_menu("floors", floor)

    texts = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
    assert any("Properties" in t for t in texts)
    assert any("Delete" in t for t in texts)
    assert not any("Rename" in t for t in texts)
    window.close()

def test_delete_selected_floor_via_generic_delete_path(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    window.explorer.refresh()
    window.explorer.select_entity("floors", window.api.floors.get_floor("Ground"))
    monkeypatch.setattr(main_window_mod.QMessageBox, "question", lambda *a, **k: main_window_mod.QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.floors.get_floor("Ground") is None
    window.close()
