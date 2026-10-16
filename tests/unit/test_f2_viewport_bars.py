"""F2: the View / Drawing / Filter toolbars and the Tool Properties panel (offscreen - no 3D widget needed)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.core.viewport import VisibilityFlags  # noqa: E402
from pyfds.gui.viewport_tools import Hit  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def w(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = MainWindow(FdsApi())
    yield win
    win.close()


def test_render_mode_buttons_drive_and_follow_the_viewport(w):
    assert w._render_actions["solid"].isChecked()
    w._render_actions["outlines"].trigger()
    assert w.api.viewport.state.render_mode == "outlines"
    assert w._render_menu_actions["outlines"].isChecked() and not w._render_actions["solid"].isChecked()
    w.api.viewport.set_render_mode("realistic")                      # changed from elsewhere (the agent, a script)
    assert w._render_actions["realistic"].isChecked() and w._render_menu_actions["realistic"].isChecked()


def test_menu_render_entries_are_real_now(w):
    w._render_menu_actions["wireframe"].trigger()
    assert w.api.viewport.state.show_wireframe and w._render_actions["wireframe"].isChecked()
    w._render_menu_actions["solid"].trigger()
    assert not w.api.viewport.state.show_wireframe


def test_filter_buttons_toggle_object_types_and_follow(w):
    a = w._filter_actions[VisibilityFlags.SLICES]
    assert a.isChecked()
    a.trigger()
    assert not w.api.viewport.state.is_visible(VisibilityFlags.SLICES)
    w.api.viewport.set_visibility(VisibilityFlags.HOLES, False)
    assert not w._filter_actions[VisibilityFlags.HOLES].isChecked()


def test_mesh_display_combo_and_snap_controls(w):
    w.mesh_display_combo.setCurrentIndex(w.mesh_display_combo.findData("lines"))
    w.mesh_display_combo.activated.emit(w.mesh_display_combo.currentIndex())
    assert w.api.viewport.state.mesh_display == "lines"
    w.snap_action.trigger()
    assert not w.api.viewport.state.snap.enabled
    w.grid_combo.setCurrentIndex(w.grid_combo.findData(0.5))
    w.grid_combo.activated.emit(w.grid_combo.currentIndex())
    assert w.api.viewport.state.snap.grid_size == 0.5
    w.ortho_action.trigger()
    assert w.api.viewport.state.snap.ortho
    w.api.viewport.set_mesh_display("boundary")
    assert w.mesh_display_combo.currentData() == "boundary"


def test_drawing_toolbar_activates_tools_and_shows_the_hint(w):
    assert w._tool_actions["select"].isChecked()
    w._tool_actions["wall"].trigger()
    assert w.tool_manager.current.name == "wall" and "Wall" in w.statusBar().currentMessage()
    w.tool_manager.activate("select")                                  # e.g. Esc in the viewport
    assert w._tool_actions["select"].isChecked() and not w._tool_actions["wall"].isChecked()


def test_draw_menu_and_toolbar_stay_in_step(w):
    w._draw_actions["add_obstruction"].trigger()
    assert w.tool_manager.current.name == "obstruction" and w._tool_actions["obstruction"].isChecked()
    assert w._draw_actions["add_obstruction"].isChecked()
    w._tool_actions["measure"].trigger()
    assert not w._draw_actions["add_obstruction"].isChecked() and w._draw_actions["measure"].isChecked()
    w._on_cancel_draw_mode()
    assert w.tool_manager.current.name == "select" and not any(a.isChecked() for a in w._draw_actions.values())


def test_a_drawn_box_is_one_undo_step_from_the_window(w):
    w.api.viewport.set_snap(enabled=False)
    w._tool_actions["obstruction"].trigger()
    w.tool_manager.click(Hit((0, 0, 0)))
    w.tool_manager.click(Hit((2, 2, 0)))
    assert len(w.api.obstructions.all()) == 1
    w.api.history.undo()
    assert w.api.obstructions.all() == []


def test_tool_properties_edit_the_tool_props_in_display_units(w):
    p = w.tool_properties
    p.height_box.setValue(2.0)
    assert w.tool_manager.props.height == pytest.approx(2.0)
    p.auto_base.setChecked(False)
    p.base_box.setValue(1.5)
    assert w.tool_manager.props.z_base == pytest.approx(1.5)
    p.auto_base.setChecked(True)
    assert w.tool_manager.props.z_base is None and not p.base_box.isEnabled()
    w.api.units.set_system("EN")
    p.sync()
    assert p.height_box.value() == pytest.approx(6.56168, rel=1e-4)       # 2 m shown in feet
    p.height_box.setValue(10.0)
    assert w.tool_manager.props.height == pytest.approx(3.048, rel=1e-3)


def test_tool_properties_surfaces_and_recent_list(w):
    p = w.tool_properties
    w.api.surfaces.create_default("STEEL")
    p.sync()
    p.surface_combo.setCurrentText("STEEL")
    p.paint_combo.setCurrentText("STEEL")
    assert w.tool_manager.props.surface_id == "STEEL" and w.tool_manager.props.paint_surface == "STEEL"
    w.tool_manager.props.remember("STEEL")
    w.tool_manager.activate("paint")                                   # a tool change re-syncs the panel
    assert p.recent.item(0).text() == "STEEL" and "Paint" in p.tool_label.text()
    p.set_paint_surface("")
    assert w.tool_manager.props.paint_surface is None


def test_navigation_and_snapshot_say_so_without_a_3d_view(w):
    w._on_navigation("roam")                                           # the offscreen window has no 3D widget
    assert "need the 3D view" in w.statusBar().currentMessage()
    assert w._on_save_view_image("x.png") == ""
