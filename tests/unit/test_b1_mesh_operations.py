"""B1 — mesh operations: refine, split, merge, move/scale/mirror/rotate, refinement zone,
stretching, open boundaries, statistics. Each public operation is one undo step."""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.api.mesh_ops import subtract_rects
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.fds_parser import FdsParser


def _box(m):
    return (m.x_min, m.x_max, m.y_min, m.y_max, m.z_min, m.z_max)


def _cells(api):
    return sum(s["total_cells"] for s in (api.meshes.stats(m) for m in api.meshes.all()))


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(20, 10, 10), xb=(0, 4, 0, 2, 0, 2), name="M")
    return a


def _one_undo_restores(api, op, snapshot):
    before = snapshot()
    op()
    assert snapshot() != before
    api.history.undo()
    assert snapshot() == before
    api.history.redo()
    assert snapshot() != before


def _snap(api):
    return lambda: [(m.name, _box(m), m.cell_count) for m in api.meshes.all()]


# ----------------------------------------------------------------- stats / MSH-03
def test_stats_cell_size_aspect_and_totals(api):
    s = api.meshes.stats("M")
    assert s["cell_size"] == pytest.approx((0.2, 0.2, 0.2)) and s["total_cells"] == 2000
    assert s["aspect_ratio"] == pytest.approx(1.0) and s["uniform"]
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(4, 5, 0, 2, 0, 2), name="N")
    assert api.meshes.project_stats() == {"meshes": 2, "total_cells": 2064,
                                          "per_mesh": {"M": 2000, "N": 64}}


def test_set_stretching_replaces_axis_points_and_flags_non_uniform(api):
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(5, 6, 0, 1, 0, 1), name="N")
    api.meshes.set_stretching("N", "X", [(5.0, 0.0), (6.0, 1.0)])
    assert [(t.direction, t.mesh_number, t.cc, t.pc) for t in api.project.mesh_transforms] == \
        [("X", 2, 5.0, 0.0), ("X", 2, 6.0, 1.0)]
    assert api.meshes.stats("N")["non_uniform_axes"] == ["X"] and not api.meshes.stats("N")["uniform"]
    api.meshes.set_stretching("N", "X", [(5.5, 0.5)])                 # replaces, never appends
    assert len(api.project.mesh_transforms) == 1
    api.meshes.set_stretching("N", "X", [])
    assert api.project.mesh_transforms == [] and api.meshes.stats("N")["uniform"]
    api.history.undo()
    assert len(api.project.mesh_transforms) == 1                        # whole replacement = one step


def test_mesh_number_follows_priority_order(api):
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(5, 6, 0, 1, 0, 1), name="N")
    assert api.meshes.mesh_number("N") == 2
    api.meshes.set_order(["N", "M"])
    assert api.meshes.mesh_number("N") == 1


# ----------------------------------------------------------------- refine MSH-08
def test_refine_one_cell_becomes_eight_and_is_one_step(api):
    _one_undo_restores(api, lambda: api.meshes.refine("M", 2), _snap(api))
    assert api.meshes.get("M").cell_count == (40, 20, 20)
    assert api.meshes.stats("M")["total_cells"] == 2000 * 8
    for bad in (1, 0, 2.5):
        with pytest.raises(ValueError):
            api.meshes.refine("M", bad)
    with pytest.raises(KeyError):
        api.meshes.refine("NOPE")


# ----------------------------------------------------------------- split MSH-06
def test_split_keeps_cells_and_total_and_snaps_to_boundary(api):
    total = _cells(api)
    new = api.meshes.split("M", "X", 1.03)                    # nearest boundary is x = 1.0
    m = api.meshes.get("M")
    assert (m.x_max, m.cell_count[0], new.x_min, new.x_max, new.cell_count[0]) == (1.0, 5, 1.0, 4.0, 15)
    assert new.name == "M_2" and _cells(api) == total
    assert api.meshes.stats("M")["cell_size"] == pytest.approx(api.meshes.stats(new)["cell_size"])
    api.history.undo()
    assert api.meshes.count() == 1 and api.meshes.get("M").x_max == 4.0 and api.meshes.get("M").cell_count == (20, 10, 10)


def test_split_default_middle_other_axis_and_rank(api):
    api.meshes.get("M").mpi_processor = 0
    new = api.meshes.split("M", "Z")
    assert (api.meshes.get("M").z_max, new.z_min, new.mpi_processor) == (1.0, 1.0, 1)
    with pytest.raises(ValueError):
        api.meshes.split("M", "X", 9.0)
    with pytest.raises(ValueError):
        api.meshes.split("M", "X", 0.0)                       # on the edge: nothing to split
    with pytest.raises(ValueError, match="axis"):
        api.meshes.split("M", "W")
    api.meshes.add_mesh(ijk=(1, 1, 1), xb=(9, 10, 0, 1, 0, 1), name="ONE")
    with pytest.raises(ValueError, match="only 1 cell"):
        api.meshes.split("ONE", "X")


