"""P0 partial rows, batch 3: clipboard (UX-03), snapping (UX-04), visibility (UX-08), number format (FIO-01)."""
from __future__ import annotations

import math

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain import snapping as sn
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 5, 0, 5, 0, 5), name="M")
    return a


def _save_load(api, tmp_path):
    f = str(tmp_path / "p.pyfds")
    Serializer().save(api.project, f)
    return Serializer().load(f)


# -- UX-03 clipboard -------------------------------------------------------------------------
def test_copy_paste_in_same_model_offsets_and_renames(api):
    o = api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="BOX")
    text = api.clipboard.copy([o])
    assert text.startswith("&OBST") and "ID='BOX'" in text
    rep = api.clipboard.paste((2.0, 0.0, 0.0))
    (new,) = rep["added"]
    assert new.name == "BOX_2" and rep["renamed"] == {"BOX": "BOX_2"}
    assert (new.x_min, new.x_max) == (3.0, 4.0) and (new.z_min, new.z_max) == (0.0, 1.0)
    assert len(api.obstructions.all()) == 2
    api.history.undo()
    assert len(api.obstructions.all()) == 1


def test_paste_into_another_model_with_dependencies(api):
    api.library.add_to_model("surfaces", "gypsum_wall_12mm")
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="GYPSUM_WALL_12MM", name="W")
    other = FdsApi()
    text = api.clipboard.to_fds_text([o], include_dependencies=True)
    assert "&SURF" in text and "&MATL" in text
    rep = other.clipboard.paste_fds_text(text)
    assert {e.name for e in rep["added"]} == {"W", "GYPSUM_WALL_12MM", "GYP_BOARD"}
    assert other.surfaces.get("GYPSUM_WALL_12MM").layers[0].material_id == "GYP_BOARD"
    again = other.clipboard.paste_fds_text(text)                   # surface+material reused, obst renamed
    assert [e.name for e in again["added"]] == ["W_2"] and len(again["skipped"]) == 2
    other.history.undo()
    assert len(other.obstructions.all()) == 1


def test_paste_fds_text_from_outside(api):
    rep = api.clipboard.paste_fds_text("&OBST XB=0,1,0,1,0,1, SURF_ID='INERT', ID='X'/\n"
                                       "&VENT XB=0,5,0,5,0,0, SURF_ID='OPEN'/")
    assert len(rep["added"]) == 2 and len(api.vents.all()) == 1
    assert len(api.history.entries()) >= 1
    n = len(api.history.entries())
    api.clipboard.paste_fds_text("&HOLE XB=0,1,0,1,0,1 /")
    assert len(api.history.entries()) == n + 1


@pytest.mark.parametrize("text", ["", "this is not fds", "&HEAD CHID='x'/"])
def test_paste_rejects_text_without_objects(api, text):
    with pytest.raises(ValueError):
        api.clipboard.paste_fds_text(text)
    assert not api.obstructions.all()


def test_copy_errors(api):
    with pytest.raises(ValueError):
        api.clipboard.copy([])
    with pytest.raises(ValueError):
        api.clipboard.paste()
    from pyfds.domain.model import Obstruction
    with pytest.raises(KeyError):
        api.clipboard.copy([Obstruction(name="stray")])
    with pytest.raises(ValueError):
        api.clipboard.paste_fds_text("&OBST XB=0,1,0,1,0,1 /", offset=(1, 2))


def test_copy_ramp_and_device_keep_working(api):
    api.ramps.add_ramp("R", [0, 1], [0, 1])
    text = api.clipboard.copy([api.ramps.get("R")])
    assert text.count("&RAMP") == 2
    other = FdsApi()
    other.clipboard.paste_fds_text(text)
    assert other.ramps.get("R").values == [0, 1]


# -- UX-04 snapping --------------------------------------------------------------------------
def test_priority_vertex_over_grid(api):
    api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="B")
    api.viewport.set_snap(snap_to_vertex=True)
    r = api.snapping.snap((1.04, 0.97, 0.02))
    assert r.kind == "vertex" and r.point == (1, 1, 0) and r.entity == "B"


def test_edge_then_face_then_mesh_then_grid(api):
    api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="B")
    api.viewport.set_snap(snap_to_vertex=True, snap_to_edge=True, snap_to_face=True)
    e = api.snapping.snap((1.5, 1.04, 0.03))
    assert e.kind == "edge" and e.point == pytest.approx((1.5, 1.0, 0.0))
    f = api.snapping.snap((1.5, 1.5, 1.1))
    assert f.kind == "face" and f.point == pytest.approx((1.5, 1.5, 1.0))
    api.viewport.set_snap(snap_to_vertex=False, snap_to_edge=False, snap_to_face=False, snap_to_grid=True)
    m = api.snapping.snap((3.02, 3.98, 2.51))                    # mesh cells are 0.5 m
    assert m.kind == "mesh_point" and m.point == pytest.approx((3.0, 4.0, 2.5))
    api.viewport.set_snap(snap_to_mesh=False)
    g = api.snapping.snap((3.02, 3.98, 2.51), grid_size=0.1) if False else api.snapping.snap((3.02, 3.98, 2.51))
    assert g.kind == "grid" and g.point == pytest.approx((3.0, 4.0, 2.5))


