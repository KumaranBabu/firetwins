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


def test_isosurface_settings_reuses_add_entity_flow(monkeypatch):
    window = _make_window()
    recorded = {}
    monkeypatch.setattr(window, "_on_add_entity", lambda tool_name: recorded.setdefault("tool", tool_name))
    window._on_isosurface_settings()
    assert recorded["tool"] == "add_isosurface"
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
