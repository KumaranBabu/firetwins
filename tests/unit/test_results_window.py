"""The results window under Qt's offscreen platform (no live 3D interactor): menus, tree, time controls, dialogs."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api.facade import FdsApi
from pyfds.gui.results import window as winmod
from pyfds.gui.results.forms import SettingsDialog
from pyfds.gui.results.window import ResultsWindow

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
R = "root/FDS Results/"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, tmp_path, monkeypatch):
    run = tmp_path / "run"
    shutil.copytree(FIX, run)
    msgs = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: msgs.append(a[2]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    w.msgs = msgs
    w.smv = str(run / "rroom.smv")
    yield w
    w.close()


def menu(w, title):
    return next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == title)


def trigger(w, top, text):
    stack, acts = [menu(w, top)], []                  # the menu and its submenus (Section Box, Movie, ...)
    while stack:
        for a in stack.pop().actions():
            acts.append(a)
            if a.menu() is not None:
                stack.append(a.menu())
    act = next(a for a in acts if a.text().replace("&", "").startswith(text))
    act.trigger()


def test_open_populates_tree_and_toggle_draws(win):
    win.open_results(win.smv)
    assert win.tree.topLevelItemCount() >= 3
    win._toggle(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    assert win.viewer.active_leaves() and win.slider.maximum() > 3
    it = win.tree.item_for(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    assert it.font(0).bold() and it.text(0).startswith("●")
    win._seek(4)
    assert win.viewer.time > 0 and "0:" in win.time_label.text()
    win._step(1)
    assert win.slider.value() == 5
    assert win.windowTitle().endswith("*")


def test_menu_actions_report_errors_in_a_box(win):
    trigger(win, "Tools", "Time History")            # nothing loaded: opens an empty plot, no crash
    win.open_results(win.smv)
    win.msgs.clear()
    win.viewer.set_speed(2)
    assert win._try(lambda: 1 / 0) is None and "ZeroDivisionError" in win.msgs[-1]


def test_view_menu_changes_camera_and_section(win):
    win.open_results(win.smv)
    trigger(win, "View", "Top")
    assert win.viewer.camera.position[2] > win.viewer.camera.target[2]
    trigger(win, "View", "Add Section Box")
    assert win.viewer.viz.active_view is not None
    trigger(win, "View", "Default View")
    assert win.viewer.viz.active_view is None


def test_settings_dialog_returns_only_changes(app):
    from pyfds.results.viz import model as vm
    u = vm.Units()
    d = SettingsDialog("Units", u, None, {"temperature": ("C", "F", "K")})
    assert d.values() == {}
    d._widgets["temperature"][0].setCurrentText("F")
    assert d.values() == {"temperature": "F"}


def test_screenshot_and_movie_render_offscreen(win, tmp_path):
    win.open_results(win.smv)
    win._toggle(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    out = tmp_path / "shot.png"
    shots = win.viewer.screenshot_plan(str(out), "single", time=3.0)
    win.viewer.render_screenshots(shots, win.view.make_renderer(win.viewer), (320, 200))
    assert out.stat().st_size > 1000
    from pyfds.results.viz import capture as cap
    plan = cap.movie_plan(str(tmp_path / "m.mp4"), 0, 1, fps=2, size=(160, 100))
    res = win.viewer.render_movie(plan, win.view.make_renderer(win.viewer))
    assert res["frames"] == 3 and (Path(res["path"]).exists() or Path(res["frames_dir"]).exists())


def test_run_monitor_open_results_hook(win):
    assert callable(winmod.ResultsWindow)
