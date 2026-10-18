"""Smoke tests — MainWindow app shell (src/pyfds/gui/main_window.py). (part 4 of 6)."""


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


def _finish_render(window):
    """Wait for the background render thread and deliver its result signal."""
    from PySide6.QtWidgets import QApplication
    worker = getattr(window, "_render_worker", None)
    if worker is not None:
        worker.wait(10000)
        QApplication.processEvents()

def test_export_animation_nonzero_return_warns(monkeypatch):
    window = _make_window()
    _, shown = _patch_export_animation(monkeypatch, window, render=lambda *a, **k: 3)
    window._on_export_animation()
    _finish_render(window)
    assert "warning" in shown and "information" not in shown
    window.close()

def test_export_animation_exception_shows_critical(monkeypatch):
    window = _make_window()

    def _boom(*a, **k):
        raise RuntimeError("smokeview not found")

    _, shown = _patch_export_animation(monkeypatch, window, render=_boom)
    window._on_export_animation()
    _finish_render(window)
    assert "critical" in shown
    window.close()

def test_view_time_history_shows_figure_dialog(monkeypatch, tmp_path):
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(main_window_mod.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    called = {"restored": False}
    monkeypatch.setattr(window.api.results, "restore", lambda *a, **k: called.__setitem__("restored", True))

    window._on_restore_results()

    assert called["restored"] is False
    window.close()

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
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

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
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    monkeypatch.setattr(
        main_window_mod.QInputDialog, "getDouble",
        lambda self_or_parent, title, label, default, lo, hi, dec: (0.0, False),
    )

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window.api.obstructions.count() == 0
    window.close()

def test_box_footprint_picked_cancelled_at_z_max_creates_nothing(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()

    def fake_get_double(self_or_parent, title, label, default, lo, hi, dec):
        return (0.0, True) if "min" in label else (0.0, False)

    monkeypatch.setattr(main_window_mod.QInputDialog, "getDouble", fake_get_double)

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window.api.obstructions.count() == 0
    window.close()

def test_box_footprint_picked_unchecks_draw_actions_even_when_cancelled(monkeypatch):
    from tests.mw_proxy import main_window_mod

    window = _make_window()
    window._draw_actions["add_obstruction"].setChecked(True)
    monkeypatch.setattr(main_window_mod.QInputDialog, "getDouble", lambda *a, **k: (0.0, False))

    window._on_box_footprint_picked("add_obstruction", 0.0, 1.0, 0.0, 1.0)

    assert window._draw_actions["add_obstruction"].isChecked() is False
    window.close()