# ----------------------------------------------------------------- merge MSH-10
def test_merge_undoes_a_split(api):
    api.meshes.split("M", "X", 2.0)
    api.meshes.split("M_2", "Y", 1.0)
    assert api.meshes.count() == 3 and _cells(api) == 2000
    keep = api.meshes.merge(["M", "M_2", "M_2_2"], new_name="WHOLE")
    assert api.meshes.count() == 1 and keep.name == "WHOLE"
    assert _box(keep) == (0, 4, 0, 2, 0, 2) and keep.cell_count == (20, 10, 10)
    api.history.undo()
    assert api.meshes.count() == 3 and api.meshes.get("M").name == "M"


def test_merge_rejects_gaps_overlaps_and_cell_size_mismatch(api):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(5, 7, 0, 2, 0, 2), name="GAP")            # gap 4..5
    with pytest.raises(ValueError, match="exactly fill"):
        api.meshes.merge(["M", "GAP"])
    api.meshes.add_mesh(ijk=(20, 10, 10), xb=(4, 8, 0, 2, 0, 2), name="COARSE")
    api.meshes.get("COARSE").cell_count = (10, 10, 10)                                   # 0.4 vs 0.2
    with pytest.raises(ValueError, match="different cell size"):
        api.meshes.merge(["M", "COARSE"])
    with pytest.raises(ValueError):
        api.meshes.merge(["M"])
    with pytest.raises(ValueError):
        api.meshes.merge(["M", "M"])


# ----------------------------------------------------------------- move / scale / mirror / rotate
def test_move_scale_one_step_each(api):
    _one_undo_restores(api, lambda: api.meshes.move("M", 1, 2, 3), _snap(api))
    assert _box(api.meshes.get("M")) == (1, 5, 2, 4, 3, 5)
    _one_undo_restores(api, lambda: api.meshes.scale("M", 2.0), _snap(api))
    assert _box(api.meshes.get("M")) == (2, 10, 4, 8, 6, 10) and api.meshes.get("M").cell_count == (20, 10, 10)
    with pytest.raises(ValueError):
        api.meshes.scale("M", 0)


def test_mirror_in_place_and_as_copy(api):
    api.meshes.mirror("M", "X", 0.0)
    assert _box(api.meshes.get("M")) == (-4, 0, 0, 2, 0, 2)
    api.history.undo()
    twin = api.meshes.mirror("M", "X", 0.0, copy=True, new_name="TWIN")
    assert twin.name == "TWIN" and _box(twin) == (-4, 0, 0, 2, 0, 2) and api.meshes.count() == 2
    assert _box(api.meshes.get("M")) == (0, 4, 0, 2, 0, 2)
    assert api.meshes.mirror("M", "Z", 1.0).z_min == 0.0                  # symmetric about its own middle


def test_rotate_quarter_turn_swaps_extents_and_counts(api):
    api.meshes.rotate("M", 90)
    m = api.meshes.get("M")
    assert _box(m) == pytest.approx((-2, 0, 0, 4, 0, 2)) and m.cell_count == (10, 20, 10)
    api.meshes.rotate("M", 180)                                              # now back-and-around
    assert _box(api.meshes.get("M")) == pytest.approx((0, 2, -4, 0, 0, 2))
    with pytest.raises(ValueError, match="90"):
        api.meshes.rotate("M", 45)
    api.history.undo()
    assert _box(api.meshes.get("M")) == pytest.approx((-2, 0, 0, 4, 0, 2))


# ----------------------------------------------------------------- refinement zone MSH-09
def test_refinement_zone_tiles_the_original_and_adds_cells_only_inside(api):
    coarse_total = _cells(api)
    pieces = api.meshes.apply_refinement("M", [1, 2, 0.5, 1.5, 0.5, 1.5], factor=2)
    core = pieces[0]
    assert _box(core) == pytest.approx((1, 2, 0.4, 1.6, 0.4, 1.6))      # snapped outward to 0.2 cells
    assert core.cell_count == (10, 12, 12)
    assert api.meshes.stats(core)["cell_size"] == pytest.approx((0.1, 0.1, 0.1))
    # the union is still the original box: volumes add up, nothing overlaps
    vol = lambda m: (m.x_max - m.x_min) * (m.y_max - m.y_min) * (m.z_max - m.z_min)
    assert sum(vol(m) for m in api.meshes.all()) == pytest.approx(4 * 2 * 2)
    assert api.meshes.count() == 7                                           # core + 6 slabs
    refined_core_cells = 10 * 12 * 12
    coarse_core_cells = 5 * 6 * 6
    assert _cells(api) == coarse_total - coarse_core_cells + refined_core_cells
    assert api.meshes.alignment_test() == {m.name: "Passed" for m in api.meshes.all()}
    api.history.undo()                                                          # ONE step undoes all of it
    assert api.meshes.count() == 1 and api.meshes.get("M").cell_count == (20, 10, 10)


