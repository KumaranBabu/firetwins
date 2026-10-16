"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 1 of 6)."""


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


def test_window_constructs_with_explorer_and_agent_dock():
    window = _make_window()
    assert window.explorer is not None
    assert window.agent_dock is not None
    window.close()

def test_agent_dock_reflects_whether_anthropic_is_installed():
    # Whether `anthropic` is installed varies by environment (it's an
    # optional extra) — assert whichever behavior is actually correct here
    # rather than hard-coding "not installed", which would break the moment
    # someone installs it (as happened in this env this session).
    import importlib.util

    window = _make_window()
    widget = window.agent_dock.widget()
    if importlib.util.find_spec("anthropic") is None:
        assert isinstance(widget, QLabel)
        assert "agent_anthropic" in widget.text()
    else:
        from pyfds.gui.agent_panel import AgentChatPanel
        assert isinstance(widget, AgentChatPanel)
    window.close()

def test_toolbar_reuses_the_same_menu_actions():
    from PySide6.QtWidgets import QToolBar
    from pyfds.core.viewport import CameraPreset

    window = _make_window()
    bar = window.findChild(QToolBar)
    assert bar is not None

    bar_actions = set(bar.actions())
    assert window._new_action in bar_actions
    assert window._undo_action in bar_actions
    assert window._redo_action in bar_actions
    assert window._reset_view_action in bar_actions
    assert window._camera_preset_actions[CameraPreset.ISOMETRIC] in bar_actions
    assert window._wireframe_action in bar_actions
    assert window._run_action in bar_actions
    window.close()

def test_toolbar_wireframe_button_stays_in_sync_with_menu():
    # Same QAction object in both places — toggling one toggles the other.
    window = _make_window()
    assert window._wireframe_action.isChecked() is False
    window._wireframe_action.trigger()
    assert window._wireframe_action.isChecked() is True
    window.close()

def test_viewport_degrades_to_label_under_offscreen_platform():
    # QtInteractor needs a real OpenGL-capable native window handle; Qt's
    # offscreen platform (what this whole suite runs under) can't provide
    # one on this machine — attempting construction is a native access
    # violation, not a catchable exception. MainWindow must never build the
    # real Viewport3D here, only the QLabel fallback.
    window = _make_window()
    assert isinstance(window.viewport_widget, QLabel)
    assert "offscreen" in window.viewport_widget.text()
    assert window.view_tabs.widget(0) is window.viewport_widget and window.centralWidget() is window.view_tabs
    window.close()

def test_edit_properties_via_menu_action_is_undoable(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    top = window.explorer.category_item("obstructions")  # "Obstructions (1)"
    window.explorer.setCurrentItem(top.child(0))

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"x_max": 5.0, "color": "BLUE"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_edit_properties()

    assert obst.x_max == 5.0
    assert obst.color == "BLUE"

    window.api.history.undo()
    window.api.history.undo()
    assert obst.x_max == 1.0
    window.close()

def test_edit_properties_noop_when_nothing_selected(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    called = {"dialog": False}

    class _FakeDialog:
        def __init__(self, *a, **k):
            called["dialog"] = True

        def exec(self):
            return 0

        def values(self):
            return {}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_edit_properties()

    assert called["dialog"] is False
    window.close()

def test_double_click_on_tree_item_opens_property_editor(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    top = window.explorer.category_item("obstructions")
    child = top.child(0)
    window.explorer.setCurrentItem(child)

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"color": "GREEN"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window.explorer.itemDoubleClicked.emit(child, 0)

    assert obst.color == "GREEN"
    window.close()

def test_view_menu_actions_noop_gracefully_without_real_viewport(monkeypatch):
    from pyfds.core.viewport import CameraPreset, VisibilityFlags

    window = _make_window()
    # None of these have a real Viewport3D to act on (QLabel fallback) —
    # they must not raise.
    window._on_reset_view()
    window._on_camera_preset(CameraPreset.ISOMETRIC)
    window._on_toggle_wireframe(True)
    window._on_toggle_visibility(VisibilityFlags.DEVICES, False)
    window.close()

def test_project_explorer_reacts_to_api_mutation_without_being_told():
    window = _make_window()

    def top_level_labels():
        return window.explorer.category_labels()

    assert "Meshes (0)" in top_level_labels()

    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    assert "Meshes (1)" in top_level_labels()
    window.close()

def test_undo_via_menu_action_reverts_mutation_and_tree_updates():
    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box")

    def obst_label():
        item = window.explorer.category_item("obstructions")
        return item.text(0) if item is not None else None

    assert obst_label() == "Obstructions (1)"

    window.api.history.undo()

    assert obst_label() == "Obstructions (0)"
    window.close()

def test_new_project_resets_status_bar():
    window = _make_window()
    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")
    assert "Meshes  : 1" in window.statusBar().currentMessage()

    window._on_new()

    assert "Meshes  : 0" in window.statusBar().currentMessage()
    window.close()

def test_model_menu_add_entity_creates_mesh_via_dispatcher(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"ijk": [10, 10, 5], "xb": [0, 4, 0, 4, 0, 2], "name": "m1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_add_entity("add_mesh")

    assert window.api.meshes.count() == 1
    assert window.api.meshes.get("m1") is not None
    window.close()

def test_simulation_parameters_dialog_prefills_current_values(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from pyfds.gui.editors.sim_params import SimulationParametersDialog
    monkeypatch.setattr(SimulationParametersDialog, "exec", lambda self: QDialog.Rejected)
    window = _make_window()
    window.api.project.params.t_end = 999.0
    dlg = window._on_simulation_parameters()
    assert dlg.field_widget("time", "t_end").value() == 999.0
    assert dlg.field_widget("time", "restrict_time_step").value() is True
    assert not dlg.is_dirty()
    window.close()

def test_simulation_parameters_dialog_applies_through_the_api(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from pyfds.gui.editors.sim_params import SimulationParametersDialog

    def fake_exec(self):
        self.field_widget("time", "t_end").set_value(250.0)
        self.field_widget("time", "t_begin").set_value(5.0)
        self.field_widget("time", "restrict_time_step").set_value(False)
        return QDialog.Accepted if self._apply_quietly() else QDialog.Rejected

    monkeypatch.setattr(SimulationParametersDialog, "exec", fake_exec)
    window = _make_window()
    window._on_simulation_parameters()
    assert window.api.project.params.t_end == 250.0
    assert window.api.project.params.t_begin == 5.0
    assert window.api.project.params.restrict_time_step is False
    window.close()

def test_output_menu_add_slice_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"quantity": "TEMPERATURE", "plane": "Z", "position": 1.0, "name": "slc1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_add_entity("add_slice")

    assert window.api.slices.get("slc1") is not None

    def top_level_labels():
        return window.explorer.category_labels()

    assert "Slices (1)" in top_level_labels()
    window.close()
