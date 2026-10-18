"""Room for the 3D view: focus mode, hide-all-panels, toolbar and panel lists, compact docks and the icon strip over the 3D view."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDockWidget, QToolBar  # noqa: E402

from tests.unit.test_main_window_phase2_part1 import _make_window  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def _window():
    w = _make_window()
    w.show()
    return w


def _shown(w, kind):
    return {x for x in w.findChildren(kind) if not x.isHidden()}


def test_focus_mode_hides_every_panel_and_toolbar_and_brings_them_back():
    w = _window()
    docks, bars = _shown(w, QDockWidget), _shown(w, QToolBar)
    assert docks and bars
    assert w.toggle_focus_mode() is True
    assert not _shown(w, QDockWidget) and not _shown(w, QToolBar)
    assert w.focus_action.isChecked()
    assert w.toggle_focus_mode() is False
    assert _shown(w, QDockWidget) == docks and _shown(w, QToolBar) == bars
    assert not w.focus_action.isChecked()
    w.close()


def test_focus_action_has_f11_and_panels_action_ctrl_b():
    w = _window()
    assert w.focus_action.shortcut().toString() == "F11" and w.panels_action.shortcut().toString() == "Ctrl+B"
    w.focus_action.trigger()
    assert w.focus_mode
    w.focus_action.trigger()
    assert not w.focus_mode
    w.close()


def test_hide_panels_keeps_the_toolbars_and_focus_mode_wins_over_it():
    w = _window()
    bars = _shown(w, QToolBar)
    w.toggle_panels(True)
    assert not _shown(w, QDockWidget) and _shown(w, QToolBar) == bars
    w.toggle_panels(False)
    assert _shown(w, QDockWidget)
    w.toggle_focus_mode(True)
    w.toggle_panels()                              # leaves focus mode instead of hiding more
    assert not w.focus_mode and _shown(w, QDockWidget)
    w.close()


def test_a_panel_hidden_by_the_user_stays_hidden_after_focus_mode():
    w = _window()
    w.agent_dock.hide()
    w.toggle_focus_mode(True)
    w.toggle_focus_mode(False)
    assert w.agent_dock.isHidden() and not w.explorer_dock.isHidden()
    w.close()


def test_window_menu_lists_every_toolbar_and_panel_including_tool_properties():
    w = _window()
    view = next(a.menu() for a in w.menuBar().actions() if a.text() == "&View")
    assert w.focus_action in view.actions() and w.panels_action in view.actions()
    menu = next(a.menu() for a in view.actions() if a.text() == "&Window")
    panels = next(a.menu() for a in menu.actions() if a.text() == "Show &Panels")
    bars = next(a.menu() for a in menu.actions() if a.text() == "Show &Toolbars")
    panels.aboutToShow.emit()
    bars.aboutToShow.emit()
    assert "Tool Properties" in [a.text() for a in panels.actions()]
    assert {"Drawing", "Filter", "View"} <= {a.text() for a in bars.actions()}
    w.close()


def test_reset_layout_clears_focus_mode():
    w = _window()
    w.toggle_focus_mode(True)
    w._on_reset_window_layout()
    assert not w.focus_mode and not w.focus_action.isChecked()
    w.close()


def test_the_default_layout_is_compact():
    w = _window()
    assert w.view_bar.isHidden()                                   # the strip over the 3D view replaces it
    assert w.drawing_bar.toolButtonStyle().name == "ToolButtonIconOnly"
    assert w.tool_properties_dock in w.tabifiedDockWidgets(w.explorer_dock)
    assert w.agent_dock in w.tabifiedDockWidgets(w.properties_dock)
    w.close()


def test_choosing_a_drawing_tool_shows_tool_properties_and_select_shows_the_tree_again():
    w = _window()
    w._on_tool_chosen("obstruction")
    assert w.tool_manager.current.name == "obstruction"
    w._on_tool_chosen("select")
    assert w.tool_manager.current.name == "select"
    w.close()


def test_overlay_buttons_share_the_menu_actions_and_fold_away():
    w = _window()
    ov = w.view_overlay
    actions = {b.defaultAction() for b in ov.buttons if b.defaultAction() is not None}
    assert w._grid_action in actions and w.snap_action in actions and w.focus_action in actions
    assert all(a in actions for a in w._render_actions.values())
    assert ov.expanded
    ov.fold_button.click()
    assert not ov.expanded
    ov.fold_button.click()
    assert ov.expanded
    w.close()


def test_every_viewport_bar_button_has_a_real_icon_so_icon_only_bars_make_sense():
    from pyfds.gui.icons import glyph_for_text
    for text in ("Select", "Measure", "Paint", "Iso", "Ortho", "Pick surface", "Wall", "Mesh", "Obstruction", "Hole", "Vent"):
        assert glyph_for_text(text) is not None, text
