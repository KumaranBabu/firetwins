"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 2 of 6)."""


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


def test_hvac_menu_add_node_and_duct_appear_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeNodeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"xyz": [0, 0, 0], "ambient": True, "name": "amb1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeNodeDialog)
    window._on_add_entity("add_hvac_node")
    assert window.api.hvac_nodes.get("amb1") is not None

    class _FakeDuctDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"node_id_1": "amb1", "node_id_2": "amb1", "name": "duct1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDuctDialog)
    window._on_add_entity("add_hvac_duct")
    assert window.api.hvac_ducts.get("duct1") is not None

    def top_level_labels():
        return window.explorer.category_labels()

    labels = top_level_labels()
    assert "HVAC Nodes (1)" in labels
    assert "HVAC Ducts (1)" in labels
    window.close()

def test_init_particle_prof_menu_actions_appear_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeParticleDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"diameter": 200.0, "name": "water_droplet"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeParticleDialog)
    window._on_add_entity("add_particle_class")
    assert window.api.particles.get("water_droplet") is not None

    class _FakeInitDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"xb": [0, 2, 0, 2, 0, 2], "temperature": 25.0, "name": "init1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeInitDialog)
    window._on_add_entity("add_init")
    assert window.api.inits.get("init1") is not None

    class _FakeProfDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"quantity": "INSIDE WALL TEMPERATURE", "xyz": [1.0, 2.0, 0.0], "name": "prof1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeProfDialog)
    window._on_add_entity("add_profile")
    assert window.api.profs.get("prof1") is not None

    def top_level_labels():
        return window.explorer.category_labels()

    labels = top_level_labels()
    assert "Init Regions (1)" in labels
    assert "Particles (1)" in labels
    assert "Profiles (1)" in labels
    window.close()

def test_model_menu_add_vent_and_hole(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeVentDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"xb": [0, 1, 0, 1, 2, 2], "surf_id": "BURNER", "name": "v1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeVentDialog)
    window._on_add_entity("add_vent")
    assert window.api.vents.get("v1") is not None
    assert window.api.vents.get("v1").surface_id == "BURNER"

    class _FakeHoleDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"xb": [0, 1, 0, 1, 0, 1], "name": "h1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeHoleDialog)
    window._on_add_entity("add_hole")
    assert window.api.holes.get("h1") is not None

    window.close()

def test_devices_menu_add_device_creates_generic_sensor(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"quantity": "VISIBILITY", "xyz": [1, 1, 2], "name": "smoke01"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_add_entity("add_device")

    added = window.api.devices.get("smoke01")
    assert added is not None
    assert added.quantity == "VISIBILITY"
    window.close()

def test_model_menu_add_entity_shows_error_on_missing_required_args(monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {}  # required "ijk"/"xb" missing — dispatcher.call must raise

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)
    shown = {}
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.setdefault("called", True))

    window._on_add_entity("add_mesh")

    assert shown.get("called") is True
    assert window.api.meshes.count() == 0
    window.close()

def test_save_as_writes_fds_file(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window = _make_window()
    out_path = tmp_path / "case.fds"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out_path), ""))

    window._on_save_as()

    assert out_path.exists()
    window.close()

def test_delete_selected_removes_entity(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = _make_window()
    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    top = window.explorer.category_item("meshes")  # "Meshes (1)"
    window.explorer.setCurrentItem(top.child(0))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.meshes.count() == 0
    window.close()

def test_delete_selected_noop_when_category_row_selected():
    window = _make_window()
    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    top = window.explorer.category_item("meshes")  # category row, carries no (attr, entity) data
    window.explorer.setCurrentItem(top)

    window._on_delete_selected()

    assert window.api.meshes.count() == 1
    window.close()

def test_validate_shows_report_dialog(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window._on_validate()
    assert window.validation_panel.summary.text() != "Not validated yet."
    assert window.messages_tabs.currentWidget() is window.validation_panel
    assert not window.messages_dock.isHidden()
    window.close()

def test_auto_fix_refreshes_explorer_and_shows_report(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    shown = {}

    class _FakeDialog:
        def __init__(self, title, text, parent=None):
            shown["title"] = title

        def exec(self):
            pass

    monkeypatch.setattr(main_window_mod, "TextReportDialog", _FakeDialog)
    refreshed = []
    monkeypatch.setattr(window.explorer, "refresh", lambda: refreshed.append(1))

    window._on_auto_fix()

    assert "Auto-Fix" in shown["title"]
    assert refreshed  # auto_fix() bypasses CommandPipeline, so this must be explicit
    window.close()

def test_new_from_template_triggers_explorer_refresh_via_event(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = _make_window()
    presets = window.api.templates.list_presets()
    assert presets

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (presets[0], True))
    refreshed = []
    monkeypatch.setattr(window.explorer, "refresh", lambda: refreshed.append(1))

    window._on_new_from_template()

    # Proves TemplateManager.apply() now emits PROJECT_LOADED (it silently
    # didn't before) and the explorer's own EventBus subscription catches it.
    assert refreshed
    window.close()

def test_new_from_template_cancelled_does_nothing(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = _make_window()
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))
    refreshed = []
    monkeypatch.setattr(window.explorer, "refresh", lambda: refreshed.append(1))

    window._on_new_from_template()

    assert not refreshed
    window.close()

