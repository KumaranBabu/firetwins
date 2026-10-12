"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 3 of 6)."""


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

def _patch_export_animation(monkeypatch, window, *, smv="case.smv", out="a.mp4",
                            accepted=True, values=None, render=None):
    from tests.mw_proxy import main_window_mod as mod

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


def test_run_simulation_failure_shows_warning(monkeypatch, tmp_path):
    import concurrent.futures
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod
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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.shutil, "which", lambda x: "/usr/bin/fds")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(main_window_mod.QInputDialog, "getInt", lambda *a, **k: (1, False))

    called = {"run_async": False}
    monkeypatch.setattr(window.api.execution, "run_async", lambda **k: called.__setitem__("run_async", True))

    window._on_run_simulation()

    assert called["run_async"] is False
    window.close()

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

def test_open_smokeview_results_launches_non_blocking(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    smv_path = str(tmp_path / "case.smv")
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (smv_path, ""))

    called = {}
    monkeypatch.setattr(window.api.smokeview, "open", lambda path, **k: called.update(path=path, **k))

    window._on_open_smokeview_results()

    assert called == {"path": smv_path, "blocking": False}
    window.close()

def test_open_smokeview_results_cancelled_does_nothing(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    called = {"opened": False}
    monkeypatch.setattr(window.api.smokeview, "open", lambda *a, **k: called.__setitem__("opened", True))

    window._on_open_smokeview_results()

    assert called["opened"] is False
    window.close()

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
