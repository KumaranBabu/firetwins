"""Room for the 3D view in both programs: a one-column editor, a lean results viewer, focus mode and the icon strips."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDockWidget, QToolBar  # noqa: E402

from pyfds.api.facade import FdsApi  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def _pump(app, n=8):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def viewer(qapp):
    from pyfds.gui.results.window import ResultsWindow
    w = ResultsWindow(FdsApi())
    w.resize(1366, 768)
    w.show()
    _pump(qapp)
    yield w
    w.close()


@pytest.fixture
def editor(qapp):
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    w.resize(1366, 768)
    w.show()
    _pump(qapp)
    yield w
    w.close()


def test_viewer_tools_and_record_bars_start_hidden(viewer):
    titles = {b.windowTitle(): b for b in viewer.findChildren(QToolBar)}
    assert titles["Tools"].isHidden() and titles["Record"].isHidden() and not titles["Time"].isHidden()


def test_viewer_gives_the_3d_view_most_of_the_window(viewer):
    assert viewer.view.width() * viewer.view.height() > 0.72 * 1366 * 768


def test_viewer_strip_has_navigation_views_mode_and_layout_buttons(viewer):
    strip = viewer.view_overlay
    names = [b.toolTip() or b.text() for b in strip.buttons]
    assert len(strip.buttons) >= 10
    assert any("Rendering" in n for n in names) and any("Focus" in n for n in names)


def test_viewer_focus_mode_keeps_the_time_bar(viewer):
    viewer.toggle_focus_mode(True)
    shown = [b.windowTitle() for b in viewer.findChildren(QToolBar) if not b.isHidden()]
    assert shown == ["Time"] and all(d.isHidden() for d in viewer.findChildren(QDockWidget))
    viewer.toggle_focus_mode(False)
    assert not viewer.findChildren(QDockWidget)[0].isHidden()


def test_viewer_window_menu_lists_bars_and_panels(viewer):
    menu = next(a.menu() for a in viewer.menuBar().actions() if a.text() == "&Window")
    sub = {a.text(): a.menu() for a in menu.actions() if a.menu()}
    sub["&Toolbars"].aboutToShow.emit()
    sub["&Panels"].aboutToShow.emit()
    assert {"Time", "Tools", "Record"} <= {a.text() for a in sub["&Toolbars"].actions()}
    assert any("Navigation View" in a.text() for a in sub["&Panels"].actions())


def test_viewer_rendering_mode_button_changes_mode(viewer):
    from pyfds.api.viz import model as vm
    button = next(b for b in viewer.view_overlay.buttons if b.toolTip() == "Rendering mode")
    target = next(a for a in button.menu().actions() if a.text() == "Realistic")
    target.trigger()
    assert viewer.viewer.viz.rendering_mode == "realistic" and "realistic" in vm.RENDER_MODES


def test_editor_has_one_left_column_with_the_properties_under_the_tree(editor):
    assert editor.dockWidgetArea(editor.properties_dock) == Qt.LeftDockWidgetArea
    assert editor.explorer_dock.y() < editor.properties_dock.y()
    assert editor.explorer_dock.x() == editor.properties_dock.x()
    assert editor.view_tabs.width() * editor.view_tabs.height() > 0.60 * 1366 * 768


def test_editor_filter_row_is_hidden_and_the_strip_has_a_show_menu(editor):
    assert editor.filter_bar.isHidden()
    button = next(b for b in editor.view_overlay.buttons if b.menu() is not None and "mesh display" in b.toolTip())
    menu = button.menu()
    menu.aboutToShow.emit()
    labels = {a.text() for a in menu.actions()}
    assert {"Mesh display", "Snap grid", "Polar snap"} <= labels
    first = next(a for a in menu.actions() if a.isCheckable())
    state = first.isChecked()
    first.trigger()
    assert first.isChecked() != state
