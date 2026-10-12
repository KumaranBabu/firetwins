"""
Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py).

Headless via QT_QPA_PLATFORM=offscreen. Verifies the shell wires up
correctly and — crucially — that ProjectExplorer updates purely by
reacting to EventBus events, never by being told directly: a mutation
made through FdsApi (the "human path") should show up in the tree without
the tree being poked.
"""
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
    assert window.centralWidget() is window.viewport_widget
    window.close()


def test_edit_properties_via_menu_action_is_undoable(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    top = window.explorer.topLevelItem(1)  # "Obstructions (1)"
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
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    top = window.explorer.topLevelItem(1)
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
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    assert "Meshes (0)" in top_level_labels()

    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    assert "Meshes (1)" in top_level_labels()
    window.close()


def test_undo_via_menu_action_reverts_mutation_and_tree_updates():
    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box")

    def obst_label():
        for i in range(window.explorer.topLevelItemCount()):
            item = window.explorer.topLevelItem(i)
            if item.text(0).startswith("Obstructions"):
                return item.text(0)
        return None

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
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.project.params.t_end = 999.0

    seen_schema = {}

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            seen_schema["t_end_default"] = schema["properties"]["t_end"]["default"]
            seen_schema["restrict_default"] = schema["properties"]["restrict_time_step"]["default"]

        def exec(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.Rejected  # cancel — only checking prefill, not the mutation

        def values(self):
            return {}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_simulation_parameters()

    assert seen_schema["t_end_default"] == 999.0
    assert seen_schema["restrict_default"] is True
    window.close()


def test_simulation_parameters_dialog_applies_via_dispatcher(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()

    class _FakeDialog:
        def __init__(self, title, description, schema, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"t_end": 250.0, "t_begin": 5.0, "restrict_time_step": False}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeDialog)

    window._on_simulation_parameters()

    assert window.api.project.params.t_end == 250.0
    assert window.api.project.params.t_begin == 5.0
    assert window.api.project.params.restrict_time_step is False
    window.close()


def test_output_menu_add_slice_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    assert "Slices (1)" in top_level_labels()
    window.close()


def test_hvac_menu_add_node_and_duct_appear_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    labels = top_level_labels()
    assert "HVAC Nodes (1)" in labels
    assert "HVAC Ducts (1)" in labels
    window.close()


def test_init_particle_prof_menu_actions_appear_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
            return {"quantity": "TEMPERATURE", "xyz": [1.0, 2.0, 0.0], "name": "prof1"}

    monkeypatch.setattr(main_window_mod, "SchemaFormDialog", _FakeProfDialog)
    window._on_add_entity("add_profile")
    assert window.api.profs.get("prof1") is not None

    def top_level_labels():
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    labels = top_level_labels()
    assert "Init Regions (1)" in labels
    assert "Particle Classes (1)" in labels
    assert "Profiles (1)" in labels
    window.close()


def test_model_menu_add_vent_and_hole(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

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


# ── Delete selected ─────────────────────────────────────────────────────────

def test_delete_selected_removes_entity(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = _make_window()
    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    top = window.explorer.topLevelItem(0)  # "Meshes (1)"
    window.explorer.setCurrentItem(top.child(0))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.meshes.count() == 0
    window.close()


def test_delete_selected_noop_when_category_row_selected():
    window = _make_window()
    window.api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    top = window.explorer.topLevelItem(0)  # category row, carries no (attr, entity) data
    window.explorer.setCurrentItem(top)

    window._on_delete_selected()

    assert window.api.meshes.count() == 1
    window.close()


# ── Validate / Auto-fix ──────────────────────────────────────────────────────

def test_validate_shows_report_dialog(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    shown = {}

    class _FakeDialog:
        def __init__(self, title, text, parent=None):
            shown["title"] = title

        def exec(self):
            shown["exec_called"] = True

    monkeypatch.setattr(main_window_mod, "TextReportDialog", _FakeDialog)

    window._on_validate()

    assert shown.get("exec_called") is True
    assert "Validation" in shown["title"]
    window.close()


def test_auto_fix_refreshes_explorer_and_shows_report(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

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


# ── New from template ────────────────────────────────────────────────────────

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


# ── Run simulation ───────────────────────────────────────────────────────────

def test_run_simulation_success_shows_completion_dialog(monkeypatch, tmp_path):
    import concurrent.futures
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: "/usr/bin/fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, True))

    fut = concurrent.futures.Future()
    fut.set_result(OrchestratorResult(success=True, wall_time_seconds=1.2, output_dir=str(tmp_path)))
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: fut)
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_run_simulation()
    window._poll_run_future()  # future is already done — bypass the QTimer wait

    assert shown.get("info") is True
    assert window._run_action.isEnabled()
    window.close()


def test_run_simulation_failure_shows_warning(monkeypatch, tmp_path):
    import concurrent.futures
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: "/usr/bin/fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, True))

    fut = concurrent.futures.Future()
    fut.set_result(OrchestratorResult(success=False, error="fds binary not found"))
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: fut)
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "warning", lambda *a, **k: shown.setdefault("warn", True))

    window._on_run_simulation()
    window._poll_run_future()

    assert shown.get("warn") is True
    window.close()


def test_run_simulation_prompts_for_binary_when_not_found_and_cancel_aborts(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: None)
    # Force the "no bundled solver either" branch — this dev machine actually
    # has fds_smv/ checked out, so without this the real bundled path would
    # resolve and the file-dialog prompt (what this test exercises) would
    # never fire.
    monkeypatch.setattr(main_window_mod, "_default_fds_binary", lambda: None)
    monkeypatch.setattr(main_window_mod, "_default_smv_binary", lambda: None)
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    called = {"run_async": False}
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: called.__setitem__("run_async", True))

    window._on_run_simulation()

    assert called["run_async"] is False
    window.close()


def test_run_simulation_configures_binary_when_user_provides_path(monkeypatch, tmp_path):
    import concurrent.futures
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    fake_fds = str(tmp_path / "fds.exe")
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: None)
    monkeypatch.setattr(main_window_mod, "_default_fds_binary", lambda: None)
    monkeypatch.setattr(main_window_mod, "_default_smv_binary", lambda: None)
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (fake_fds, ""))
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, True))

    fut = concurrent.futures.Future()
    fut.set_result(OrchestratorResult(success=True, wall_time_seconds=0.1, output_dir=str(tmp_path)))
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: fut)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_run_simulation()
    window._poll_run_future()

    assert window.api.config.fds_binary == fake_fds
    window.close()