def test_mesh_line_and_plane(api):
    api.viewport.set_snap(snap_to_grid=False)
    line = api.snapping.snap((3.02, 3.98, 2.6), tolerance=0.1)
    assert line.kind == "mesh_line" and line.point == pytest.approx((3.0, 4.0, 2.6))
    plane = api.snapping.snap((3.02, 3.8, 2.7), tolerance=0.1)
    assert plane.kind == "mesh_plane" and plane.point == pytest.approx((3.0, 3.8, 2.7))
    none = api.snapping.snap((3.25, 3.75, 2.75), tolerance=0.05)
    assert none.kind == "none" and none.point == (3.25, 3.75, 2.75)


def test_alt_disables_and_tolerance_limits(api):
    api.viewport.set_snap(snap_to_vertex=True)
    api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1])
    assert api.snapping.snap((1.04, 1.0, 0.0), enabled=False).kind == "none"
    far = api.snapping.snap((1.4, 1.0, 0.0), snap_to_grid=False) if False else api.snapping.snap((1.4, 1.0, 0.0), tolerance=0.1)
    assert far.kind != "vertex"
    api.viewport.set_snap(enabled=False)
    assert api.snapping.snap((1.04, 1.0, 0.0)).kind == "none"


def test_ortho_polar_lock_and_sketch_plane(api):
    o = api.snapping.snap((3.0, 0.4, 0.2), anchor=(0, 0, 0), ortho=True, grid_size=0.5)
    assert o.kind == "ortho" and o.point == pytest.approx((3.0, 0.0, 0.0))
    p = api.snapping.snap((2.0, 2.2, 0), anchor=(0, 0, 0), polar_step_deg=45)
    assert p.kind == "polar" and p.point[0] == pytest.approx(p.point[1], abs=0.2)
    assert math.hypot(*p.point[:2]) == pytest.approx(round(math.hypot(2.0, 2.2) / 0.1) * 0.1, abs=1e-6)
    lk = api.snapping.snap((2.0, 1.0, 0.0), anchor=(0, 0, 0), lock_direction=(1, 0, 0))
    assert lk.kind == "locked" and lk.point[1] == pytest.approx(0.0) and lk.point[2] == pytest.approx(0.0)
    pl = api.snapping.snap((1.04, 1.02, 7.0), plane=("z", 2.0))
    assert pl.point[2] == pytest.approx(2.0)
    flat = sn.constrain((3, 0.2, 5), (0, 0, 0), ortho=True, plane=("z", 0))
    assert flat[0] == (3, 0, 0)


def test_snap_arguments_validated(api):
    for bad in (dict(point=(1, 2)), dict(point=(1, 2, 3), tolerance=-1), dict(point=(1, 2, 3), kinds=["nope"])):
        with pytest.raises(ValueError):
            sn.snap(bad.pop("point"), api.project, **bad)
    with pytest.raises(TypeError):
        api.snapping.snap((1, 2, 3), bogus=1)
    with pytest.raises(ValueError):
        api.snapping.snap((1, 2, 3), anchor=(0, 0, 0), lock_direction=(0, 0, 0))


def test_geom_vertices_snap(api):
    api.geom.box([6, 7, 6, 7, 6, 7], name="G")
    api.viewport.set_snap(snap_to_vertex=True)
    r = api.snapping.snap((6.05, 6.0, 6.0))
    assert r.kind == "vertex" and r.entity == "G"


# -- UX-08 visibility ------------------------------------------------------------------------
def _three(api):
    return [api.obstructions.add_obstruction([i, i + 1, 0, 1, 0, 1], name=f"O{i}") for i in range(3)]


def test_hide_show_isolate_and_queries(api):
    a, b, c = _three(api)
    assert api.view.hide([a, b]) == 2 and api.view.hide(a) == 0
    assert not api.view.is_visible(a) and api.view.is_visible(c)
    assert [e.name for e in api.view.visible("obstructions")] == ["O2"]
    assert api.view.show(a) == 1 and api.view.show(a) == 0
    n = api.view.isolate([b])
    assert n >= 3 and api.view.is_visible(b) and not api.view.is_visible(c)
    assert not api.view.is_visible(api.meshes.get("M"))              # everything else, meshes too
    api.view.show_all()
    assert not api.view.hidden() and all(api.view.is_visible(x) for x in (a, b, c))
    with pytest.raises(ValueError):
        api.view.isolate([])
    from pyfds.domain.model import Obstruction
    with pytest.raises(KeyError):
        api.view.hide(Obstruction(name="stray"))


