"""F3: the Qt-free geometry of the 2D plan view - what shows at a level, what a click hits, the sketch grid."""
import pytest

from pyfds.api import FdsApi
from pyfds.core.viewport import VisibilityFlags
from pyfds.gui.plan import extent, grid_lines, grid_spacing, pick_shape, plan_shapes


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 10, 0, 10, 0, 6], name="M")
    a.obstructions.add_obstruction([1, 3, 1, 3, 0, 2.5], name="low")
    a.obstructions.add_obstruction([5, 7, 5, 7, 3.2, 5.5], name="upper")
    return a


def names(shapes, kind):
    return sorted(s.label for s in shapes if s.kind == kind)


def test_level_and_slab_choose_what_shows(api):
    assert names(plan_shapes(api, 0.0, 3.0), "obstruction") == ["low"]
    first = plan_shapes(api, 0.0, 3.0)
    assert [s.kind for s in first][0] == "mesh"                      # the domain is always there, drawn first
    second = plan_shapes(api, 3.0, 3.0)
    assert names(second, "obstruction") == ["upper"]                 # 'low' ends at 2.5, below the slab


def test_objects_reaching_down_into_the_level_show_faint_only_when_below(api):
    shapes = plan_shapes(api, 2.0, 1.0)
    low = next(s for s in shapes if s.label == "low")
    assert not low.below                                              # it reaches up into the slab
    only = plan_shapes(api, 2.6, 0.3)                                 # slab 2.6..2.9: 'low' ended at 2.5, 'upper' starts at 3.2
    assert names(only, "obstruction") == []


def test_kinds_follow_the_visibility_flags_and_the_explicit_filter(api):
    api.holes.add_hole([4, 5, 4, 5, 0, 2.5], name="door")
    api.vents.add_vent([0, 1, 0, 1, 0, 0], name="floor_vent")
    assert {s.kind for s in plan_shapes(api, 0.0, 3.0)} == {"mesh", "obstruction", "hole", "vent"}
    api.viewport.set_visibility(VisibilityFlags.HOLES, False)
    assert "hole" not in {s.kind for s in plan_shapes(api, 0.0, 3.0)}
    assert {s.kind for s in plan_shapes(api, 0.0, 3.0, visible={"mesh"})} == {"mesh"}


def test_devices_are_points_and_disabled_objects_are_left_out(api):
    api.devices.add_device("TEMPERATURE", [2, 2, 1.0], name="TC1")
    pts = [s for s in plan_shapes(api, 0.0, 3.0) if s.kind == "device"]
    assert len(pts) == 1 and pts[0].is_point and (pts[0].x0, pts[0].y0) == (2, 2)
    api.obstructions.get("low").enabled = False
    assert "low" not in names(plan_shapes(api, 0.0, 3.0), "obstruction")


def test_draw_order_puts_small_things_on_top(api):
    api.holes.add_hole([4, 5, 4, 5, 0, 2.5], name="door")
    order = [s.kind for s in plan_shapes(api, 0.0, 3.0)]
    assert order.index("mesh") < order.index("obstruction") < order.index("hole")


# -- picking ----------------------------------------------------------------------------------------------------------
def test_pick_inside_an_obstruction_but_not_inside_a_mesh(api):
    shapes = plan_shapes(api, 0.0, 3.0)
    assert pick_shape(shapes, 2.0, 2.0, 0.1).label == "low"
    assert pick_shape(shapes, 8.0, 8.0, 0.1) is None                 # inside the domain, nothing there
    assert pick_shape(shapes, 0.05, 5.0, 0.1).kind == "mesh"         # on the domain's edge
    assert pick_shape(shapes, -5, -5, 0.1) is None


def test_pick_prefers_the_smaller_and_the_more_specific_shape(api):
    api.obstructions.add_obstruction([1.5, 2.5, 1.5, 2.5, 0, 1], name="small")
    api.vents.add_vent([1.8, 2.2, 1.8, 2.2, 0, 0], name="v")
    shapes = plan_shapes(api, 0.0, 3.0)
    assert pick_shape(shapes, 2.0, 2.0, 0.05).label == "v"           # a vent on top of the boxes
    assert pick_shape(shapes, 1.6, 1.6, 0.05).label == "small"       # smaller of the two overlapping boxes
    assert pick_shape(shapes, 1.1, 1.1, 0.05).label == "low"


def test_pick_tolerance_for_thin_things(api):
    api.vents.add_vent([4, 4, 1, 3, 0, 2], name="wall_vent")        # zero width in X
    shapes = plan_shapes(api, 0.0, 3.0)
    assert pick_shape(shapes, 4.05, 2.0, 0.1).label == "wall_vent"
    assert pick_shape(shapes, 4.5, 2.0, 0.1) is None


# -- grid -------------------------------------------------------------------------------------------------------------
def test_grid_spacing_coarsens_when_zoomed_out():
    assert grid_spacing(0.1, 100.0) == pytest.approx(0.2)            # 0.1 m would be 10 px apart: doubled
    assert grid_spacing(0.1, 1000.0) == pytest.approx(0.1)           # plenty of room: the snap grid itself
    assert grid_spacing(0.1, 20.0) == pytest.approx(1.0)
    assert grid_spacing(0.1, 1.0) == pytest.approx(20.0)             # 1 px per metre -> lines at least 12 m apart


def test_grid_lines_are_multiples_and_capped():
    assert grid_lines(0.05, 0.55, 0.1) == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])
    assert grid_lines(-0.25, 0.25, 0.25) == pytest.approx([-0.25, 0.0, 0.25])
    assert grid_lines(0, 1e9, 0.1) == []                              # a runaway zoom asks for nothing, not millions
    assert grid_lines(1, 0, 0.1) == [] and grid_lines(0, 1, 0) == []


def test_extent(api):
    assert extent(plan_shapes(api, 0.0, 3.0)) == (0, 0, 10, 10)
    assert extent([]) is None
