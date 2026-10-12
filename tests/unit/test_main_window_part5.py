"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 5 of 6)."""


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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="target_box")
    monkeypatch.setattr(main_window_mod.QInputDialog, "getText", lambda *a, **k: ("target", True))

    window._on_find()

    assert window.explorer.selected()[1].name == "target_box"
    window.close()

def test_on_find_shows_message_when_nothing_matches(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getText", lambda *a, **k: ("nope", True))
    shown = {}
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_find()

    assert shown.get("info") is True
    window.close()

def test_convert_to_blocks_calls_voxelize_and_reports_count(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    called = {"voxelize": False}
    monkeypatch.setattr(window.api.geom, "voxelize", lambda path: called.__setitem__("voxelize", True))

    window._on_convert_to_blocks()

    assert called["voxelize"] is False
    window.close()

def test_convert_to_blocks_error_shows_critical(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

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

def test_export_db_materials_writes_file(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    out_path = str(tmp_path / "materials.json")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (out_path, ""))
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_export_db("materials")

    import os
    assert os.path.exists(out_path)
    window.close()

def test_export_db_cancelled_does_nothing(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    called = {"export": False}
    monkeypatch.setattr(window.api.engineering, "export_surfaces", lambda p: called.__setitem__("export", True))

    window._on_export_db("surfaces")

    assert called["export"] is False
    window.close()

def test_export_db_all_writes_folder(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    out_dir = str(tmp_path / "db_export")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: out_dir)
    monkeypatch.setattr(main_window_mod.QMessageBox, "information", lambda *a, **k: None)

    window._on_export_db_all()

    import os
    assert os.path.isdir(out_dir)
    assert len(os.listdir(out_dir)) > 0
    window.close()

def test_resume_simulation_success_shows_completion_dialog(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    called = {"resume": False}
    monkeypatch.setattr(window.api.execution, "resume_from_checkpoint", lambda *a, **k: called.__setitem__("resume", True))

    window._on_resume_simulation()

    assert called["resume"] is False
    window.close()

def test_resume_simulation_cancelled_at_process_count_does_nothing(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "c.fds"), ""))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, False))
    called = {"resume": False}
    monkeypatch.setattr(window.api.execution, "resume_from_checkpoint", lambda *a, **k: called.__setitem__("resume", True))

    window._on_resume_simulation()

    assert called["resume"] is False
    window.close()

def test_openmp_environment_sets_thread_count_and_is_undoable(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (4, True))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads == 4
    window.api.history.undo()
    assert window.api.project.misc.openmp_threads is None
    window.close()

def test_openmp_environment_zero_means_auto_unset(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window.api.project.misc.openmp_threads = 8
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (0, True))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads is None
    window.close()

def test_openmp_environment_cancelled_does_nothing(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (4, False))

    window._on_openmp_environment()

    assert window.api.project.misc.openmp_threads is None
    window.close()

def test_open_results_folder_opens_url(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    opened = {}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.setdefault("url", url))

    window._on_open_results_folder()

    assert "url" in opened
    window.close()

def test_open_results_folder_cancelled_does_nothing(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    opened = {"called": False}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.__setitem__("called", True))

    window._on_open_results_folder()

    assert opened["called"] is False
    window.close()

def test_open_doc_opens_existing_file(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    doc = tmp_path / "guide.pdf"
    doc.write_text("fake pdf")
    opened = {}
    monkeypatch.setattr(main_window_mod.QDesktopServices, "openUrl", lambda url: opened.setdefault("url", url))

    window._on_open_doc(doc)

    assert "url" in opened
    window.close()

def test_open_doc_missing_file_shows_message(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QMessageBox, "about", lambda *a, **k: None)

    window._on_about()  # must not raise
    window.close()