def test_run_simulation_uses_bundled_solver_without_prompting(monkeypatch, tmp_path):
    import concurrent.futures
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    bundled_fds = str(tmp_path / "bundled_fds.exe")
    bundled_smv = str(tmp_path / "bundled_smokeview.exe")
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: None)
    monkeypatch.setattr(main_window_mod, "_default_fds_binary", lambda: bundled_fds)
    monkeypatch.setattr(main_window_mod, "_default_smv_binary", lambda: bundled_smv)

    prompted = {"called": False}
    monkeypatch.setattr(
        main_window_mod.QFileDialog, "getOpenFileName",
        lambda *a, **k: prompted.__setitem__("called", True) or ("", ""),
    )
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, True))

    fut = concurrent.futures.Future()
    fut.set_result(OrchestratorResult(success=True, wall_time_seconds=0.1, output_dir=str(tmp_path)))
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: fut)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_run_simulation()
    window._poll_run_future()

    assert prompted["called"] is False  # bundled solver found — no browse dialog needed
    assert window.api.config.fds_binary == bundled_fds
    assert window.api.config.smv_binary == bundled_smv
    window.close()


def test_run_simulation_passes_num_processes_through(monkeypatch, tmp_path):
    import concurrent.futures
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: "/usr/bin/fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (4, True))

    fut = concurrent.futures.Future()
    fut.set_result(OrchestratorResult(success=True, wall_time_seconds=0.1, output_dir=str(tmp_path)))
    received = {}
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: received.update(k) or fut)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_run_simulation()
    window._poll_run_future()

    assert received["num_processes"] == 4
    window.close()


