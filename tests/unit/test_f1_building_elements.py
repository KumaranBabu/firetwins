"""F1: pipes, ramps, beams, doors and windows (api.geom) and the Draw-menu dialogs that add them."""
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.domain.building_elements import pipe_mesh, ramp_mesh, signed_volume


# -- meshes ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("start,end", [((0, 0, 0), (0, 0, 2)), ((0, 0, 0), (3, 0, 0)), ((1, 1, 1), (2, 3, 4))])
def test_pipe_is_a_closed_outward_shape_with_the_right_volume(start, end):
    from pyfds.domain.geometry_repair import inspect
    verts, faces = pipe_mesh(start, end, 0.5, 0.1, segments=48)
    rep = inspect(verts, faces)
    assert rep["closed"] and rep["open_edges"] == 0 and rep["non_manifold_edges"] == 0 and rep["degenerate"] == 0
    exact = math.pi * (0.5 ** 2 - 0.4 ** 2) * math.dist(start, end)
    assert signed_volume(verts, faces) == pytest.approx(exact, rel=0.01)           # 48-gon: within 1 % of a true circle


def test_a_thick_wall_makes_a_solid_rod():
    from pyfds.domain.geometry_repair import inspect
    verts, faces = pipe_mesh((0, 0, 0), (0, 0, 1), 0.2, 0.5, segments=48)
    assert inspect(verts, faces)["closed"] and signed_volume(verts, faces) == pytest.approx(math.pi * 0.04, rel=0.01)


@pytest.mark.parametrize("direction", ["+X", "-X", "+Y", "-Y"])
def test_ramp_is_an_exact_wedge_in_every_direction(direction):
    from pyfds.domain.geometry_repair import inspect
    verts, faces = ramp_mesh((1, 2, 0.5), direction, 4.0, 1.5, 1.0)
    assert inspect(verts, faces)["closed"] and signed_volume(verts, faces) == pytest.approx(4.0 * 1.5 * 1.0 / 2)
    top = max(v[2] for v in verts)
    assert top == pytest.approx(1.5)                                                # climbs from 0.5 to 1.5
    xs, ys = [v[0] for v in verts], [v[1] for v in verts]
    ex, ey = max(xs) - min(xs), max(ys) - min(ys)
    assert (ex, ey) == pytest.approx((4.0, 1.5) if direction in ("+X", "-X") else (1.5, 4.0))


def test_meshes_refuse_nonsense():
    with pytest.raises(ValueError):
        pipe_mesh((0, 0, 0), (0, 0, 0), 0.5, 0.1)
    with pytest.raises(ValueError):
        pipe_mesh((0, 0, 0), (0, 0, 1), -1, 0.1)
    with pytest.raises(ValueError):
        pipe_mesh((0, 0, 0), (0, 0, 1), 0.5, 0.1, segments=3)
    with pytest.raises(ValueError):
        ramp_mesh((0, 0, 0), "UP", 1, 1, 1)
    with pytest.raises(ValueError):
        ramp_mesh((0, 0, 0), "+X", 1, 0, 1)


# -- api ----------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def api():
    return FdsApi()


def test_beams_columns_and_lintels(api):
    b = api.geom.add_beam((0, 0, 3), (4, 0, 3), 0.2, 0.3)
    assert (b.x_min, b.x_max, b.y_min, b.y_max, b.z_min, b.z_max) == pytest.approx((0, 4, -0.1, 0.1, 2.85, 3.15))
    c = api.geom.add_beam((1, 1, 0), (1, 1, 3), 0.3, 0.2)
    assert (c.z_min, c.z_max, c.x_min, c.x_max, c.y_min, c.y_max) == pytest.approx((0, 3, 0.85, 1.15, 0.9, 1.1))
    y = api.geom.add_beam((2, 0, 1), (2, 5, 1), 0.2, 0.2)
    assert (y.y_min, y.y_max) == (0, 5)
    with pytest.raises(ValueError, match="X, Y or Z"):
        api.geom.add_beam((0, 0, 0), (1, 1, 0), 0.2, 0.2)
    with pytest.raises(ValueError):
        api.geom.add_beam((0, 0, 0), (0, 0, 0), 0.2, 0.2)
    with pytest.raises(ValueError):
        api.geom.add_beam((0, 0, 0), (1, 0, 0), 0, 0.2)
    assert [o.name for o in api.obstructions.all()] == ["BEAM", "BEAM_2", "BEAM_3"]


def test_pipe_and_ramp_are_one_undo_step_each(api):
    p = api.geom.add_pipe((0, 0, 0), (0, 0, 2), 0.3, 0.05)
    r = api.geom.add_sloped_ramp((1, 0, 0), "+X", 3, 1.2, 0.5, name="ACCESS")
    assert api.geom.check_geometry(p)["closed"] and api.geom.check_geometry(r)["closed"]
    assert r.name == "ACCESS" and len(api.geom.all()) == 2
    api.history.undo()
    assert [g.name for g in api.geom.all()] == ["PIPE"]
    api.history.undo()
    assert api.geom.all() == []