def test_filter_and_type_toggles(api):
    a, b, c = _three(api)
    api.vents.add_vent([0, 1, 0, 1, 0, 0], name="V")
    b.tags = ["wall"]
    assert api.view.filter(collection="obstructions", name_contains="o") == 3
    assert api.view.filter(tag="wall") == 1 and api.view.is_visible(b) and not api.view.is_visible(a)
    assert api.view.filter(name_contains="nothing-matches") == 0
    with pytest.raises(ValueError):
        api.view.filter()
    with pytest.raises(KeyError):
        api.view.filter(collection="nope")
    api.view.show_all()
    api.view.set_type_visible("vents", False)
    assert api.view.hidden_types() == ["vents"] and api.view.visible("vents") == []
    assert not api.view.is_visible(api.vents.get("V")) and api.view.is_visible(a)
    api.view.set_type_visible("vents", True)
    assert api.view.visible("vents")
    with pytest.raises(KeyError):
        api.view.set_type_visible("nope", False)


def test_visibility_is_saved_with_the_document(api, tmp_path):
    a, b, c = _three(api)
    api.view.hide([a, c])
    api.view.set_type_visible("vents", False)
    back = FdsApi(_save_load(api, tmp_path))
    assert sorted(e.name for e in back.view.hidden()) == ["O0", "O2"]
    assert back.view.hidden_types() == ["vents"]
    assert [e.name for e in back.view.visible("obstructions")] == ["O1"]


def test_hidden_objects_still_written_to_fds(api):
    a, *_ = _three(api)
    api.view.hide(a)
    assert "ID='O0'" in FdsWriter().generate_content(api.project)


# -- FIO-01 number format --------------------------------------------------------------------
def test_default_format_unchanged(api):
    api.obstructions.add_obstruction([0.123456789, 1.5, 0, 1, 0, 1], name="X")
    before = FdsWriter().generate_content(api.project)
    api.fds_format.set_number_format(None, "auto")
    assert FdsWriter().generate_content(api.project) == before
    assert api.fds_format.get() == {"significant_digits": None, "style": "auto"}


@pytest.mark.parametrize("digits,style,value,expected", [
    (3, "auto", 0.123456789, "0.123"), (3, "auto", 1234.5678, "1230.0"), (6, "auto", 3.14159265, "3.14159"),
    (3, "auto", 5e-7, "5.00E-7"), (3, "decimal", 5e-7, "0.0000005"),
    (4, "scientific", 12.5, "1.250E+1"), (2, "auto", 0.0, "0.0"), (3, "auto", 2.0, "2.0"),
    (3, "auto", -0.0456, "-0.0456"),
])
def test_number_format_preview(api, digits, style, value, expected):
    api.fds_format.set_number_format(digits, style)
    assert api.fds_format.preview(value) == expected


def test_number_format_applies_to_export_and_is_saved_and_undoable(api, tmp_path):
    api.obstructions.add_obstruction([0.123456789, 1.5, 0, 1, 0, 1], name="X")
    api.fds_format.set_number_format(3, "auto")
    text = api.fds_format.to_string()
    assert "XB=0.123,1.5" in text and "0.123456789" not in text
    assert "XB=0.123" in FdsWriter().generate_content(api.project)
    assert _save_load(api, tmp_path).number_format == {"significant_digits": 3, "style": "auto"}
    api.history.undo()
    assert api.project.number_format is None and "0.1234568" in api.fds_format.to_string()
    assert FdsWriter().generate_content(api.project, {"significant_digits": 2, "style": "auto"}).count("0.12") >= 1
    # the explicit argument does not leak into later writes
    assert "0.1234568" in FdsWriter().generate_content(api.project)


@pytest.mark.parametrize("digits,style", [(0, "auto"), (16, "auto"), (3.5, "auto"), (True, "auto"), (3, "weird")])
def test_bad_number_format_rejected(api, digits, style):
    with pytest.raises(ValueError):
        api.fds_format.set_number_format(digits, style)
    assert api.project.number_format is None


# -- tools -----------------------------------------------------------------------------------
def test_agent_tools(api):
    d = AgentToolDispatcher(api)
    api.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="B")
    text = d.call("copy_objects_as_fds", {"objects": [{"collection": "obstructions", "name": "B"}]})
    assert d.call("paste_fds_text", {"text": text, "offset": [1, 0, 0]})["renamed"] == {"B": "B_2"}
    assert d.call("paste_clipboard", {})["added"] == ["B_3"]
    obj = [{"collection": "obstructions", "name": "B"}]
    assert d.call("hide_objects", {"objects": obj}) == 1
    assert d.call("show_objects", {"objects": obj}) == 1
    assert d.call("isolate_objects", {"objects": obj}) > 0
    assert d.call("filter_objects", {"name_contains": "B_"}) == 2
    d.call("show_all_objects", {})
    d.call("set_type_visible", {"collection": "vents", "visible": False})
    assert api.view.hidden_types() == ["vents"]
    api.viewport.set_snap(snap_to_vertex=True)
    s = d.call("snap_point", {"point": [1.02, 1.0, 0.0], "tolerance": 0.1})
    assert s["kind"] == "vertex" and s["point"] == [1.0, 1.0, 0.0]
    d.call("set_fds_number_format", {"significant_digits": 4})
    assert api.fds_format.get()["significant_digits"] == 4
    with pytest.raises(KeyError):
        d.call("hide_objects", {"objects": [{"collection": "obstructions", "name": "NOPE"}]})