def test_run_simulation_cancelled_at_process_count_does_not_run(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: "/usr/bin/fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, False))

    called = {"run_async": False}
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: called.__setitem__("run_async", True))

    window._on_run_simulation()

    assert called["run_async"] is False
    window.close()


# ── Tree right-click context menu ────────────────────────────────────────────

def test_right_click_on_entity_row_selects_it_and_requests_context_menu():
    # Standalone ProjectExplorer, not through MainWindow: MainWindow.__init__
    # connects this same signal to _on_explorer_context_menu, which pops a
    # real (blocking, unmockable-in-PySide6) QMenu.exec() — constructing the
    # explorer on its own means only this test's lambda is connected, so
    # emitting the signal here carries zero risk of an accidental real popup.
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    explorer = ProjectExplorer(api)

    received = []
    explorer.entity_context_menu_requested.connect(lambda: received.append(1))

    top = explorer.topLevelItem(1)  # "Obstructions (1)"
    child = top.child(0)
    rect = explorer.visualItemRect(child)
    explorer._on_context_menu_requested(rect.center())

    assert received == [1]
    assert explorer.selected() == ("obstructions", api.obstructions.get("box1"))
    explorer.shutdown()


def test_right_click_on_empty_space_does_not_request_context_menu():
    from PySide6.QtCore import QPoint
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    explorer = ProjectExplorer(FdsApi())
    received = []
    explorer.entity_context_menu_requested.connect(lambda: received.append(1))

    explorer._on_context_menu_requested(QPoint(-5, -5))  # off the tree entirely

    assert received == []
    explorer.shutdown()


def test_context_menu_contains_properties_rename_toggle_delete():
    # Tests menu *construction* only — never calls .exec(), which is a real
    # blocking modal call in PySide6 that can't be safely monkeypatched
    # (confirmed empirically: patching QMenu.exec still hung the test
    # process). _on_explorer_context_menu's one-line .exec() call itself is
    # intentionally left untested, same as Viewport3D's thin widget wrapper.
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    menu = window._build_entity_context_menu("obstructions", obst)

    # QAction.text() keeps the "&" mnemonic character (e.g. "Re&name...") —
    # strip it before substring-matching.
    texts = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
    assert any("Properties" in t for t in texts)
    assert any("Rename" in t for t in texts)
    assert any("Disable Object" in t for t in texts)
    assert any("Delete" in t for t in texts)
    window.close()


def test_context_menu_toggle_label_reflects_disabled_state():
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    obst.enabled = False

    menu = window._build_entity_context_menu("obstructions", obst)

    texts = [a.text() for a in menu.actions()]
    assert any("Enable Object" in t for t in texts)

    window.close()


