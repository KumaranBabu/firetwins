"""B2 — wall/slab/room/curved wall/stairs/roof/truss generators, boolean, block conversion,
particle clouds. Each public operation is one undo step."""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain import building_shapes as bs
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(40, 40, 20), xb=(0, 4, 0, 4, 0, 2), name="M")
    return a


def _vol(boxes):
    return sum((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in boxes)


def _xb(o):
    return (o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max)


def _undo_one(api, op, count):
    n0 = count()
    op()
    assert count() > n0
    api.history.undo()
    assert count() == n0
    api.history.redo()
    assert count() > n0


# -- pure shapes ----------------------------------------------------------------------------
def test_straight_wall_is_one_exact_box():
    (b,) = bs.wall([(0, 0), (3, 0)], 0.2, 0, 2.5, "C")
    assert b == pytest.approx((0, 3, -0.1, 0.1, 0, 2.5))


@pytest.mark.parametrize("align,y0,y1", [("L", 0, 0.2), ("R", -0.2, 0), ("C", -0.1, 0.1)])
def test_wall_alignment(align, y0, y1):
    (b,) = bs.wall([(0, 0), (3, 0)], 0.2, 0, 1, align)
    assert (b[2], b[3]) == pytest.approx((y0, y1))


def test_l_shaped_wall_corner_is_filled():
    boxes = bs.wall([(0, 0), (2, 0), (2, 2)], 0.2, 0, 1, "C")
    # the outer corner square (2.0..2.1, -0.1..0) must be covered
    assert any(b[0] <= 2.0 + 1e-9 and b[1] >= 2.1 - 1e-9 and b[2] <= -0.1 + 1e-9 and b[3] >= 0 for b in boxes)
    # no overshoot beyond the outer face
    assert max(b[1] for b in boxes) == pytest.approx(2.1)
    assert min(b[2] for b in boxes) == pytest.approx(-0.1)


def test_diagonal_wall_is_stair_stepped_and_close_in_area():
    boxes = bs.wall([(0, 0), (3, 3)], 0.3, 0, 1, "C", res=0.05)
    assert len(boxes) > 5
    expected = 3 * 2 ** 0.5 * 0.3          # length x thickness (footprint), height 1
    assert _vol(boxes) == pytest.approx(expected, rel=0.1)


def test_curved_wall_ring_area():
    boxes = bs.curved_wall((0, 0), 2.0, 0, 360, 0.2, 0, 1, res=0.05)
    area = 3.14159265 * ((2.1 ** 2) - (1.9 ** 2))
    assert _vol(boxes) == pytest.approx(area, rel=0.15)


def test_slab_rectangle_is_one_box_and_polygon_is_rasterised():
    (b,) = bs.slab([(0, 0), (2, 0), (2, 3), (0, 3)], 0.0, 0.2)
    assert b == pytest.approx((0, 2, 0, 3, -0.2, 0))
    tri = bs.slab([(0, 0), (2, 0), (0, 2)], 1.0, 0.1, res=0.05)
    assert _vol(tri) == pytest.approx(2 * 0.1, rel=0.1)


def test_room_parts_and_interior():
    parts, inner = bs.room(0, 4, 0, 3, 0, 2.5, 0.2, "inside", 0.1, 0.1)
    names = [p for p, _ in parts]
    assert names == ["S", "N", "W", "E", "floor", "ceiling"]
    assert inner == pytest.approx((0.2, 3.8, 0.2, 2.8, 0, 2.5))
    outside = bs.room(0, 4, 0, 3, 0, 2.5, 0.2, "outside")[1]
    assert outside == pytest.approx((0, 4, 0, 3, 0, 2.5))
    with pytest.raises(ValueError):
        bs.room(0, 0.3, 0, 3, 0, 2, 0.2)


def test_stairs_heights_and_direction():
    s = bs.stairs(0, 0, 0, "+X", 1.0, 3, 0.2, 0.3, landing=1.0)
    assert [b[5] for b in s] == pytest.approx([0.2, 0.4, 0.6, 0.6])
    assert s[0][:2] == pytest.approx((0, 0.3)) and s[-1][:2] == pytest.approx((0.9, 1.9))
    n = bs.stairs(1, 1, 0, "-Y", 1.0, 2, 0.2, 0.3)
    assert n[1][2:4] == pytest.approx((0.4, 0.7)) or n[1][2:4] == pytest.approx((1 - 0.6, 1 - 0.3))


def test_gable_roof_rises_to_ridge_and_is_symmetric():
    boxes = bs.roof(0, 4, 0, 6, 3.0, 30, 0.2, "gable", "X", res=0.1)
    top = max(b[5] for b in boxes)
    assert top == pytest.approx(3.0 + 3 * 0.57735 + 0.2, abs=0.05)
    low = min(b[4] for b in boxes)
    assert low == pytest.approx(3.0, abs=0.06)
    shed = bs.roof(0, 4, 0, 6, 3.0, 20, 0.2, "shed", "X", res=0.1)
    assert max(b[5] for b in shed) == pytest.approx(3.0 + 6 * 0.36397 + 0.2, abs=0.05)


def test_truss_spans_and_rises():
    boxes = bs.truss(0, 0, 3, 6, 1.5, 6, 0.1, 0.1, "X", res=0.025)
    assert min(b[0] for b in boxes) == pytest.approx(0, abs=0.03)
    assert max(b[1] for b in boxes) == pytest.approx(6, abs=0.03)
    assert max(b[5] for b in boxes) == pytest.approx(3 + 0.1 + 1.5, abs=0.06)
    assert {round(b[2], 6) for b in boxes} == {-0.05} and {round(b[3], 6) for b in boxes} == {0.05}


@pytest.mark.parametrize("call", [
    lambda: bs.wall([(0, 0)], 0.2, 0, 1),
    lambda: bs.wall([(0, 0), (1, 0)], 0.2, 0, 1, "X"),
    lambda: bs.stairs(0, 0, 0, "UP", 1, 2, 0.2, 0.3),
    lambda: bs.roof(0, 1, 0, 1, 0, 90, 0.1),
    lambda: bs.truss(0, 0, 0, 5, 1, 1, 0.1, 0.1),
    lambda: bs.rasterize([(0, 0), (1, 0)], 0.1),
])
def test_bad_input_is_refused(call):
    with pytest.raises(ValueError):
        call()


# -- API -------------------------------------------------------------------------------------
def test_add_wall_is_one_undo_step(api):
    _undo_one(api, lambda: api.geom.add_wall([(0.5, 0.5), (3.5, 0.5), (3.5, 3.5)], 0.2, 2.0, surf_id="CONCRETE"),
              lambda: len(api.obstructions.all()))
    walls = api.geom.add_wall([(0.5, 0.5), (3.5, 0.5)], 0.2, 2.0, name="W")
    assert walls[0].surface_id == "CONCRETE" or walls[0].surface_id == "INERT"
    assert walls[0].name.startswith("W_")


def test_names_are_unique_across_calls(api):
    a = api.geom.add_wall([(0, 0), (1, 0)], 0.2, 1, name="W")
    b = api.geom.add_wall([(0, 1), (1, 1)], 0.2, 1, name="W")
    assert a[0].name != b[0].name


def test_default_resolution_is_mesh_cell_size(api):
    assert api.geom._resolution(None) == pytest.approx(0.1)
    assert api.geom._resolution(0.25) == 0.25
    with pytest.raises(ValueError):
        api.geom._resolution(-1)
    assert FdsApi().geom._resolution(None) == 0.1


def test_add_room_with_door_and_window_is_one_undo_step(api):
    def op():
        return api.geom.add_room([0.5, 3.5, 0.5, 3.5], 2.5, 0.2, floor_thickness=0.1,
                                 openings=[{"side": "S", "centre": 2.0, "width": 0.9, "height": 2.0},
                                           {"side": "E", "centre": 2.0, "width": 1.0, "height": 1.0, "sill": 1.0}])
    _undo_one(api, op, lambda: len(api.obstructions.all()) + len(api.holes.all()))
    r = op()
    assert len(r["walls"]) == 5 and len(r["holes"]) == 2
    door = _xb(r["holes"][0])
    assert door[0] == pytest.approx(1.55) and door[1] == pytest.approx(2.45) and door[4] == 0 and door[5] == 2.0
    window = _xb(r["holes"][1])
    assert window[4] == pytest.approx(1.0) and window[5] == pytest.approx(2.0)
    # the hole actually crosses the wall thickness
    wall_s = _xb(r["walls"][0])
    assert door[2] == wall_s[2] and door[3] == wall_s[3]      # spans the full wall thickness, inside the wall box
    assert not [x for x in api.validation.validate().results if x.rule == 'HoleContainment']


def test_add_room_bad_opening_leaves_nothing(api):
    n = len(api.obstructions.all())
    with pytest.raises(ValueError):
        api.geom.add_room([0.5, 3.5, 0.5, 3.5], 2.5, openings=[{"side": "Q", "centre": 1, "width": 1, "height": 1}])
    assert len(api.obstructions.all()) == n and not api.holes.all()


def test_stairs_roof_truss_curved_slab_via_api(api):
    cnt = lambda: len(api.obstructions.all())
    _undo_one(api, lambda: api.geom.add_stairs(0.5, 1, 0, "+X", 1, 5), cnt)
    _undo_one(api, lambda: api.geom.add_roof([0, 4, 0, 4], 2.0, 25), cnt)
    _undo_one(api, lambda: api.geom.add_truss(0.5, 2, 1.5, 3, 0.8), cnt)
    _undo_one(api, lambda: api.geom.add_curved_wall([2, 2], 1.0, 0, 180, 0.2, 2.0), cnt)
    _undo_one(api, lambda: api.geom.add_slab([(0, 0), (3, 0), (3, 2), (1, 3)], 0.0, 0.2), cnt)


def test_generated_geometry_round_trips_through_fds(api, tmp_path):
    api.geom.add_room([0.5, 3.5, 0.5, 3.5], 2.5, 0.2, openings=[{"side": "N", "centre": 2, "width": 1, "height": 2}])
    out = tmp_path / "room.fds"
    FdsWriter().write(api.project, str(out))
    again = FdsParser().parse(str(out))
    assert len(again.obstructions) == len(api.obstructions.all())
    assert len(again.holes) == 1


def test_boolean_is_one_undo_step_and_optionally_removes_inputs(api):
    pytest.importorskip("pyvista")
    a = api.geom.box([0, 2, 0, 2, 0, 2], name="A")
    b = api.geom.box([1, 3, 1, 3, 0, 2], name="B")
    n = len(api.geom.all())
    out = api.geom.boolean("union", "A", "B", name="U")
    assert out.name == "U" and len(api.geom.all()) == n + 1
    api.history.undo()
    assert len(api.geom.all()) == n
    api.geom.boolean("difference", a, b, name="D", remove_inputs=True)
    assert [g.name for g in api.geom.all()] == ["D"]
    api.history.undo()
    assert len(api.geom.all()) == n
    with pytest.raises(ValueError):
        api.geom.boolean("union", a, a)
    with pytest.raises(KeyError):
        api.geom.boolean("union", "A", "nope")
    with pytest.raises(ValueError):
        api.geom.boolean("xor", a, b)


def test_convert_to_blocks_and_preview(api):
    pytest.importorskip("pyvista")
    g = api.geom.box([0.5, 1.5, 0.5, 1.5, 0.5, 1.5], name="G", surf_id="STEEL")
    prev = api.geom.preview_blocks("G", mode="solid")
    assert prev["count"] > 0 and len(prev["boxes"]) == prev["count"]
    assert not api.obstructions.all()                          # preview changes nothing
    api.history.clear()
    blocks = api.geom.convert_to_blocks("G", mode="solid")
    assert len(blocks) == prev["count"] and all(o.surface_id == "STEEL" for o in blocks)
    assert not api.geom.all()
    api.history.undo()
    assert api.geom.all() and not api.obstructions.all()       # one step restores the geom
    kept = api.geom.convert_to_blocks("G", remove_geom=False)
    assert kept and api.geom.all()


def test_particle_cloud(api):
    from pyfds.domain.model import Particle
    api.project.particles.append(Particle(name="SOOT_P"))
    c = api.inits.add_particle_cloud([0, 1, 0, 1, 0, 1], "SOOT_P", n_particles=500)
    assert c.part_id == "SOOT_P" and c.n_particles == 500
    with pytest.raises(ValueError):
        api.inits.add_particle_cloud([0, 1, 0, 1, 0, 1], "SOOT_P")
    with pytest.raises(ValueError):
        api.inits.add_particle_cloud([0, 1, 0, 1, 0, 1], "SOOT_P", n_particles=5, n_particles_pua=2.0)
    with pytest.raises(KeyError):
        api.inits.add_particle_cloud([0, 1, 0, 1, 0, 1], "MISSING", n_particles=5)


def test_agent_tools(api):
    d = AgentToolDispatcher(api)
    r = d.call("add_room", {"xb": [0.5, 3.5, 0.5, 3.5], "height": 2.5,
                            "openings": [{"side": "S", "centre": 2, "width": 1, "height": 2}]})
    assert len(r["walls"]) == 4 and len(r["holes"]) == 1
    assert len(d.call("add_stairs", {"x": 1, "y": 1, "z": 0, "direction": "+X", "width": 1, "steps": 4})) == 4
    assert d.call("add_wall", {"path": [[0, 0], [2, 0]], "thickness": 0.2, "height": 2})
    assert d.call("add_roof", {"xb": [0, 4, 0, 4], "z_eave": 2, "pitch_deg": 20})
    assert d.call("add_truss", {"x": 0.5, "y": 2, "z": 1.5, "span": 3, "rise": 0.8})
    assert d.call("add_curved_wall", {"center": [2, 2], "radius": 1, "start_deg": 0, "end_deg": 90,
                                      "thickness": 0.2, "height": 2})
    assert d.call("add_slab", {"polygon": [[0, 0], [2, 0], [2, 2]], "z_top": 0, "thickness": 0.2})
    if True:
        pytest.importorskip("pyvista")
        d.call("add_stairs", {"x": 1, "y": 3, "z": 0, "direction": "+Y", "width": 1, "steps": 2})
        api.geom.box([0.5, 1.5, 0.5, 1.5, 0.5, 1.5], name="G")
        assert d.call("preview_blocks", {"geom": "G"})["count"] > 0
        assert d.call("convert_to_blocks", {"geom": "G"})
