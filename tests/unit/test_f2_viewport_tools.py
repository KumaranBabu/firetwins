"""F2: the Qt-free viewport tool framework - snapping, box/wall drawing, measure, pick and paint."""
import math

import pytest

from pyfds.api import FdsApi
from pyfds.core.viewport import SnapSettings
from pyfds.gui.viewport_tools import (Hit, ToolManager, face_index, paint_fields, snap_point, surface_at)


@pytest.fixture
def api():
    return FdsApi()


@pytest.fixture
def tm(api):
    api.viewport.set_snap(enabled=True, grid_size=0.5, snap_to_grid=True, snap_to_mesh=False, tolerance=0.25)
    return ToolManager(api)


def hit(x, y, z=0.0, normal=None, entity=None):
    return Hit((x, y, z), normal, entity)


# -- snapping ---------------------------------------------------------------------------------------------------
def test_snap_to_grid_and_off():
    s = SnapSettings(enabled=True, grid_size=0.5, snap_to_grid=True, snap_to_mesh=False)
    assert snap_point((1.26, 0.74, 0.1), s) == (1.5, 0.5, 0.0)
    s.enabled = False
    assert snap_point((1.26, 0.74, 0.1), s) == (1.26, 0.74, 0.1)


class _M:
    def __init__(self, lo, hi, cells):
        (self.x_min, self.y_min, self.z_min), (self.x_max, self.y_max, self.z_max) = lo, hi
        self.cell_count = cells


def test_mesh_lines_beat_the_grid():
    s = SnapSettings(enabled=True, grid_size=1.0, snap_to_grid=True, snap_to_mesh=True, tolerance=0.2)
    m = _M((0, 0, 0), (3, 3, 3), (10, 10, 10))                   # cell 0.3
    assert snap_point((0.62, 1.2, 0.0), s, [m])[:2] == pytest.approx((0.6, 1.2))
    assert snap_point((0.5, 0.5, 0.5), s, [m]) == pytest.approx((0.6, 0.6, 0.6))      # 0.6 is within reach
    s.tolerance = 0.05
    assert snap_point((0.4, 0.4, 0.4), s, [m]) == pytest.approx((0.0, 0.0, 0.0))      # no line in reach -> the grid


def test_vertex_snap_pulls_to_a_corner(api):
    api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1])
    s = SnapSettings(enabled=True, snap_to_vertex=True, snap_to_grid=False, snap_to_mesh=False, tolerance=0.3)
    assert snap_point((2.1, 0.9, 0.05), s, objects=api.obstructions.all()) == (2, 1, 0)
    assert snap_point((5, 5, 5), s, objects=api.obstructions.all()) == (5, 5, 5)


def test_ortho_and_polar_constrain_from_the_anchor():
    s = SnapSettings(enabled=True, snap_to_grid=False, snap_to_mesh=False, ortho=True)
    assert snap_point((3.0, 0.4, 0), s, anchor=(0, 0, 0)) == (3.0, 0.0, 0)
    s = SnapSettings(enabled=True, snap_to_grid=False, snap_to_mesh=False, polar_step_deg=45.0)
    x, y, _ = snap_point((2.0, 1.7, 0), s, anchor=(0, 0, 0))
    assert math.degrees(math.atan2(y, x)) == pytest.approx(45.0)


# -- box tools ----------------------------------------------------------------------------------------------------
def test_obstruction_two_clicks_use_the_tool_height_and_one_undo(tm, api):
    tm.props.height = 2.5
    tm.activate("obstruction")
    assert tm.click(hit(0.1, 0.1)) is None and tm.current.active()
    tm.move(hit(2.1, 1.9))
    p = tm.preview()
    assert p.boxes == [(0.0, 2.0, 0.0, 2.0, 0.0, 2.5)] and "2 x 2 x 2.5" in p.text
    o = tm.click(hit(2.1, 1.9))
    assert (o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max) == (0, 2, 0, 2, 0, 2.5)
    assert not tm.current.active() and len(api.obstructions.all()) == 1
    api.history.undo()
    assert api.obstructions.all() == []


def test_draws_on_top_of_another_object_and_honours_z_base(tm):
    tm.activate("obstruction")
    tm.click(hit(0, 0, 1.0))
    o = tm.click(hit(1, 1, 1.0))
    assert o.z_min == 1.0 and o.z_max == 4.0
    tm.props.z_base = 0.5
    tm.click(hit(0, 0, 9.0))
    o = tm.click(hit(1, 1, 9.0))
    assert o.z_min == 0.5