def test_rename_entity_via_dialog_is_undoable(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    monkeypatch.setattr("pyfds.gui.main_window.QInputDialog.getText", lambda *a, **k: ("renamed", True))

    window._on_rename_entity(obst)

    assert obst.name == "renamed"
    window.api.history.undo()
    assert obst.name == "box1"
    window.close()


def test_rename_entity_cancelled_does_nothing(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    monkeypatch.setattr("pyfds.gui.main_window.QInputDialog.getText", lambda *a, **k: ("ignored", False))

    window._on_rename_entity(obst)

    assert obst.name == "box1"
    window.close()


def test_toggle_enabled_disables_and_reenables_and_is_undoable():
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    assert obst.enabled is True

    window._on_toggle_enabled(obst)
    assert obst.enabled is False

    window.api.history.undo()
    assert obst.enabled is True
    window.close()


def test_disabled_entity_shown_dimmed_in_tree():
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    window._on_toggle_enabled(obst)

    top = window.explorer.topLevelItem(1)
    child = top.child(0)
    assert "(disabled)" in child.text(0)
    window.close()


def test_viewport_scene_reflects_disabled_entities_after_toggle():
    from pyfds.gui.viewport_scene import build_scene

    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    assert any(s.label == "box1" for s in build_scene(window.api))

    window._on_toggle_enabled(obst)
    assert not any(s.label == "box1" for s in build_scene(window.api))
    window.close()


# ── Results menu ──────────────────────────────────────────────────────────────

def _write_fake_devc_csv(out_dir, chid="room_fire"):
    path = out_dir / f"{chid}_devc.csv"
    path.write_text(
        "Time,tc_center,tc_ceiling,hrr_total\n"
        "s,C,C,kW\n"
        "0.0,20.0,20.0,0.0\n"
        "1.0,21.5,20.5,10.0\n"
        "2.0,24.0,21.0,50.0\n"
    )
    return str(path)


def test_open_smokeview_results_launches_non_blocking(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    smv_path = str(tmp_path / "case.smv")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (smv_path, ""))

    called = {}
    monkeypatch.setattr(window.api.smokeview, "open", lambda path, **k: called.update(path=path, **k))

    window._on_open_smokeview_results()

    assert called == {"path": smv_path, "blocking": False}
    window.close()


def test_open_smokeview_results_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    called = {"opened": False}
    monkeypatch.setattr(window.api.smokeview, "open", lambda *a, **k: called.__setitem__("opened", True))

    window._on_open_smokeview_results()

    assert called["opened"] is False
    window.close()


def _patch_export_animation(monkeypatch, window, *, smv="case.smv", out="a.mp4",
                            accepted=True, values=None, render=None):
    import pyfds.gui.main_window as mod

    monkeypatch.setattr(mod.QFileDialog, "getOpenFileName", lambda *a, **k: (smv, ""))
    monkeypatch.setattr(mod.QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))

    class _FakeDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return mod.QDialog.Accepted if accepted else mod.QDialog.Rejected

        def values(self):
            return values or {"quantity": "TEMPERATURE", "fps": 10,
                              "start_time": 0.0, "end_time": 0.0}

    monkeypatch.setattr(mod, "SchemaFormDialog", _FakeDialog)
    shown = {}
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(mod.QMessageBox, kind,
                            lambda *a, _k=kind, **k: shown.setdefault(_k, a))
    calls = []
    monkeypatch.setattr(window.api.smokeview, "render_movie",
                        render or (lambda *a, **k: calls.append((a, k)) or 0))
    return calls, shown


def test_export_animation_success(monkeypatch):
    window = _make_window()
    calls, shown = _patch_export_animation(
        monkeypatch, window,
        values={"quantity": "VISIBILITY", "fps": 24, "start_time": 5.0, "end_time": 0.0},
    )
    window._on_export_animation()
    assert calls == [(("case.smv", "a.mp4", "VISIBILITY"),
                      {"fps": 24, "start_time": 5.0, "end_time": None})]
    assert "information" in shown
    window.close()


def test_export_animation_zero_times_mean_full_range(monkeypatch):
    window = _make_window()
    calls, _ = _patch_export_animation(monkeypatch, window)
    window._on_export_animation()
    assert calls[0][1]["start_time"] is None and calls[0][1]["end_time"] is None
    window.close()


@pytest.mark.parametrize("cancel", ["smv", "dialog", "out"])
def test_export_animation_cancel_does_not_render(monkeypatch, cancel):
    window = _make_window()
    kwargs = {"smv": "" if cancel == "smv" else "case.smv",
              "out": "" if cancel == "out" else "a.mp4",
              "accepted": cancel != "dialog"}
    calls, _ = _patch_export_animation(monkeypatch, window, **kwargs)
    window._on_export_animation()
    assert calls == []
    window.close()


def test_export_animation_nonzero_return_warns(monkeypatch):
    window = _make_window()
    _, shown = _patch_export_animation(monkeypatch, window, render=lambda *a, **k: 3)
    window._on_export_animation()
    assert "warning" in shown and "information" not in shown
    window.close()


def test_export_animation_exception_shows_critical(monkeypatch):
    window = _make_window()

    def _boom(*a, **k):
        raise RuntimeError("smokeview not found")

    _, shown = _patch_export_animation(monkeypatch, window, render=_boom)
    window._on_export_animation()
    assert "critical" in shown
    window.close()


def test_view_time_history_shows_figure_dialog(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.new(chid="room_fire")
    _write_fake_devc_csv(tmp_path, chid="room_fire")

    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    shown = {}

    class _FakeFigureDialog:
        def __init__(self, title, figure, parent=None):
            shown["title"] = title
            shown["figure"] = figure

        def exec(self):
            shown["exec_called"] = True

    monkeypatch.setattr(main_window_mod, "_import_figure_dialog", lambda: _FakeFigureDialog)

    window._on_view_time_history()

    assert shown.get("exec_called") is True
    assert shown["title"] == "Device Time History"
    window.close()


def test_view_time_history_no_devices_shows_info(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.new(chid="empty_case")
    # no devc.csv written — build_index() finds nothing

    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_view_time_history()

    assert shown.get("info") is True
    window.close()


def test_archive_and_restore_results_round_trip(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.new(chid="room_fire")
    _write_fake_devc_csv(tmp_path, chid="room_fire")
    archive_path = str(tmp_path / "archive.json")

    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (archive_path, ""))
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_archive_results()

    import os
    assert os.path.exists(archive_path)

    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (archive_path, ""))
    shown = {}

    class _FakeReportDialog:
        def __init__(self, title, text, parent=None):
            shown["title"] = title
            shown["text"] = text

        def exec(self):
            shown["exec_called"] = True

    monkeypatch.setattr(main_window_mod, "TextReportDialog", _FakeReportDialog)

    window._on_restore_results()

    assert shown.get("exec_called") is True
    assert "room_fire" in shown["text"]
    window.close()


def test_restore_results_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    called = {"restored": False}
    monkeypatch.setattr(window.api.results, "restore", lambda *a, **k: called.__setitem__("restored", True))

    window._on_restore_results()

    assert called["restored"] is False
    window.close()


# ── 3D viewport click-to-select ──────────────────────────────────────────────

def test_select_entity_sets_current_tree_item():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    picked = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    explorer = ProjectExplorer(api)

    explorer.select_entity("obstructions", picked)

    assert explorer.selected() == ("obstructions", picked)
    explorer.shutdown()


def test_select_entity_noop_for_entity_not_in_tree():
    from pyfds.api import FdsApi
    from pyfds.domain.model import Obstruction
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    explorer = ProjectExplorer(api)

    stray = Obstruction(name="not_in_project")
    explorer.select_entity("obstructions", stray)  # must not raise

    assert explorer.selected() is None
    explorer.shutdown()


def test_selected_entities_returns_all_multi_selected_rows():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    a = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    explorer = ProjectExplorer(api)

    explorer.select_entities([("obstructions", a), ("obstructions", b)])

    pairs = explorer.selected_entities()
    assert len(pairs) == 2
    assert ("obstructions", a) in pairs
    assert ("obstructions", b) in pairs
    explorer.shutdown()


def test_selected_entities_empty_when_nothing_selected():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    explorer = ProjectExplorer(api)

    assert explorer.selected_entities() == []
    explorer.shutdown()


def test_select_entities_leaves_prior_selection_when_nothing_matches():
    from pyfds.api import FdsApi
    from pyfds.domain.model import Obstruction
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    kept = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    explorer = ProjectExplorer(api)
    explorer.select_entity("obstructions", kept)

    stray = Obstruction(name="not_in_project")
    explorer.select_entities([("obstructions", stray)])

    assert explorer.selected() == ("obstructions", kept)
    explorer.shutdown()


def test_select_entities_replaces_prior_selection():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    a = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    explorer = ProjectExplorer(api)
    explorer.select_entity("obstructions", a)

    explorer.select_entities([("obstructions", b)])

    assert explorer.selected_entities() == [("obstructions", b)]
    explorer.shutdown()


def test_viewport_entity_picked_not_wired_when_fallback_label():
    # Under offscreen (this whole suite), viewport_widget is the QLabel
    # fallback with no entity_picked signal — MainWindow.__init__ must guard
    # this with hasattr rather than assuming a real Viewport3D.
    window = _make_window()
    assert not hasattr(window.viewport_widget, "entity_picked")
    window.close()


def test_viewport_selection_changed_not_wired_when_fallback_label():
    # Same fallback-label guard as entity_picked, above — Viewport3D itself
    # can't be constructed under the offscreen platform this suite runs on
    # (native GL access violation), so its multi-pick selection_changed
    # signal is likewise never present to connect to under test.
    window = _make_window()
    assert not hasattr(window.viewport_widget, "selection_changed")
    window.close()


# ── Draw-box tool ─────────────────────────────────────────────────────────────

def test_draw_menu_actions_registered_and_checkable():
    window = _make_window()
    # Phase 1 expanded the Draw menu from 3 basic tools to 14 primitives/
    # architectural elements; the original 3 must still be present.
    assert {"add_obstruction", "add_vent", "add_hole"} <= set(window._draw_actions.keys())
    for action in window._draw_actions.values():
        assert action.isCheckable()
        assert action.isChecked() is False
    window.close()


def test_set_draw_mode_noop_when_fallback_label_but_still_updates_status():
    window = _make_window()
    window._on_set_draw_mode("add_obstruction")  # must not raise without a real Viewport3D
    assert "add_obstruction" in window.statusBar().currentMessage()
    window.close()


def test_cancel_draw_mode_unchecks_all_draw_actions():
    window = _make_window()
    window._draw_actions["add_vent"].setChecked(True)

    window._on_cancel_draw_mode()

    assert all(not a.isChecked() for a in window._draw_actions.values())
    window.close()


def test_box_footprint_picked_creates_entity_via_dispatcher(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(
        main_window_mod.QInputDialog, "getDouble",
        lambda self_or_parent, title, label, default, lo, hi, dec: (
            (0.0, True) if "min" in label else (3.0, True)
        ),
    )

    window._on_box_footprint_picked("add_obstruction", 0.0, 2.0, 0.0, 3.0)

    obsts = window.api.obstructions.all()
    assert len(obsts) == 1
    o = obsts[0]
    assert (o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max) == (0.0, 2.0, 0.0, 3.0, 0.0, 3.0)
    window.close()


def test_box_footprint_picked_dispatches_to_correct_tool_for_vent_and_hole(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(
        main_window_mod.QInputDialog, "getDouble",
        lambda self_or_parent, title, label, default, lo, hi, dec: (
            (0.0, True) if "min" in label else (2.0, True)
        ),
    )

    window._on_box_footprint_picked("add_vent", 0.0, 1.0, 0.0, 1.0)
    window._on_box_footprint_picked("add_hole", 2.0, 3.0, 0.0, 1.0)

    assert window.api.vents.count() == 1
    assert window.api.holes.count() == 1
    window.close()


def test_box_footprint_picked_cancelled_at_z_min_creates_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(
        main_window_mod.QInputDialog, "getDouble",
        lambda self_or_parent, title, label, default, lo, hi, dec: (0.0, False),
    )

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window.api.obstructions.count() == 0
    window.close()


def test_box_footprint_picked_cancelled_at_z_max_creates_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()

    def fake_get_double(self_or_parent, title, label, default, lo, hi, dec):
        return (0.0, True) if "min" in label else (0.0, False)

    monkeypatch.setattr(main_window_mod.QInputDialog, "getDouble", fake_get_double)

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window.api.obstructions.count() == 0
    window.close()


def test_box_footprint_picked_unchecks_draw_actions_even_when_cancelled(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window._draw_actions["add_obstruction"].setChecked(True)
    monkeypatch.setattr(main_window_mod.QInputDialog, "getDouble", lambda *a, **k: (0.0, False))

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window._draw_actions["add_obstruction"].isChecked() is False
    window.close()


# ── Quick wins: Find ─────────────────────────────────────────────────────────

def test_find_entity_by_name_matches_case_insensitive_substring():
    from PySide6.QtCore import Qt
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="Burner_Box")
    explorer = ProjectExplorer(api)

    match = explorer.find_entity_by_name("burner")

    assert match is not None
    assert match.data(0, Qt.UserRole)[1].name == "Burner_Box"
    explorer.shutdown()


def test_find_entity_by_name_no_match_returns_none():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import ProjectExplorer

    api = FdsApi()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    explorer = ProjectExplorer(api)

    assert explorer.find_entity_by_name("nope") is None
    explorer.shutdown()


def test_on_find_selects_matching_row(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="target_box")
    monkeypatch.setattr(main_window_mod.QInputDialog, "getText", lambda *a, **k: ("target", True))

    window._on_find()

    assert window.explorer.selected()[1].name == "target_box"
    window.close()


def test_on_find_shows_message_when_nothing_matches(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getText", lambda *a, **k: ("nope", True))
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_find()

    assert shown.get("info") is True
    window.close()


# ── Quick wins: Convert to Blocks ────────────────────────────────────────────

def test_convert_to_blocks_calls_voxelize_and_reports_count(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    stl_path = str(tmp_path / "shape.stl")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (stl_path, ""))
    monkeypatch.setattr(window.api.geom, "voxelize", lambda path: [object(), object()])
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_convert_to_blocks()

    assert shown.get("info") is True
    window.close()


def test_convert_to_blocks_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    called = {"voxelize": False}
    monkeypatch.setattr(window.api.geom, "voxelize", lambda path: called.__setitem__("voxelize", True))

    window._on_convert_to_blocks()

    assert called["voxelize"] is False
    window.close()


def test_convert_to_blocks_error_shows_critical(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "x.stl"), ""))

    def _raise(path):
        raise RuntimeError("No meshes in project — add a mesh first.")
    monkeypatch.setattr(window.api.geom, "voxelize", _raise)
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "critical", lambda *a, **k: shown.setdefault("crit", True))

    window._on_convert_to_blocks()

    assert shown.get("crit") is True
    window.close()


# ── Quick wins: Export database ──────────────────────────────────────────────

def test_export_db_materials_writes_file(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    out_path = str(tmp_path / "materials.json")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (out_path, ""))
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_export_db("materials")

    import os
    assert os.path.exists(out_path)
    window.close()


def test_export_db_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    called = {"export": False}
    monkeypatch.setattr(window.api.engineering, "export_surfaces", lambda p: called.__setitem__("export", True))

    window._on_export_db("surfaces")

    assert called["export"] is False
    window.close()


def test_export_db_all_writes_folder(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    out_dir = str(tmp_path / "db_export")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: out_dir)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_export_db_all()

    import os
    assert os.path.isdir(out_dir)
    assert len(os.listdir(out_dir)) > 0
    window.close()


# ── Quick wins: Resume simulation ────────────────────────────────────────────

def test_resume_simulation_success_shows_completion_dialog(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    fds_path = str(tmp_path / "case.fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (fds_path, ""))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (2, True))

    received = {}
    monkeypatch.setattr(
        window.api.execution, "resume_from_checkpoint",
        lambda path, **k: received.update(path=path, **k) or OrchestratorResult(
            success=True, wall_time_seconds=5.0, output_dir=str(tmp_path)
        ),
    )
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_resume_simulation()
    window._poll_resume_future()

    assert shown.get("info") is True
    assert received["path"] == fds_path
    assert received["num_processes"] == 2
    window.close()


def test_resume_simulation_failure_shows_warning(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod
    from pyfds.automation.orchestrator import OrchestratorResult

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "c.fds"), ""))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, True))
    monkeypatch.setattr(
        window.api.execution, "resume_from_checkpoint",
        lambda path, **k: OrchestratorResult(success=False, error="checkpoint missing"),
    )
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "warning", lambda *a, **k: shown.setdefault("warn", True))

    window._on_resume_simulation()
    window._poll_resume_future()

    assert shown.get("warn") is True
    window.close()


