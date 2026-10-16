"""F3: the 2D plan view widget and panel, driven with real Qt mouse/key events (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.plan import PlanPanel, PlanView  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([20, 20, 10], [0, 10, 0, 10, 0, 3], name="M")
    a.obstructions.add_obstruction([2, 4, 2, 4, 0, 2], name="box")
    a.viewport.set_snap(enabled=True, grid_size=0.5, snap_to_grid=True, snap_to_mesh=False)
    return a


@pytest.fixture
def view(api):
    v = PlanView(api)
    v.resize(800, 600)
    v.show()
    v.fit()
    yield v
    v.shutdown()
    v.close()


def click(view, x, y, mods=Qt.NoModifier):
    QTest.mouseClick(view.viewport(), Qt.LeftButton, mods, view.widget_pos_of(x, y))


def test_shows_the_model_and_fits_it(view):
    kinds = [s.kind for s in view._shapes]
    assert kinds == ["mesh", "obstruction"]
    r = view.mapFromScene(view.to_scene(0, 0)), view.mapFromScene(view.to_scene(10, 10))
    assert 0 <= r[0].x() < r[1].x() <= 800 and 0 <= r[1].y() < r[0].y() <= 600      # the whole domain is on screen
    assert view.scene().items()                                                      # and drawn


def test_refits_when_shown_and_resized_until_the_user_moves_the_view(api):
    v = PlanView(api)                                  # built hidden and tiny, like the window does
    v.resize(900, 700)
    v.show()
    p0, p1 = v.widget_pos_of(0, 0), v.widget_pos_of(10, 10)
    assert p1.x() - p0.x() > 300                       # fills the view instead of staying a speck
    v.resize(500, 400)
    assert v.widget_pos_of(10, 10).x() - v.widget_pos_of(0, 0).x() < p1.x() - p0.x()     # followed the resize
    v.zoom(2.0)
    scale = v.px_per_m
    v.resize(700, 500)
    assert v.px_per_m == pytest.approx(scale)           # the user's zoom is left alone
    v.fit()
    v.shutdown()
    v.close()


def test_y_axis_points_up_on_screen(view):
    assert view.widget_pos_of(5, 8).y() < view.widget_pos_of(5, 2).y()


def test_click_selects_and_ctrl_click_adds(view):
    picked, groups = [], []
    view.entity_picked.connect(lambda a, e: picked.append((a, e.name)))
    view.selection_changed.connect(lambda g: groups.append([e.name for _a, e in g]))
    click(view, 3, 3)
    assert picked == [("obstructions", "box")] and groups[-1] == ["box"]
    click(view, 5, 0.0, Qt.ControlModifier)                         # the domain edge: adds the mesh
    assert sorted(groups[-1]) == ["M", "box"]
    click(view, 8, 8)                                                # empty space inside the domain: clears
    assert groups[-1] == []


def test_selection_from_the_tree_is_highlighted(view, api):
    box = api.obstructions.get("box")
    view.set_selection([box])
    assert id(box) in view._selected
    pen_widths = {round(i.pen().widthF(), 1) for i in view.scene().items() if hasattr(i, "pen")}
    assert 3.0 in pen_widths


def test_drawing_a_box_with_the_shared_tool_snaps_and_is_one_undo(view, api):
    view.tools.props.height = 2.0
    view.tools.activate("obstruction")
    click(view, 6.1, 6.1)
    QTest.mouseMove(view.viewport(), view.widget_pos_of(8.0, 7.0))
    assert view.tools.preview().boxes                                  # rubber band is up
    assert view._preview_items
    click(view, 8.1, 7.1)
    new = [o for o in api.obstructions.all() if o.name != "box"][0]
    assert (new.x_min, new.x_max, new.y_min, new.y_max) == (6.0, 8.0, 6.0, 7.0)
    assert (new.z_min, new.z_max) == (0.0, 2.0)                        # starts at the plan's level
    api.history.undo()
    assert len(api.obstructions.all()) == 1


def test_level_sets_the_height_new_objects_start_at(view, api):
    view.set_level(1.5, 3.0)
    view.tools.props.height = 1.0
    view.tools.activate("obstruction")
    click(view, 6, 6)
    click(view, 8, 8)
    o = [o for o in api.obstructions.all() if o.name != "box"][0]
    assert (o.z_min, o.z_max) == (1.5, 2.5)


def test_a_drag_does_not_click(view, api):
    view.tools.activate("obstruction")
    p0, p1 = view.widget_pos_of(6, 6), view.widget_pos_of(9, 9)
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, p0)
    QTest.mouseMove(view.viewport(), p1)
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    assert not view.tools.current.active()


def test_wall_by_clicks_and_enter(view, api):
    view.tools.activate("wall")
    click(view, 6, 6)
    click(view, 9, 6.2)                                                # forced along X by the tool
    QTest.keyClick(view, Qt.Key_Return)
    walls = [o for o in api.obstructions.all() if o.name != "box"]
    assert len(walls) == 1 and walls[0].x_max - walls[0].x_min > 3.0


def test_escape_cancels_then_leaves_the_tool(view):
    view.tools.activate("obstruction")
    click(view, 6, 6)
    QTest.keyClick(view, Qt.Key_Escape)
    assert not view.tools.current.active() and view.tools.current.name == "obstruction"
    QTest.keyClick(view, Qt.Key_Escape)
    assert view.tools.current.name == "select"


def test_measure_in_plan(view):
    view.tools.activate("measure")
    click(view, 1, 1)
    click(view, 4, 5)
    assert view.tools.current.last.distance == pytest.approx(5.0)


def test_zoom_pan_and_cursor_readout(view):
    assert view.viewport().hasMouseTracking()
    before = view.px_per_m
    view.zoom(2.0)
    assert view.px_per_m == pytest.approx(before * 2)
    h0 = view.horizontalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.MiddleButton, Qt.NoModifier, QPoint(300, 300))
    QTest.mouseMove(view.viewport(), QPoint(340, 300))
    QTest.mouseRelease(view.viewport(), Qt.MiddleButton, Qt.NoModifier, QPoint(340, 300))
    assert view.horizontalScrollBar().value() == h0 - 40                 # dragged 40 px right -> content moves with it
    view.fit()
    seen = []
    view.cursor_moved.connect(seen.append)
    QTest.mouseMove(view.viewport(), view.widget_pos_of(5, 5))
    x, y, z = seen[-1]
    assert (x, y) == pytest.approx((5, 5), abs=0.1) and z == 0.0


def test_follows_model_changes_and_viewport_filters(view, api):
    api.obstructions.add_obstruction([6, 7, 6, 7, 0, 1], name="late")
    assert any(s.label == "late" for s in view._shapes)
    from pyfds.core.viewport import VisibilityFlags
    api.viewport.set_visibility(VisibilityFlags.OBSTRUCTIONS, False)
    assert not any(s.kind == "obstruction" for s in view._shapes)


# -- the panel -------------------------------------------------------------------------------------------------------
@pytest.fixture
def panel(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = PlanPanel(api)
    p.resize(900, 650)
    p.show()
    yield p
    p.shutdown()
    p.close()


def test_floor_choice_sets_level_and_slab(panel, api):
    api.floors.define_floor("L1", 0.0, 3.0)
    api.floors.define_floor("L2", 3.0, 6.0)
    api.obstructions.add_obstruction([6, 7, 6, 7, 3.5, 5], name="up")
    panel.set_floor("L2")
    assert panel.view.level == 3.0 and panel.view.band == 3.0
    assert [s.label for s in panel.view._shapes if s.kind == "obstruction"] == ["up"]
    panel.floor_combo.setCurrentIndex(panel.floor_combo.findData("L1"))
    panel.floor_combo.activated.emit(panel.floor_combo.currentIndex())
    assert panel.view.level == 0.0 and "box" in [s.label for s in panel.view._shapes]
    with pytest.raises(KeyError):
        panel.set_floor("nope")


def test_level_box_and_units(panel, api):
    panel.level_box.setValue(1.0)
    assert panel.view.level == 1.0
    api.units.set_system("EN")
    p2 = PlanPanel(api)
    p2._on_cursor((3.28084, 0.0, 0.0))
    assert "x 10.76" in p2.coords.text() and p2.coords.text().rstrip().endswith("ft")
    p2.level_box.setValue(3.28084)                                     # typed in feet
    assert p2.view.level == pytest.approx(1.0, rel=1e-3)
    p2.shutdown()
    p2.close()


def test_grid_toggle_and_fit_and_coordinate_label(panel):
    panel.grid_check.setChecked(False)
    assert panel.view.show_grid is False
    panel.view.zoom(5)
    panel.fit_button.click()
    assert 0 <= panel.view.widget_pos_of(5, 5).x() <= panel.view.width()
    panel._on_cursor((1.234, 5.678, 0.0))
    assert "1.23" in panel.coords.text() and "5.68" in panel.coords.text()
    panel._on_cursor(None)
    assert panel.coords.text() == ""


def test_window_opens_the_2d_tab_and_mirrors_selection(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    w = MainWindow(FdsApi())
    w.api.meshes.add_mesh([10, 10, 10], [0, 4, 0, 4, 0, 3], name="M")
    o = w.api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="o")
    plan = w.show_plan_tab()
    assert w.view_tabs.tabText(1) == "2D" and w.view_tabs.currentWidget() is plan
    assert w.show_plan_tab() is plan                                   # created once
    w.explorer.select_entity("obstructions", o)
    assert id(o) in plan.view._selected                                # tree -> plan
    click(plan.view, 1.5, 1.5)
    assert w.explorer.selected()[1] is o                               # plan -> tree
    w._on_close_view_tab(1)
    assert getattr(w, "_plan_panel", None) is None
    w.close()


def test_polar_snap_control_from_the_toolbar(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    w.polar_combo.setCurrentIndex(w.polar_combo.findData(45.0))
    w.polar_combo.activated.emit(w.polar_combo.currentIndex())
    assert w.api.viewport.state.snap.polar_step_deg == 45.0
    w.api.viewport.set_snap(polar_step_deg=None)
    assert w.polar_combo.currentData() is None
    w.close()
