"""Automated regression coverage for the Phase 2 menu handlers (both wiring (part 1 of 4)."""


from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from tests.mw_proxy import main_window_mod as mw  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

def _make_window():
    from pyfds.gui.main_window import MainWindow
    from pyfds.api import FdsApi
    return MainWindow(FdsApi())

def _select_first_obstruction(window):
    top = window.explorer.topLevelItem(1)  # "Obstructions (N)"
    child = top.child(0)
    window.explorer.setCurrentItem(child)

class _FakeDialog:
    """Generic SchemaFormDialog stand-in — records the schema it was built
    with (so tests can assert on pre-filled defaults) and returns a fixed
    values() dict on exec()."""

    last_schema = None

    def __init__(self, title, description, schema, parent=None):
        self.title = title
        self.schema = schema
        _FakeDialog.last_schema = schema

    def exec(self):
        return QDialog.Accepted

    def values(self):
        return self._values

    _values: dict = {}

def _fake_dialog_returning(values: dict):
    class _D(_FakeDialog):
        _values = values
    return _D


def test_save_falls_back_to_save_as_when_no_path(monkeypatch):
    window = _make_window()
    assert window._current_project_path is None
    called = {"save_as": False}
    monkeypatch.setattr(window, "_on_save_as", lambda: called.__setitem__("save_as", True))
    window._on_save()
    assert called["save_as"] is True
    window.close()

def test_save_writes_in_place_when_path_known(monkeypatch):
    window = _make_window()
    window._current_project_path = "existing.fds"
    recorded = {}
    monkeypatch.setattr(window.api, "save", lambda path: recorded.setdefault("path", path))

    def _fail(*a, **k):
        raise AssertionError("Save As dialog should not appear when a path is already known")
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", _fail)

    window._on_save()
    assert recorded["path"] == "existing.fds"
    window.close()

def test_recent_projects_round_trip(monkeypatch, tmp_path):
    window = _make_window()
    project_file = tmp_path / "myproject.fds"
    project_file.write_text("dummy")

    window._add_recent_path(str(project_file))
    labels = [a.text() for a in window._recent_submenu.actions()]
    assert "myproject.fds" in labels

    recorded = {}
    monkeypatch.setattr(window.api, "load", lambda p: recorded.setdefault("path", p))
    window._on_open_recent(str(project_file))
    assert recorded["path"] == str(project_file)
    assert window._current_project_path == str(project_file)
    window.close()

def test_recent_projects_stale_path_is_pruned(monkeypatch, tmp_path):
    window = _make_window()
    missing = str(tmp_path / "gone.fds")
    window._add_recent_path(missing)

    warned = {"called": False}
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a, **k: warned.__setitem__("called", True))
    window._on_open_recent(missing)

    assert warned["called"] is True
    assert missing not in window._recent_paths()
    window.close()

def test_export_as_fds_appends_extension(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a, **k: ("myexport", ""))
    recorded = {}
    monkeypatch.setattr(window.api, "save", lambda path: recorded.setdefault("path", path))
    window._on_export_as_fds()
    assert recorded["path"] == "myexport.fds"
    window.close()

def test_import_stl_calls_geom_load_stl(monkeypatch, tmp_path):
    window = _make_window()
    stl_path = str(tmp_path / "shell.stl")
    monkeypatch.setattr(mw.QFileDialog, "getOpenFileName", lambda *a, **k: (stl_path, ""))
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("CONCRETE", True))
    recorded = {}
    monkeypatch.setattr(window.api.geom, "load_stl", lambda path, surf_id=None: recorded.update(path=path, surf_id=surf_id))
    window._on_import_stl()
    assert recorded == {"path": stl_path, "surf_id": "CONCRETE"}
    window.close()

def test_project_settings_updates_chid_and_title_undoably(monkeypatch):
    window = _make_window()
    original_chid = window.api.project.chid
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"chid": "case_42", "title": "My Room"}))
    window._on_project_settings()
    assert window.api.project.chid == "case_42"
    assert window.api.project.title == "My Room"
    window.api.history.undo()
    window.api.history.undo()
    assert window.api.project.chid == original_chid
    window.close()

def test_preferences_updates_config_and_shared_by_both_menus(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"fds_binary": "/opt/fds", "default_mpi_processes": 3}))
    window._on_preferences()
    assert window.api.config.get("fds_binary") == "/opt/fds"
    assert window.api.config.get("default_mpi_processes") == 3
    window.close()