def test_zero_size_is_refused_and_keeps_the_first_corner(tm):
    tm.activate("obstruction")
    tm.click(hit(1, 1))
    assert tm.click(hit(1, 3)) is None
    assert tm.current.active() and "too small" in tm.take_messages()[0]
    assert tm.click(hit(3, 3)) is not None


def test_hole_and_surface_choice(tm, api):
    tm.props.surface_id = "STEEL"
    tm.activate("obstruction")
    tm.click(hit(0, 0))
    assert tm.click(hit(1, 1)).surface_id == "STEEL"
    tm.activate("hole")
    tm.click(hit(0, 0))
    assert tm.click(hit(1, 1)) in api.holes.all()


def test_vent_lies_in_the_plane_of_the_first_face(tm):
    tm.activate("vent")
    tm.click(hit(0, 0, 0))                                         # floor: flat in Z
    v = tm.click(hit(2, 3, 0))
    assert (v.z_min, v.z_max) == (0, 0) and (v.x_max, v.y_max) == (2, 3) and v.surface_id == "OPEN"
    tm.click(hit(4.0, 1.0, 0.5, normal=(1, 0, 0)))                 # a wall facing +X: flat in X
    w = tm.click(hit(4.0, 3.0, 2.5, normal=(1, 0, 0)))
    assert (w.x_min, w.x_max) == (4.0, 4.0) and (w.y_min, w.y_max) == (1.0, 3.0) and (w.z_min, w.z_max) == (0.5, 2.5)


def test_mesh_tool_makes_poisson_friendly_counts(tm, api):
    tm.props.cell_size = 0.1
    tm.props.height = 2.0
    tm.activate("mesh")
    tm.click(hit(0, 0))
    m = tm.click(hit(1.4, 1.0))
    assert m.cell_count == (15, 10, 20)                            # 14 -> 15 (factors 3, 5)
    assert api.meshes.all() == [m]


def test_escape_cancels_then_leaves_the_tool(tm):
    tm.activate("obstruction")
    tm.click(hit(0, 0))
    assert tm.escape() is False and not tm.current.active() and tm.current.name == "obstruction"
    assert tm.escape() is True and tm.current.name == "select"
    assert tm.escape() is False


# -- wall -------------------------------------------------------------------------------------------------------
def test_wall_segments_are_axis_aligned_and_corners_close(tm, api):
    tm.props.wall_thickness = 0.2
    tm.props.height = 3.0
    tm.activate("wall")
    tm.click(hit(0, 0))
    tm.click(hit(4.0, 0.3))                                         # nearly along X -> forced along X
    tm.move(hit(4.0, 3.0))
    assert len(tm.preview().boxes) == 2
    tm.click(hit(4.1, 3.0))                                         # nearly along Y at x=4
    made = tm.finish()
    assert len(made) == 2
    a, b = made
    assert (a.x_min, a.x_max, a.y_min, a.y_max) == pytest.approx((-0.1, 4.1, -0.1, 0.1))
    assert (b.x_min, b.x_max, b.y_min, b.y_max) == pytest.approx((3.9, 4.1, -0.1, 3.1))
    assert a.z_max == 3.0
    api.history.undo()
    assert api.obstructions.all() == []                             # the whole run is one undo step


def test_wall_close_joins_back_to_the_start(tm):
    tm.activate("wall")
    for p in ((0, 0), (4, 0), (4, 3), (0, 3)):
        tm.click(hit(*p))
    assert len(tm.current.close()) == 4


# -- measure ----------------------------------------------------------------------------------------------------
def test_measure_two_points(tm):
    tm.activate("measure")
    tm.click(hit(0, 0, 0))
    tm.move(hit(3.0, 4.0, 0))
    assert "distance 5" in tm.preview().text
    m = tm.click(hit(3.0, 4.0, 0))
    assert m.distance == pytest.approx(5.0) and m.delta == (3.0, 4.0, 0.0)
    assert tm.current.last is m and "distance 5" in tm.take_messages()[0]
    tm.click(hit(0, 0, 0))                                          # a third click starts over
    assert tm.current.active() and len(tm.current.history) == 1


# -- paint and pick -------------------------------------------------------------------------------------------------
def test_face_index_and_surface_expansion(api):
    assert [face_index(n) for n in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1))] == [0, 1, 2, 3, 4, 5]
    assert face_index(None) is None
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="A")
    assert surface_at(o, (0, 0, 1)) == "A" and surface_at(o, None) == "A"
    api.obstructions.update(o, surface_ids=["TOP", "SIDE", "BOT"])
    assert [surface_at(o, n) for n in ((0, 0, 1), (1, 0, 0), (0, 0, -1))] == ["TOP", "SIDE", "BOT"]