def test_refinement_zone_touching_edges_makes_fewer_pieces(api):
    pieces = api.meshes.apply_refinement("M", [0, 1, 0, 2, 0, 2], factor=2)       # corner slab only
    assert len(pieces) == 2 and api.meshes.count() == 2
    with pytest.raises(ValueError):
        api.meshes.apply_refinement(pieces[1], [50, 60, 0, 1, 0, 1])
    with pytest.raises(ValueError):
        api.meshes.apply_refinement(pieces[0], [0, 1], 2)


# ----------------------------------------------------------------- open boundaries MSH-11
def test_open_boundaries_single_mesh_six_faces_idempotent_and_valid(api, tmp_path):
    vents = api.meshes.open_boundaries()
    assert len(vents) == 6 and {v.surface_id for v in vents} == {"OPEN"}
    assert api.meshes.open_boundaries() == []                                  # second run adds nothing
    api.history.undo()
    assert api.vents.count() == 0                                              # six vents = one step
    api.history.redo()
    assert api.vents.count() == 6
    out = tmp_path / "o.fds"
    FdsWriter().write(api.project, str(out))
    back = FdsParser().parse(str(out))
    assert len(back.vents) == 6
    assert not [r for r in api.validation.validate().results if r.rule == "VentCoplanar"]


def test_open_boundaries_skips_shared_faces_and_handles_partial_overlap(api):
    api.meshes.split("M", "X", 2.0)                                            # two abutting halves
    vents = api.meshes.open_boundaries()
    assert len(vents) == 10                                                    # 2 x 6 faces - the 2 shared ones
    api.history.undo()
    api.meshes.add_mesh(ijk=(10, 5, 10), xb=(4, 6, 0, 1, 0, 2), name="SIDE")   # half the height of M_2's +x face
    exposed = [v for v in api.meshes.open_boundaries() if v.name.startswith("M_2_XMAX")]
    assert len(exposed) == 1 and (exposed[0].y_min, exposed[0].y_max) == (1.0, 2.0)   # only the uncovered half


def test_subtract_rects_exact():
    rest = subtract_rects((0, 4, 0, 4), [(1, 3, 1, 3)])
    assert sum((u1 - u0) * (v1 - v0) for u0, u1, v0, v1 in rest) == pytest.approx(16 - 4)
    assert subtract_rects((0, 1, 0, 1), [(0, 1, 0, 1)]) == []
    assert subtract_rects((0, 1, 0, 1), [(5, 6, 5, 6)]) == [(0, 1, 0, 1)]


# ----------------------------------------------------------------- agent tools
def test_agent_tools_for_mesh_operations(api):
    d = AgentToolDispatcher(api)
    d.call("split_mesh", {"mesh": "M", "axis": "X", "at": 2.0})
    d.call("refine_mesh", {"mesh": "M", "factor": 2})
    d.call("move_mesh", {"mesh": "M_2", "dx": 1.0})
    d.call("scale_mesh", {"mesh": "M_2", "factor": 1.0})
    d.call("mirror_mesh", {"mesh": "M", "axis": "Y", "at": 1.0, "copy": True, "new_name": "MIR"})
    d.call("rotate_mesh", {"mesh": "MIR", "angle": 180})
    d.call("set_mesh_stretching", {"mesh": "M", "axis": "X", "points": [[0.0, 0.0], [2.0, 1.0]]})
    assert d.call("mesh_stats", {})["project"]["meshes"] == 3
    assert d.call("open_mesh_boundaries", {"meshes": ["M"]})
    api.history.undo()
    api.meshes.remove(api.meshes.get("MIR"))
    d.call("apply_mesh_refinement", {"mesh": "M", "xb": [0, 1, 0, 1, 0, 1], "factor": 2})
    api.meshes.clear()
    api.meshes.add_mesh(ijk=(4, 4, 4), xb=(0, 1, 0, 1, 0, 1), name="A")
    d.call("split_mesh", {"mesh": "A", "axis": "X"})
    assert d.call("merge_meshes", {"meshes": ["A", "A_2"], "new_name": "AB"})["name"] == "AB"