def test_copy_paste_creates_independent_entity(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    _select_first_obstruction(window)

    assert window._paste_action.isEnabled() is False
    window._on_copy()
    assert window._paste_action.isEnabled() is True

    before = len(window.api.obstructions.all())
    window._on_paste()
    after = window.api.obstructions.all()
    assert len(after) == before + 1
    pasted = [o for o in after if o.name == "box1_copy"][0]
    assert pasted.uid != obst.uid
    window.close()

def test_cut_removes_then_paste_restores(monkeypatch):
    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    _select_first_obstruction(window)

    # _on_cut() -> _on_delete_selected() shows a real confirmation dialog.
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a, **k: mw.QMessageBox.Yes)

    count_before = len(window.api.obstructions.all())
    window._on_cut()
    assert len(window.api.obstructions.all()) == count_before - 1

    window._on_paste()
    assert len(window.api.obstructions.all()) == count_before
    window.close()

def test_duplicate_is_immediate_no_selection_needed_afterwards(monkeypatch):
    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    _select_first_obstruction(window)

    before = len(window.api.obstructions.all())
    window._on_duplicate()
    after = window.api.obstructions.all()
    assert len(after) == before + 1
    assert any(o.name == "box1_copy" for o in after)
    window.close()

def test_copy_on_scenario_row_is_rejected_not_crashed(monkeypatch):
    window = _make_window()
    window.api.scenarios.create("Baseline", "")
    # Scenario rows aren't FdsEntity — selecting one and hitting Copy must
    # decline cleanly, not raise AttributeError reaching for .model_copy().
    informed = {"called": False}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.__setitem__("called", True))
    window.explorer.selectedItems  # sanity: explorer exists
    monkeypatch.setattr(window.explorer, "selected", lambda: ("scenarios", window.api.scenarios.all()[0]))
    window._on_copy()
    assert informed["called"] is True
    assert window._clipboard_entity is None
    window.close()

def test_snap_settings_updates_viewport_state(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"grid_size": 0.25, "enabled": False}))
    window._on_snap_settings()
    assert window.api.viewport.state.snap.grid_size == 0.25
    assert window.api.viewport.state.snap.enabled is False
    window.close()

def test_draw_cylinder_calls_geom_cylinder(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"name": "C1", "center_base": [0, 0, 0], "radius": 0.5, "height": 2.0, "surf_id": "INERT"}
    ))
    recorded = {}
    monkeypatch.setattr(window.api.geom, "cylinder", lambda *a, **k: recorded.update(args=a, kwargs=k))
    window._on_draw_cylinder()
    assert recorded["args"] == ([0, 0, 0], 0.5, 2.0)
    assert recorded["kwargs"] == {"surf_id": "INERT", "name": "C1"}
    window.close()

def test_draw_sphere_calls_geom_sphere(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"name": "S1", "center": [1, 2, 3], "radius": 0.75, "surf_id": "INERT"}
    ))
    recorded = {}
    monkeypatch.setattr(window.api.geom, "sphere", lambda *a, **k: recorded.update(args=a, kwargs=k))
    window._on_draw_sphere()
    assert recorded["args"] == ([1, 2, 3], 0.75)
    assert recorded["kwargs"] == {"surf_id": "INERT", "name": "S1"}
    window.close()

def test_draw_cone_calls_geom_cone(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"name": "K1", "center_base": [0, 0, 0], "radius": 1.0, "height": 3.0, "surf_id": "INERT"}
    ))
    recorded = {}
    monkeypatch.setattr(window.api.geom, "cone", lambda *a, **k: recorded.update(args=a, kwargs=k))
    window._on_draw_cone()
    assert recorded["args"] == ([0, 0, 0], 1.0, 3.0)
    window.close()

def test_unsupported_draw_primitive_shows_clean_placeholder_not_error(monkeypatch):
    window = _make_window()
    captured = {}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda self, title, text: captured.update(title=title, text=text))
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: pytest.fail("must not show an error dialog"))
    window._on_placeholder_geometry_primitive("Wall")
    assert "Wall" in captured["text"]
    window.close()