def test_resume_simulation_cancelled_at_file_picker_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    called = {"resume": False}
    monkeypatch.setattr(window.api.execution, "resume_from_checkpoint", lambda *a, **k: called.__setitem__("resume", True))

    window._on_resume_simulation()

    assert called["resume"] is False
    window.close()


def test_resume_simulation_cancelled_at_process_count_does_nothing(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "c.fds"), ""))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, False))
    called = {"resume": False}
    monkeypatch.setattr(window.api.execution, "resume_from_checkpoint", lambda *a, **k: called.__setitem__("resume", True))

    window._on_resume_simulation()

    assert called["resume"] is False
    window.close()


# ── Quick wins: OpenMP environment ───────────────────────────────────────────

def test_openmp_environment_sets_thread_count_and_is_undoable(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (4, True))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads == 4
    window.api.history.undo()
    assert window.api.project.misc.openmp_threads is None
    window.close()


def test_openmp_environment_zero_means_auto_unset(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.project.misc.openmp_threads = 8
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (0, True))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads is None
    window.close()


def test_openmp_environment_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (4, False))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads is None
    window.close()


# ── Quick wins: Open Results Folder ──────────────────────────────────────────

def test_open_results_folder_opens_url(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    opened = {}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.setdefault("url", url))

    window._on_open_results_folder()

    assert "url" in opened
    window.close()