def test_doors_and_windows_are_holes_through_the_wall(api):
    d = api.geom.add_opening("door", (2, 0, 0))
    assert (d.x_min, d.x_max, d.y_min, d.y_max, d.z_min, d.z_max) == pytest.approx((1.55, 2.45, -0.15, 0.15, 0, 2.1))
    w = api.geom.add_opening("window", (2, 0, 3.0), "Y", wall_thickness=0.4)
    assert (w.x_min, w.x_max) == pytest.approx((1.8, 2.2)) and (w.y_min, w.y_max) == pytest.approx((-0.6, 0.6))
    assert (w.z_min, w.z_max) == pytest.approx((3.9, 5.1))                         # sill 0.9 above the floor at z=3
    big = api.geom.add_opening("door", (5, 0), width=2.0, height=2.5, sill=0.1)
    assert (big.z_min, big.z_max) == pytest.approx((0.1, 2.6))
    assert [h.name for h in api.holes.all()] == ["DOOR", "WINDOW", "DOOR_2"]
    for bad in (dict(kind="gate", centre=(0, 0, 0)), dict(kind="door", centre=(0, 0, 0), wall_axis="Z"),
                dict(kind="door", centre=(0, 0, 0), width=-1), dict(kind="window", centre=(0, 0, 0), sill=-0.5)):
        with pytest.raises(ValueError):
            api.geom.add_opening(**bad)


def test_a_door_really_cuts_the_wall_in_the_fds_text(api):
    api.meshes.add_mesh([40, 10, 20], [0, 4, 0, 1, 0, 2.5])
    api.obstructions.add_obstruction([0, 4, 0, 0.2, 0, 2.5], name="WALL")
    api.geom.add_opening("door", (2, 0.1, 0), wall_thickness=0.4)
    text = api.fds_text()
    assert "&HOLE" in text and "DOOR" in text


# -- the Draw-menu dialogs ------------------------------------------------------------------------------------------------------
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def w(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a[-1]))
    win = MainWindow(FdsApi())
    win.errors = errors
    yield win
    win.close()


def test_defaults_follow_the_first_mesh(w):
    assert w._model_rect() == [0.0, 5.0, 0.0, 5.0]
    w.api.meshes.add_mesh([10, 10, 10], [1, 7, 2, 4, 0, 3], name="M")
    assert w._model_rect() == [1, 7, 2, 4]
    forms = w._element_forms()
    assert forms["floor"]["props"]["x_max"]["default"] == 7 and forms["door"]["props"]["centre"]["default"][:2] == [4.0, 3.0]


def test_floor_and_ceiling_make_slabs_at_the_right_level(w):
    w.api.meshes.add_mesh([10, 10, 10], [0, 4, 0, 3, 0, 3], name="M")
    f = w._draw_element("floor", {})                                              # all defaults
    c = w._draw_element("ceiling", {"thickness": 0.1})
    assert f and c and all(o.z_max <= 0.0 + 1e-9 for o in f) and all(abs(o.z_max - 3.0) < 1e-9 for o in c)
    assert min(o.z_min for o in c) == pytest.approx(2.9)
    assert w._draw_element("floor", {"x_min": 3.0, "x_max": 1.0}) is None and "larger than the minimum" in w.errors[-1]


def test_door_window_beam_pipe_ramp_from_the_forms(w):
    d = w._draw_element("door", {"centre": [2.0, 0.0, 0.0]})
    win = w._draw_element("window", {"centre": [3.0, 0.0, 0.0], "wall_axis": "Y"})
    beam = w._draw_element("beam", {"start": [0, 0, 3], "end": [0, 4, 3]})
    pipe = w._draw_element("pipe", {"outer_radius": 0.1, "wall": 0.01})
    ramp = w._draw_element("ramp", {"direction": "+Y", "rise": 0.4})
    assert d.name == "DOOR" and win.name == "WINDOW" and beam.name == "BEAM" and pipe.name == "PIPE" and ramp.name == "RAMP"
    assert (beam.y_min, beam.y_max) == (0, 4)
    assert w.api.geom.check_geometry(pipe)["closed"] and w.api.geom.check_geometry(ramp)["closed"]


def test_bad_form_values_show_an_error_and_add_nothing(w):
    assert w._draw_element("beam", {"start": [0, 0, 0], "end": [1, 1, 0]}) is None and "X, Y or Z" in w.errors[-1]
    assert w._draw_element("ramp", {"rise": 0}) is None and w.api.geom.all() == []
    assert w._draw_element("door", {"width": -1}) is None and w.api.holes.all() == []


def test_the_draw_menu_entries_are_real_and_open_their_forms(w, monkeypatch):
    from pyfds.gui.main_window import actions_building as ab
    opened = []

    class Fake:
        def __init__(self, title, description, schema, parent=None):
            opened.append(title)

        def exec(self):
            return 0
    monkeypatch.setattr(ab, "SchemaFormDialog", Fake)
    menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Model")
    draw = next(a.menu() for a in menu.actions() if a.menu() is not None and a.text().replace("&", "") == "Draw")
    entries = {a.text().replace("&", ""): a for a in draw.actions()}
    for label in ("Draw Pipe...", "Draw Beam...", "Draw Floor...", "Draw Ceiling...", "Draw Door...", "Draw Window...",
                  "Draw Ramp..."):
        entries[label].trigger()
    assert opened == ["Draw Pipe", "Draw Beam", "Draw Floor", "Draw Ceiling", "Draw Door", "Draw Window", "Draw Ramp"]
    assert not hasattr(w, "_on_placeholder_geometry_primitive")
