"""
Automated regression coverage for the Phase 2 menu handlers (both wiring
batches: File/Edit/Draw/Devices/View/Help, then Project Settings/
Preferences/Snap Settings/Output Frequency/Units Conversion/Calculator).

These exist because a live desktop GUI can't be driven headlessly here
(Viewport3D needs a real OpenGL window — see viewport_3d.py's module
docstring), so a manual click-through checklist can only ever cover what a
human actually clicked. This file exercises the same handler methods
programmatically, the same way test_main_window.py already does for the
pre-Phase-2 handlers: fake the dialog classes, call the `_on_*` method
directly, assert on the resulting api/project state.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import pyfds.gui.main_window as mw  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window():
    from pyfds.gui.main_window import MainWindow
    from pyfds.api import FdsApi
    return MainWindow(FdsApi())


# QSettings is faked globally by tests/conftest.py::no_real_qsettings —
# every GUI test in the suite is protected from writing into the real
# HKCU\Software\PyFDS\PyFDS registry key, not just this file.


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


# ── File menu ────────────────────────────────────────────────────────────

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


# ── Edit menu ────────────────────────────────────────────────────────────

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


# ── Draw menu ────────────────────────────────────────────────────────────

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


# ── Devices menu ─────────────────────────────────────────────────────────

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


# ── View menu ────────────────────────────────────────────────────────────

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


# ── Output menu ──────────────────────────────────────────────────────────

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


# ── Tools menu ───────────────────────────────────────────────────────────

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


# ── Help menu ────────────────────────────────────────────────────────────

def test_keyboard_shortcuts_lists_real_bindings(monkeypatch):
    window = _make_window()
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["text"] = text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_keyboard_shortcuts()
    assert "Copy" in captured["text"]
    assert "Paste" in captured["text"]
    assert "Ctrl" in captured["text"]
    window.close()


# ── Results menu (Phase 2 batch 3) ──────────────────────────────────────────
#
# ResultsManager (api.results) already has real read-side backends
# (SliceIndex/BoundaryIndex, generate_report, analyze_batch) that predate
# this wiring — these tests fake the index/report objects it returns so we
# exercise the handler's own logic (dialog plumbing, error handling) without
# needing real FDS output files on disk.

class _FakeSliceEntry:
    def __init__(self, quantity, units, mesh_id, filepath):
        self.quantity, self.units, self.mesh_id, self.filepath = quantity, units, mesh_id, filepath


def test_slice_browser_lists_indexed_slices(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_slices(self):
            return [_FakeSliceEntry("TEMP", "C", 1, "case_01.sf")]

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_slice_browser()
    assert "Slice Browser" in captured["title"]
    assert "TEMP" in captured["text"]
    assert "case_01.sf" in captured["text"]
    window.close()


def test_slice_browser_no_data_shows_info_not_report(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_slices(self):
            return []

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mw, "TextReportDialog", lambda *a, **k: pytest.fail("must not open report with no data"))
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_slice_browser()
    assert informed
    window.close()


def test_boundary_browser_lists_indexed_boundaries(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_boundaries(self):
            return [_FakeSliceEntry("WALL TEMPERATURE", "C", 1, "case_01.bf")]

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_boundary_browser()
    assert "Boundary Browser" in captured["title"]
    assert "WALL TEMPERATURE" in captured["text"]
    window.close()


def test_isosurface_settings_reuses_add_entity_flow(monkeypatch):
    window = _make_window()
    recorded = {}
    monkeypatch.setattr(window, "_on_add_entity", lambda tool_name: recorded.setdefault("tool", tool_name))
    window._on_isosurface_settings()
    assert recorded["tool"] == "add_isosurface"
    window.close()


def test_export_csv_copies_device_file(monkeypatch, tmp_path):
    window = _make_window()
    src = tmp_path / "case_01_devc.csv"
    src.write_text("Time,TC1\n0.0,20.0\n")
    dest = tmp_path / "exported.csv"
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def all_device_names(self):
            return ["TC1"]

        def find_device_file(self, name):
            return str(src)

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: ("TC1", True))
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a, **k: (str(dest), ""))
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: None)
    window._on_export_csv()
    assert dest.read_text() == src.read_text()
    window.close()


def test_generate_report_saves_with_chosen_format(monkeypatch, tmp_path):
    window = _make_window()
    dest = tmp_path / "report.html"
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(
        mw.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(dest), "HTML Report (*.html)"),
    )
    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: None)
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: None)
    saved = {}

    class _FakeReport:
        def save(self, filepath, *, fmt="text"):
            saved["filepath"], saved["fmt"] = filepath, fmt

    monkeypatch.setattr(window.api.results, "generate_report", lambda: _FakeReport())
    window._on_generate_report()
    assert saved == {"filepath": str(dest), "fmt": "html"}
    window.close()


def test_batch_export_writes_html_report(monkeypatch, tmp_path):
    window = _make_window()
    dest = tmp_path / "batch_report.html"
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("", True))
    monkeypatch.setattr(
        mw.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(dest), "HTML Report (*.html)"),
    )
    recorded = {}

    class _FakeReport:
        def to_html(self, filepath, title=""):
            recorded["filepath"], recorded["title"] = filepath, title

    def _fake_analyze_batch(output_root, study_name=None, **kwargs):
        recorded["output_root"], recorded["study_name"] = output_root, study_name
        return _FakeReport()

    monkeypatch.setattr(window.api.results, "analyze_batch", _fake_analyze_batch)
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: None)
    window._on_batch_export()
    assert recorded["output_root"] == str(tmp_path)
    assert recorded["study_name"] is None  # blank input means "all variants"
    assert recorded["filepath"] == str(dest)
    window.close()


def test_plot_manager_plots_chosen_device(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def all_device_names(self):
            return ["TC1", "TC2"]

        def find_device_file(self, name):
            return "case_01_devc.csv"

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: ("TC2", True))
    monkeypatch.setattr(mw, "_import_figure_dialog", lambda: _FakeFigureDialog)
    monkeypatch.setattr("pyfds.results.reader.DeviceReader.read", staticmethod(lambda filepath: "fake-results"))
    monkeypatch.setattr("pyfds.results.plotters.plot_device_timeseries", lambda results: "fake-fig")
    window._on_plot_manager()
    assert _FakeFigureDialog.last_title == "Plot: TC2"
    assert _FakeFigureDialog.last_fig == "fake-fig"
    window.close()


# ── Tools menu (Phase 2 batch 4) ────────────────────────────────────────────
#
# ValidationManager/MeshManager/PluginManager (api.validation/api.meshes/
# api.plugins) already had real read-side backends — these tests fake what
# they return so we exercise the handler's own logic without needing a
# real project full of meshes/entities to validate.

class _FakeValidationResult:
    def __init__(self, rule, text):
        self.rule = rule
        self._text = text

    def __str__(self):
        return self._text


def test_tools_validation_shows_plugin_inclusive_report(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window.api.validation, "validate_with_plugins", lambda: "PLUGIN REPORT TEXT")
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_tools_validation()
    assert "Validation" in captured["title"]
    assert "PLUGIN REPORT TEXT" in captured["text"]
    window.close()


def test_find_errors_lists_error_severity_only(monkeypatch):
    window = _make_window()

    class _FakeReport:
        errors = [_FakeValidationResult("SomeRule", "[ERROR] bad thing")]

    monkeypatch.setattr(window.api.validation, "validate", lambda: _FakeReport())
    captured = {}

    class _FakeDialog2:
        def __init__(self, title, text, parent=None):
            captured["text"] = text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeDialog2)
    window._on_find_errors()
    assert "[ERROR] bad thing" in captured["text"]
    window.close()


def test_find_errors_none_found_shows_info_not_report(monkeypatch):
    window = _make_window()

    class _FakeReport:
        errors = []

    monkeypatch.setattr(window.api.validation, "validate", lambda: _FakeReport())
    monkeypatch.setattr(mw, "TextReportDialog", lambda *a, **k: pytest.fail("must not open report with no errors"))
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_find_errors()
    assert informed
    window.close()


def test_mesh_diagnostics_lists_poisson_compliance(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window.api.meshes, "check_poisson", lambda: {"Mesh1": True, "Mesh2": False})
    captured = {}

    class _FakeDialog3:
        def __init__(self, title, text, parent=None):
            captured["text"] = text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeDialog3)
    window._on_mesh_diagnostics()
    assert "Mesh1" in captured["text"] and "OK" in captured["text"]
    assert "Mesh2" in captured["text"] and "WARNING" in captured["text"]
    window.close()


def test_mesh_diagnostics_no_meshes_shows_info(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window.api.meshes, "check_poisson", lambda: {})
    monkeypatch.setattr(mw, "TextReportDialog", lambda *a, **k: pytest.fail("must not open report with no meshes"))
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_mesh_diagnostics()
    assert informed
    window.close()


def test_mesh_checker_filters_to_mesh_rules_only(monkeypatch):
    window = _make_window()

    class _FakeReport:
        results = [
            _FakeValidationResult("MeshOverlapRule", "[WARN] meshes overlap"),
            _FakeValidationResult("UnrelatedRule", "[WARN] unrelated"),
        ]

    monkeypatch.setattr(window.api.validation, "validate", lambda: _FakeReport())
    captured = {}

    class _FakeDialog4:
        def __init__(self, title, text, parent=None):
            captured["text"] = text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeDialog4)
    window._on_mesh_checker()
    assert "meshes overlap" in captured["text"]
    assert "unrelated" not in captured["text"]
    window.close()


def test_mesh_checker_no_mesh_issues_shows_info(monkeypatch):
    window = _make_window()

    class _FakeReport:
        results = [_FakeValidationResult("UnrelatedRule", "[WARN] unrelated")]

    monkeypatch.setattr(window.api.validation, "validate", lambda: _FakeReport())
    monkeypatch.setattr(mw, "TextReportDialog", lambda *a, **k: pytest.fail("must not open report with no mesh issues"))
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_mesh_checker()
    assert informed
    window.close()


class _FakeReportDialog:
    def __init__(self, title, text, parent=None):
        pass

    def exec(self):
        return QDialog.Accepted


def test_plugin_manager_lists_then_loads_more_on_confirm(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(window.api.plugins, "all_plugins", lambda: ["fake-plugin"])
    monkeypatch.setattr(mw, "TextReportDialog", _FakeReportDialog)
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a, **k: mw.QMessageBox.Yes)
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: None)
    recorded = {}
    monkeypatch.setattr(
        window.api.plugins, "load_directory",
        lambda directory: recorded.setdefault("directory", directory) or 3,
    )
    window._on_plugin_manager()
    assert recorded["directory"] == str(tmp_path)
    window.close()


def test_plugin_manager_declines_loading_more(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window.api.plugins, "all_plugins", lambda: [])
    monkeypatch.setattr(mw, "TextReportDialog", _FakeReportDialog)
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a, **k: mw.QMessageBox.No)
    monkeypatch.setattr(
        mw.QFileDialog, "getExistingDirectory",
        lambda *a, **k: pytest.fail("must not prompt for a directory when the user declined"),
    )
    window._on_plugin_manager()
    window.close()


def test_fds_preview_shows_generated_fds_text(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(
        "pyfds.io.fds_writer.FdsWriter.to_string",
        lambda self, project: "&HEAD CHID='test' /",
    )
    captured = {}

    class _FakeDialog5:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeDialog5)
    window._on_fds_preview()
    assert "FDS Preview" in captured["title"]
    assert "&HEAD" in captured["text"]
    window.close()


class _FakeFigureDialog:
    last_title = None
    last_fig = None

    def __init__(self, title, fig, parent=None):
        _FakeFigureDialog.last_title = title
        _FakeFigureDialog.last_fig = fig

    def exec(self):
        return QDialog.Accepted


# ── HVAC menu ────────────────────────────────────────────────────────────

def _build_simple_hvac_network(window):
    window.api.hvac_nodes.add_node(xyz=[0, 0, 0], ambient=True, name="ATM")
    window.api.hvac_nodes.add_node(xyz=[5, 0, 0], name="ROOM")
    window.api.hvac_ducts.add_duct(node_id_1="ATM", node_id_2="ROOM", diameter=0.3, length=5.0)


def test_hvac_solver_setup_runs_solver_with_chosen_params(monkeypatch):
    window = _make_window()
    _build_simple_hvac_network(window)

    monkeypatch.setattr(
        mw, "SchemaFormDialog",
        _fake_dialog_returning({"rho": 1.0, "max_iter": 50, "tol": 1e-4}),
    )
    called = {}
    real_solve = window.api.hvac.solve_network

    def _spy_solve(rho=1.2, max_iter=200, tol=1e-5):
        called.update(rho=rho, max_iter=max_iter, tol=tol)
        return real_solve(rho=rho, max_iter=max_iter, tol=tol)

    monkeypatch.setattr(window.api.hvac, "solve_network", _spy_solve)

    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_hvac_solver_setup()
    assert called == {"rho": 1.0, "max_iter": 50, "tol": 1e-4}
    assert "HVAC" in captured["title"]
    assert "HVAC Network Solve" in captured["text"]
    window.close()


def test_hvac_diagnostics_runs_solver_with_defaults(monkeypatch):
    window = _make_window()
    _build_simple_hvac_network(window)

    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_hvac_diagnostics()
    assert captured["title"] == "HVAC Diagnostics"
    assert "HVAC Network Solve" in captured["text"]
    window.close()


def test_hvac_diagnostics_reports_solver_failure(monkeypatch):
    window = _make_window()

    def _boom():
        raise RuntimeError("bad network")

    monkeypatch.setattr(window.api.hvac, "solve_network", _boom)
    critical = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: critical.append(1))
    window._on_hvac_diagnostics()
    assert critical
    window.close()


# ── Window menu ──────────────────────────────────────────────────────────

def test_show_panels_submenu_toggles_dock_visibility():
    window = _make_window()
    window.show()
    assert window.explorer_dock.isVisible()
    window.explorer_dock.toggleViewAction().trigger()
    assert not window.explorer_dock.isVisible()
    window.close()


def test_workspace_then_layouts_round_trips_saved_state(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(window, "saveState", lambda: b"fake-state-bytes")
    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("my-layout", True))
    window._on_workspace()
    assert "my-layout" in window._window_layout_names()

    monkeypatch.setattr(mw.QInputDialog, "getItem", lambda *a, **k: ("my-layout", True))
    restored = []
    monkeypatch.setattr(window, "restoreState", lambda state: restored.append(state))
    window._on_layouts()
    assert restored == [b"fake-state-bytes"]
    window.close()


def test_layouts_with_none_saved_shows_info_not_picker(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(
        mw.QInputDialog, "getItem",
        lambda *a, **k: pytest.fail("must not prompt with no saved layouts"),
    )
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_layouts()
    assert informed
    window.close()


def test_reset_window_layout_restores_startup_state(monkeypatch):
    window = _make_window()
    restored = []
    monkeypatch.setattr(window, "restoreState", lambda state: restored.append(state))
    window._on_reset_window_layout()
    assert restored == [window._default_window_state]
    window.close()


def test_hvac_network_editor_opens_singleton_instance():
    window = _make_window()
    assert window._hvac_editor is None
    window._on_hvac_network_editor()
    first = window._hvac_editor
    assert first is not None
    window._on_hvac_network_editor()
    assert window._hvac_editor is first
    window.close()


# ── Group / Ungroup ──────────────────────────────────────────────────────

def test_group_selected_creates_group_and_assigns(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("MyGroup", True))
    window._on_group_selected()

    assert window.api.groups.group_of(a) == "MyGroup"
    assert window.api.groups.group_of(b) == "MyGroup"
    window.close()


def test_group_selected_declines_without_name(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])

    monkeypatch.setattr(mw.QInputDialog, "getText", lambda *a, **k: ("", False))
    window._on_group_selected()

    assert window.api.groups.group_of(a) is None
    window.close()


def test_group_selected_with_nothing_selected_shows_info(monkeypatch):
    window = _make_window()
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_group_selected()
    assert informed
    window.close()


def test_ungroup_selected_clears_membership(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])

    window._on_ungroup_selected()

    assert window.api.groups.group_of(a) is None
    window.close()


def test_ungroup_selecting_group_row_ungroups_all_members(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    g = window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("groups", g)])

    window._on_ungroup_selected()

    assert window.api.groups.group_of(a) is None
    assert window.api.groups.group_of(b) is None
    assert window.api.groups.get("G1") is None
    window.close()


def test_select_group_members_selects_all_in_tree(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()

    window._on_select_group_members("G1")

    pairs = window.explorer.selected_entities()
    assert {e.name for _, e in pairs} == {"a", "b"}
    window.close()


def test_select_group_members_empty_group_shows_info(monkeypatch):
    window = _make_window()
    window.api.groups.create("Empty")
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_select_group_members("Empty")
    assert informed
    window.close()


# ── Move / Rotate / Scale / Mirror Selected ─────────────────────────────

def test_move_selected_translates_all_entity_kinds(monkeypatch):
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 2], name="obst")
    from pyfds.domain.geometry_tools import GeometryTools
    geom = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="geom")
    window.api.project.add_entity(geom)
    device = window.api.devices.add_device(xyz=[5, 5, 5], quantity="TEMPERATURE", name="dev")
    window.explorer.refresh()
    window.explorer.select_entities([
        ("obstructions", obst), ("geom", geom), ("devices", device),
    ])

    monkeypatch.setattr(
        mw, "SchemaFormDialog", _fake_dialog_returning({"dx": 1.0, "dy": 2.0, "dz": 0.0})
    )
    window._on_move_selected()

    assert (obst.x_min, obst.y_min) == (1.0, 2.0)
    assert geom.verts[0] == (1.0, 2.0, 0.0)
    assert device.xyz == (6.0, 7.0, 5.0)

    window.api.history.undo()
    assert (obst.x_min, obst.y_min) == (0.0, 0.0)
    assert geom.verts[0] == (0.0, 0.0, 0.0)
    assert device.xyz == (5.0, 5.0, 5.0)
    window.close()


def test_move_selected_with_nothing_selected_shows_info(monkeypatch):
    window = _make_window()
    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_move_selected()
    assert informed
    window.close()


def test_rotate_selected_uses_shared_pivot_not_per_entity_centroid(monkeypatch):
    # Two identical-size boxes side by side; rotating 180° about their
    # COMBINED centroid should swap their positions, not spin each one in
    # place about its own centroid (which would leave both unchanged).
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"degrees": 180.0}))
    window._on_rotate_selected()

    assert (a.x_min, a.x_max) == pytest.approx((4.0, 6.0))
    assert (b.x_min, b.x_max) == pytest.approx((0.0, 2.0))
    window.close()


def test_rotate_selected_skips_xb_entity_on_non_90_multiple(monkeypatch):
    # XB entities (RotateCommand) only accept multiples of 90; a Geom in
    # the same batch has no such restriction — the XB entity is skipped,
    # not a hard failure for the whole selection.
    window = _make_window()
    obst = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="obst")
    from pyfds.domain.geometry_tools import GeometryTools
    geom = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="geom")
    window.api.project.add_entity(geom)
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", obst), ("geom", geom)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"degrees": 17.5}))
    window._on_rotate_selected()

    assert (obst.x_min, obst.x_max) == (0.0, 2.0)  # untouched — skipped
    assert geom.verts[0] != (0.0, 0.0, 0.0)  # Geom did rotate
    window.close()


def test_scale_selected_scales_about_shared_centroid(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"factor": 2.0}))
    window._on_scale_selected()

    # Combined centroid is x=3.0 — doubling extents about that shared
    # point spreads the two boxes apart, not just each growing in place.
    assert a.x_min == pytest.approx(-3.0)
    assert b.x_max == pytest.approx(9.0)
    window.close()


def test_mirror_selected_reflects_across_shared_plane(monkeypatch):
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a), ("obstructions", b)])

    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"axis": "X"}))
    window._on_mirror_selected()

    assert (a.x_min, a.x_max) == pytest.approx((4.0, 6.0))
    assert (b.x_min, b.x_max) == pytest.approx((0.0, 2.0))
    window.close()


def test_boolean_union_requires_exactly_two_geoms(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    window.api.project.add_entity(a)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a)])

    informed = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_boolean_union()
    assert informed
    assert len(window.api.geom.all()) == 1  # no result added
    window.close()


def test_boolean_union_adds_new_geom_keeping_sources(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a), ("geom", b)])

    window._on_boolean_union()

    all_geoms = window.api.geom.all()
    assert len(all_geoms) == 3  # a, b, and the new union — sources kept
    assert a in all_geoms and b in all_geoms
    window.close()


def test_boolean_difference_and_intersection_also_add_new_geom(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()

    window.explorer.select_entities([("geom", a), ("geom", b)])
    window._on_boolean_difference()
    assert len(window.api.geom.all()) == 3

    window.explorer.select_entities([("geom", a), ("geom", b)])
    window._on_boolean_intersection()
    assert len(window.api.geom.all()) == 4
    window.close()


def test_boolean_union_shows_error_for_non_manifold_geom(monkeypatch):
    window = _make_window()
    from pyfds.domain.geometry_tools import GeometryTools
    a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="open_a")
    a.faces = a.faces[:-2]
    b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
    window.api.project.add_entity(a)
    window.api.project.add_entity(b)
    window.explorer.refresh()
    window.explorer.select_entities([("geom", a), ("geom", b)])

    critical = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: critical.append(1))
    window._on_boolean_union()
    assert critical
    assert len(window.api.geom.all()) == 2  # no result added
    window.close()


def test_group_selection_transforms_as_one_rigid_unit(monkeypatch):
    # Selecting only one grouped entity must expand to the whole group —
    # this is what makes Group/Ungroup useful for transforms, not just an
    # Explorer-tree decoration.
    window = _make_window()
    a = window.api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 1], name="a")
    b = window.api.obstructions.add_obstruction(xb=[4, 6, 0, 2, 0, 1], name="b")
    window.api.groups.create("G1")
    window.api.groups.assign(a, "G1")
    window.api.groups.assign(b, "G1")
    window.explorer.refresh()
    window.explorer.select_entities([("obstructions", a)])  # only 'a' selected

    monkeypatch.setattr(
        mw, "SchemaFormDialog", _fake_dialog_returning({"dx": 10.0, "dy": 0.0, "dz": 0.0})
    )
    window._on_move_selected()

    assert a.x_min == pytest.approx(10.0)
    assert b.x_min == pytest.approx(14.0)  # 'b' moved too, via group expansion
    window.close()