def test_open_results_folder_cancelled_does_nothing(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    opened = {"called": False}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.__setitem__("called", True))

    window._on_open_results_folder()

    assert opened["called"] is False
    window.close()


# ── Quick wins: Help menu ────────────────────────────────────────────────────

def test_open_doc_opens_existing_file(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    doc = tmp_path / "guide.pdf"
    doc.write_text("fake pdf")
    opened = {}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.setdefault("url", url))

    window._on_open_doc(doc)

    assert "url" in opened
    window.close()


def test_open_doc_missing_file_shows_message(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    missing = tmp_path / "does_not_exist.pdf"
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))
    opened = {"called": False}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.__setitem__("called", True))

    window._on_open_doc(missing)

    assert shown.get("info") is True
    assert opened["called"] is False
    window.close()


def test_about_dialog_does_not_raise(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QMessageBox, "about", lambda *a, **k: None)

    window._on_about()  # must not raise
    window.close()


# ── Scenarios ────────────────────────────────────────────────────────────────

def test_new_scenario_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    assert "Scenarios (1)" in top_level_labels()
    window.close()


def test_clone_scenario_via_dialog(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_clone_scenario()

    assert shown.get("info") is True
    window.close()


def test_apply_scenario_dialog_applies_by_name(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_reset_scenario()

    assert shown.get("info") is True
    window.close()


def test_set_scenario_override_via_context_menu_flow(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.scenarios.create("low_hrr")
    window.explorer.refresh()
    window.explorer.select_entity("scenarios", window.api.scenarios.get("low_hrr"))
    monkeypatch.setattr(main_window_mod.QMessageBox, "question", lambda *a, **k: main_window_mod.QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.scenarios.get("low_hrr") is None
    window.close()


# ── Floors ───────────────────────────────────────────────────────────────────

def test_define_floor_appears_in_explorer(monkeypatch):
    from PySide6.QtWidgets import QDialog
    import pyfds.gui.main_window as main_window_mod

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
        return [window.explorer.topLevelItem(i).text(0) for i in range(window.explorer.topLevelItemCount())]

    assert "Floors (1)" in top_level_labels()
    window.close()


def test_auto_assign_floors_reports_count(monkeypatch):
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_auto_assign_floors()

    assert shown.get("info") is True
    window.close()


def test_assign_to_floor_uses_tree_selection(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_assign_to_floor()

    assert shown.get("info") is True
    window.close()


def test_export_then_import_floors_round_trip(monkeypatch, tmp_path):
    import pyfds.gui.main_window as main_window_mod

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
    import pyfds.gui.main_window as main_window_mod

    window = _make_window()
    window.api.floors.define_floor("Ground", 0.0, 3.0)
    window.explorer.refresh()
    window.explorer.select_entity("floors", window.api.floors.get_floor("Ground"))
    monkeypatch.setattr(main_window_mod.QMessageBox, "question", lambda *a, **k: main_window_mod.QMessageBox.Yes)

    window._on_delete_selected()

    assert window.api.floors.get_floor("Ground") is None
    window.close()