def test_paint_one_face_then_the_whole_object(tm, api):
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="A")
    tm.props.paint_surface = "B"
    tm.activate("paint")
    tm.click(hit(0.5, 0.5, 1.0, normal=(0, 0, 1), entity=("obstructions", o)))
    assert o.surface_ids == ["A", "A", "A", "A", "A", "B"]
    api.history.undo()
    assert not o.surface_ids and o.surface_id == "A"
    tm.click(hit(0.5, 0.5, 1.0, entity=("obstructions", o)))          # unknown face -> whole object
    assert o.surface_id == "B" and not o.surface_ids


def test_painting_every_face_collapses_to_one_surface(api):
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="A")
    api.obstructions.update(o, surface_ids=["B", "B", "B", "B", "B", "A"])
    assert paint_fields(o, (0, 0, 1), "B") == {"surface_id": "B", "surface_ids": None}


def test_paint_vent_and_refusals(tm, api):
    v = api.vents.add_vent([0, 1, 0, 1, 0, 0], surf_id="OPEN")
    tm.activate("paint")
    assert tm.click(hit(0, 0, entity=("vents", v))) is None and "choose a surface" in tm.take_messages()[0]
    tm.props.paint_surface = "FAN"
    tm.click(hit(0, 0, entity=("vents", v)))
    assert v.surface_id == "FAN"
    assert tm.click(hit(0, 0, entity=("meshes", object()))) is None and "only obstructions" in tm.take_messages()[0]


def test_pick_sets_the_paint_surface_and_remembers_recent(tm, api):
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="A")
    api.obstructions.update(o, surface_ids=["TOP", "SIDE", "BOT"])
    tm.activate("pick")
    assert tm.click(hit(0, 0, normal=(0, 0, 1), entity=("obstructions", o))) == "TOP"
    assert tm.props.paint_surface == "TOP"
    tm.click(hit(0, 0, normal=(1, 0, 0), entity=("obstructions", o)))
    tm.click(hit(0, 0, normal=(0, 0, 1), entity=("obstructions", o)))
    assert tm.props.recent_surfaces == ["TOP", "SIDE"]
    assert tm.click(hit(0, 0)) is None                              # empty space


def test_activate_unknown_tool_and_switching_cancels(tm):
    tm.activate("obstruction")
    tm.click(hit(0, 0))
    tm.activate("wall")
    assert not tm.tools["obstruction"].active()
    with pytest.raises(KeyError):
        tm.activate("lasso")
    assert tm.names()[0] == "select"


def test_on_change_fires_for_redraws(api):
    seen = []
    t = ToolManager(api, on_change=lambda: seen.append(1))
    t.activate("obstruction")
    t.click(hit(0, 0))
    t.move(hit(1, 1))
    assert len(seen) == 3


# -- roam camera --------------------------------------------------------------------------------------------------
def test_roam_directions_and_movement():
    from pyfds.gui.viewport_tools.roam import RoamCamera
    c = RoamCamera(position=(0, 0, 1.7), yaw=0.0, pitch=0.0, step=1.0)
    assert c.forward() == pytest.approx((1, 0, 0)) and c.right() == pytest.approx((0, -1, 0))
    c.move(forward=2)
    assert c.position == pytest.approx((2, 0, 1.7))
    c.move(right=1)                                                   # facing +X, right is -Y
    assert c.position == pytest.approx((2, -1, 1.7))
    c.move(up=1)
    assert c.position[2] == pytest.approx(2.7)
    c.look(90, 0)
    assert c.forward() == pytest.approx((0, 1, 0), abs=1e-9)


def test_roam_pitch_is_clamped_and_walking_follows_the_view():
    from pyfds.gui.viewport_tools.roam import RoamCamera
    c = RoamCamera(position=(0, 0, 5), step=1.0)
    c.look(0, 200)
    assert c.pitch == 89.0
    c.look(0, -400)
    assert c.pitch == -89.0
    c.pitch = -45.0
    c.move(forward=1)
    assert c.position[2] < 5 and c.position[0] > 0                    # forward while looking down descends


def test_roam_from_the_current_camera_and_model_scaled_step():
    from pyfds.gui.viewport_tools.roam import RoamCamera
    c = RoamCamera.looking((0, 0, 0), (0, 5, 5))
    assert c.yaw == pytest.approx(90.0) and c.pitch == pytest.approx(45.0)
    c.set_step_for_model((0, 60, 0, 0, 0, 0))                          # a 60 m long model
    assert c.step == pytest.approx(3.0)
    c.set_step_for_model((0, 0.1, 0, 0.1, 0, 0.1))
    assert c.step == 0.05                                             # never absurdly small