@pytest.mark.parametrize("handler_name,expected_quantity", [
    ("_on_add_heat_flux", "HEAT FLUX"),
    ("_on_add_smoke_detector", "OPTICAL DENSITY"),
    ("_on_add_beam_detector", "EXTINCTION COEFFICIENT"),
    ("_on_add_gas_sensor", "CARBON MONOXIDE"),
    ("_on_add_anemometer", "VELOCITY"),
    ("_on_add_velocity_probe", "VELOCITY"),
    ("_on_add_pressure_probe", "PRESSURE"),
])
def test_device_sensor_prefills_expected_quantity(monkeypatch, handler_name, expected_quantity):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"quantity": expected_quantity, "xyz": [0, 0, 1]}
    ))
    recorded = {}
    monkeypatch.setattr(window.dispatcher, "call", lambda name, values: recorded.update(name=name, values=values))
    getattr(window, handler_name)()
    assert _FakeDialog.last_schema["properties"]["quantity"]["default"] == expected_quantity
    assert recorded["name"] == "add_device"
    assert recorded["values"]["quantity"] == expected_quantity
    window.close()

def test_add_nozzle_reuses_sprinkler_entity_flow(monkeypatch):
    window = _make_window()
    recorded = {}
    monkeypatch.setattr(window, "_on_add_entity", lambda tool_name: recorded.setdefault("tool", tool_name))
    window._on_add_nozzle()
    assert recorded["tool"] == "add_sprinkler"
    window.close()

def test_fullscreen_toggles_window_state():
    # Qt only applies/tracks window-state flags once the native window has
    # actually been shown — offscreen platform included.
    window = _make_window()
    window.show()
    assert window.isFullScreen() is False
    window._on_toggle_fullscreen()
    assert window.isFullScreen() is True
    window._on_toggle_fullscreen()
    assert window.isFullScreen() is False
    window.close()

def test_save_then_load_bookmark_restores_camera(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("north-view", True))
    saved_camera = window.api.viewport.state.camera
    window._on_save_bookmark()
    assert window._view_bookmarks["north-view"] is saved_camera

    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: ("north-view", True))
    recorded = {}
    monkeypatch.setattr(window.api.viewport, "set_camera", lambda cam: recorded.setdefault("camera", cam))
    window._on_load_bookmark()
    assert recorded["camera"] is saved_camera
    window.close()

def test_load_bookmark_with_none_saved_shows_info_not_picker(monkeypatch):
    window = _make_window()
    informed = {"called": False}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.__setitem__("called", True))

    def _fail(*a, **k):
        raise AssertionError("should not prompt for a bookmark name when none exist")
    monkeypatch.setattr(mw.QInputDialog, "getItem", _fail)

    window._on_load_bookmark()
    assert informed["called"] is True
    window.close()

def test_output_frequency_updates_dump_params_undoably(monkeypatch):
    window = _make_window()
    original = window.api.project.dump.dt_devc
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"dt_devc": 2.5, "dt_slcf": 5.0}))
    window._on_output_frequency()
    assert window.api.project.dump.dt_devc == 2.5
    assert window.api.project.dump.dt_slcf == 5.0
    window.api.history.undo()
    window.api.history.undo()
    assert window.api.project.dump.dt_devc == original
    window.close()

def test_units_conversion_length_meters_to_feet(monkeypatch):
    window = _make_window()
    queue = iter([("Length", True), ("m", True), ("ft", True)])
    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: next(queue))
    monkeypatch.setattr(mw.QInputDialog, "getDouble", lambda *a, **k: (1.0, True))

    captured = {}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda self, title, text: captured.update(text=text))
    window._on_units_conversion()
    assert "3.28" in captured["text"]
    window.close()

def test_units_conversion_temperature_boiling_point(monkeypatch):
    window = _make_window()
    queue = iter([("Temperature", True), ("C", True), ("F", True)])
    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: next(queue))
    monkeypatch.setattr(mw.QInputDialog, "getDouble", lambda *a, **k: (100.0, True))

    captured = {}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda self, title, text: captured.update(text=text))
    window._on_units_conversion()
    assert "212" in captured["text"]
    window.close()

def test_calculator_evaluates_arithmetic(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("2+2*3", True))
    captured = {}
    monkeypatch.setattr(mw.QMessageBox, "information", lambda self, title, text: captured.update(text=text))
    window._on_calculator()
    assert "= 8" in captured["text"]
    window.close()

def test_calculator_rejects_unsafe_expression(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("__import__('os')", True))
    warned = {"called": False}
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a, **k: warned.__setitem__("called", True))
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: pytest.fail("unsafe expression must not be evaluated"))
    window._on_calculator()
    assert warned["called"] is True
    window.close()
