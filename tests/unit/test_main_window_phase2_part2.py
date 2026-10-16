"""Automated regression coverage for the Phase 2 menu handlers (both wiring (part 2 of 4)."""


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

class _FakeSliceEntry:
    def __init__(self, quantity, units, mesh_id, filepath):
        self.quantity, self.units, self.mesh_id, self.filepath = quantity, units, mesh_id, filepath

class _FakeValidationResult:
    def __init__(self, rule, text):
        self.rule = rule
        self._text = text

    def __str__(self):
        return self._text

class _FakeReportDialog:
    def __init__(self, title, text, parent=None):
        pass

    def exec(self):
        return QDialog.Accepted

class _FakeFigureDialog:
    last_title = None
    last_fig = None

    def __init__(self, title, fig, parent=None):
        _FakeFigureDialog.last_title = title
        _FakeFigureDialog.last_fig = fig

    def exec(self):
        return QDialog.Accepted


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
