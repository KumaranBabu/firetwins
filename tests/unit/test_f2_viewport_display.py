"""F2: render modes, mesh display modes and slice planes in the viewport scene (pure data, no display needed)."""
import pytest

from pyfds.api import FdsApi
from pyfds.core.viewport import VisibilityFlags


def _make_api():
    return FdsApi()


# -- F2: render modes, mesh display, slices ---------------------------------------------------------------
def test_render_modes_set_edges_and_smoothing():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    pick = lambda: next(s for s in build_scene(api) if s.entity_kind == "obstruction")
    assert (pick().style, pick().edges, pick().smooth) == ("surface", False, False)
    api.viewport.set_render_mode("outlines")
    assert pick().edges and pick().style == "surface"
    api.viewport.set_render_mode("realistic")
    assert pick().smooth and not pick().edges
    api.viewport.set_render_mode("wireframe")
    assert pick().style == "wireframe" and api.viewport.state.show_wireframe
    api.viewport.set_render_mode("solid")
    assert not api.viewport.state.show_wireframe
    with pytest.raises(ValueError):
        api.viewport.set_render_mode("glow")


def test_wireframe_toggle_and_render_mode_stay_in_step():
    api = _make_api()
    api.viewport.toggle_wireframe()
    assert api.viewport.state.render_mode == "wireframe"
    api.viewport.toggle_wireframe()
    assert api.viewport.state.render_mode == "solid"


def test_mesh_display_modes():
    from pyfds.gui.viewport_scene import build_scene, mesh_grid_lines
    api = _make_api()
    api.meshes.add_mesh([4, 2, 2], [0, 4, 0, 2, 0, 2], name="m")
    kinds = lambda: [s.entity_kind for s in build_scene(api) if s.entity_kind.startswith("mesh")]
    assert kinds() == ["mesh"]
    api.viewport.set_mesh_display("lines")
    assert kinds() == ["mesh", "mesh-lines"]
    lines = next(s for s in build_scene(api) if s.entity_kind == "mesh-lines")
    assert lines.helper and lines.mesh.n_cells == 2 * (6 + 8 + 8)      # (n+1) lines each way on the two faces of every axis
    api.viewport.set_mesh_display("boundary")
    assert kinds() == ["mesh", "mesh-shell"]
    api.viewport.set_mesh_display("hidden")
    assert kinds() == []
    assert not api.viewport.state.is_visible(VisibilityFlags.MESHES)
    api.viewport.set_mesh_display("outline")
    assert kinds() == ["mesh"] and api.viewport.state.is_visible(VisibilityFlags.MESHES)
    with pytest.raises(ValueError):
        api.viewport.set_mesh_display("dots")


def test_grid_lines_are_capped_for_fine_meshes():
    from pyfds.gui.viewport_scene import mesh_grid_lines
    api = _make_api()
    m = api.meshes.add_mesh([1000, 1000, 1000], [0, 10, 0, 10, 0, 10], name="fine")
    assert mesh_grid_lines(m).n_cells < 6 * 2 * 125 * 2     # at most ~121 lines per direction on each face


def test_slices_follow_their_flag_and_sit_at_their_position():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.meshes.add_mesh([4, 4, 4], [0, 4, 0, 4, 0, 4], name="m")
    api.slices.add_slice("TEMPERATURE", "Y", 2.0)
    s = next(s for s in build_scene(api) if s.entity_kind == "slice")
    b = s.mesh.bounds
    assert b[2] == pytest.approx(2.0, abs=1e-2) and b[3] == pytest.approx(2.0, abs=1e-2) and b[1] == pytest.approx(4.0)
    api.viewport.set_visibility(VisibilityFlags.SLICES, False)
    assert not [s for s in build_scene(api) if s.entity_kind == "slice"]
