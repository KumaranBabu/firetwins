"""B3 — glTF/DAE/IFC import, BIM -> obstructions, geometry repair and export, floor-plan backgrounds
and tracing. Each public operation is one undo step."""
from __future__ import annotations

import base64
import json
import struct

import numpy as np
import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain import geometry_repair as gr
from pyfds.domain.plan_trace import merge_rects, trace
from pyfds.io.mesh_importers import import_geometry_all, supported_formats
from pyfds.io.serializer import Serializer


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(100, 40, 30), xb=(0, 10, 0, 4, 0, 3), name="M")
    return a


CUBE_V = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
CUBE_F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
          (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]


def _count(api):
    return len(api.geom.all())


# -- glTF / DAE -------------------------------------------------------------------------------
def _gltf_doc(translation=(0, 0, 0)):
    pos = np.array(CUBE_V, dtype="<f4")
    idx = np.array(CUBE_F, dtype="<u2").reshape(-1)
    blob = pos.tobytes() + idx.tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "translation": list(translation)}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "buffers": [{"byteLength": len(blob)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": pos.nbytes},
                           {"buffer": 0, "byteOffset": pos.nbytes, "byteLength": idx.nbytes}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5123, "count": 36, "type": "SCALAR"}]}
    return doc, blob


def test_gltf_with_embedded_buffer_is_y_up_by_default(tmp_path, api):
    doc, blob = _gltf_doc(translation=(0, 5, 0))                 # 5 m up in glTF = +Z in FDS
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob).decode()
    f = tmp_path / "a.gltf"
    f.write_text(json.dumps(doc))
    g = api.geom.import_file(str(f))
    assert g.bbox() == pytest.approx((0, 1, -1, 0, 5, 6))       # (x, y, z) -> (x, -z, y)
    assert len(g.faces) == 12


def test_glb_binary_container(tmp_path, api):
    doc, blob = _gltf_doc()
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    data = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
            + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob)
    f = tmp_path / "a.glb"
    f.write_bytes(data)
    g = api.geom.import_file(str(f), up_axis="Z", units="mm")
    assert g.bbox() == pytest.approx((0, .001, 0, .001, 0, .001))


DAE = """<?xml version="1.0"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
 <asset><unit meter="0.01" name="centimeter"/><up_axis>Z_UP</up_axis></asset>
 <library_geometries><geometry id="g1"><mesh>
  <source id="p"><float_array id="pa" count="12">0 0 0 100 0 0 100 100 0 0 100 0</float_array>
   <technique_common><accessor source="#pa" count="4" stride="3"/></technique_common></source>
  <vertices id="v"><input semantic="POSITION" source="#p"/></vertices>
  <polylist count="1"><input semantic="VERTEX" source="#v" offset="0"/><vcount>4</vcount><p>0 1 2 3</p></polylist>
 </mesh></geometry></library_geometries>
 <library_visual_scenes><visual_scene id="s"><node><matrix>1 0 0 200 0 1 0 0 0 0 1 0 0 0 0 1</matrix>
  <instance_geometry url="#g1"/></node></visual_scene></library_visual_scenes>
</COLLADA>"""


def test_dae_uses_file_units_and_node_matrix(tmp_path, api):
    f = tmp_path / "a.dae"
    f.write_text(DAE)
    g = api.geom.import_file(str(f))
    assert g.bbox() == pytest.approx((2, 3, 0, 1, 0, 0))        # 200 cm shift, 100 cm square, quad -> 2 tris
    assert len(g.faces) == 2


def test_closed_formats_are_refused_clearly(tmp_path):
    for ext in (".fbx", ".dwg"):
        f = tmp_path / f"a{ext}"
        f.write_bytes(b"x")
        with pytest.raises(ValueError, match="closed format"):
            import_geometry_all(str(f))
    assert {".ifc", ".gltf", ".glb", ".dae"} <= set(supported_formats())


# -- IFC / BIM --------------------------------------------------------------------------------
def _make_ifc(path, mm=False):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    import ifcopenshell.api as iapi
    f = ifcopenshell.api.run("project.create_file")
    proj = iapi.run("root.create_entity", f, ifc_class="IfcProject", name="P")
    iapi.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS" if mm else "METERS"})
    ctx = iapi.run("context.add_context", f, context_type="Model")
    body = iapi.run("context.add_context", f, context_type="Model", context_identifier="Body",
                    target_view="MODEL_VIEW", parent=ctx)
    site, bld, st = (iapi.run("root.create_entity", f, ifc_class=c, name=n)
                     for c, n in (("IfcSite", "S"), ("IfcBuilding", "B"), ("IfcBuildingStorey", "Level 1")))
    iapi.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    iapi.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    iapi.run("aggregate.assign_object", f, products=[st], relating_object=bld)
    k = 1000 if mm else 1
    for i, (cls, x) in enumerate([("IfcWall", 0), ("IfcSlab", 5)]):
        w = iapi.run("root.create_entity", f, ifc_class=cls, name=f"El{i}")
        iapi.run("geometry.assign_representation", f, product=w, representation=iapi.run(
            "geometry.add_wall_representation", f, context=body, length=4 * k, height=3 * k, thickness=0.2 * k))
        m = np.eye(4)
        m[0, 3] = x * k
        iapi.run("geometry.edit_object_placement", f, product=w, matrix=m)
        iapi.run("spatial.assign_container", f, products=[w], relating_structure=st)
    f.write(str(path))
    return path


def test_ifc_gives_one_tagged_shape_per_element_in_metres(tmp_path, api):
    shapes = api.geom.import_file(str(_make_ifc(tmp_path / "b.ifc", mm=True)))
    assert {g.bim_type for g in shapes} == {"IfcWall", "IfcSlab"}
    assert all(g.bim_storey == "Level 1" and g.source_file == "b.ifc" for g in shapes)
    wall = api.geom.get("Wall_El0")
    assert wall.bbox() == pytest.approx((0, 4, 0, .2, 0, 3))    # millimetre file converted
    assert api.geom.bim_types() == {"IfcSlab": 1, "IfcWall": 1}
    api.history.undo()
    assert _count(api) == 0                                     # whole import = one undo step


def test_ifc_type_filter_and_merge(tmp_path, api):
    p = str(_make_ifc(tmp_path / "b.ifc"))
    one = api.geom.import_file(p, types=["IfcWall"])
    assert one.bim_type == "IfcWall"
    api.geom.remove(one)
    merged = api.geom.import_file(p, merge=True, name="Whole")
    assert merged.name == "Whole" and merged.bim_type is None


def test_generate_model_from_bim(tmp_path, api):
    api.geom.import_file(str(_make_ifc(tmp_path / "b.ifc")))
    assert [g.bim_type for g in api.geom.select_by_bim_type("ifcwall")] == ["IfcWall"]
    api.surfaces.add(__import__("pyfds.domain.model", fromlist=["Surface"]).Surface(name="GYPSUM"))
    obsts = api.geom.generate_from_bim(types=["IfcWall"], surface_map={"IfcWall": "GYPSUM"})
    assert obsts and all(o.surface_id == "GYPSUM" for o in obsts)
    assert _count(api) == 1 and api.geom.bim_types() == {"IfcSlab": 1}      # wall shape consumed, slab kept
    box = (min(o.x_min for o in obsts), max(o.x_max for o in obsts), max(o.z_max for o in obsts))
    assert box == pytest.approx((0, 4, 3), abs=0.11)
    api.history.undo()
    assert _count(api) == 2 and not api.obstructions.all()
    with pytest.raises(ValueError, match="no BIM shapes"):
        api.geom.generate_from_bim(types=["IfcDoor"])


# -- repair -----------------------------------------------------------------------------------
def test_repair_welds_drops_bad_triangles_and_fixes_winding():
    v = list(CUBE_V) + [(0, 0, 0)]                              # a duplicate corner
    f = [(a, b, c) for a, b, c in CUBE_F]
    f[0] = (f[0][0], f[0][2], f[0][1])                          # one flipped triangle
    f.append((8, 1, 1))                                         # degenerate
    f.append(CUBE_F[3])                                         # duplicate
    f = [(8 if x == 0 and i == 1 else x for x in t) and t for i, t in enumerate(f)]
    before = gr.inspect(v, f)
    assert before["degenerate"] >= 1 and before["duplicate"] >= 1
    nv, nf, rep = gr.repair(v, f)
    assert len(nv) == 8 and len(nf) == 12
    assert rep["after"]["closed"] and rep["after"]["volume"] == pytest.approx(1.0)
    assert rep["flipped_triangles"] >= 1 and rep["removed_degenerate"] >= 1 and rep["removed_duplicate"] == 1


def test_repair_turns_inside_out_solid_outward():
    nf = [t[::-1] for t in CUBE_F]
    assert gr.inspect(CUBE_V, nf)["volume"] < 0
    _, f2, rep = gr.repair(CUBE_V, nf)
    assert rep["inverted_whole_mesh"] and rep["after"]["volume"] == pytest.approx(1.0)


def test_api_repair_is_undoable(api):
    g = api.geom.box((0, 1, 0, 1, 0, 1), name="B")
    g.faces = [tuple(t[::-1]) for t in g.faces]
    assert api.geom.check_geometry("B")["volume"] < 0
    rep = api.geom.repair("B")
    assert rep["inverted_whole_mesh"] and api.geom.check_geometry("B")["volume"] > 0
    api.history.undo()
    assert api.geom.check_geometry("B")["volume"] < 0


def test_rescale_fixes_wrong_units(api):
    g = api.geom.box((0, 1000, 0, 1000, 0, 1000), name="Big")
    api.geom.rescale("Big", 0.001)
    assert g.bbox() == pytest.approx((0, 1, 0, 1, 0, 1))
    with pytest.raises(ValueError):
        api.geom.rescale("Big", 0)


# -- export -----------------------------------------------------------------------------------
@pytest.mark.parametrize("ext,kw", [(".stl", {}), (".stl", {"ascii_stl": True}), (".obj", {})])
def test_export_then_reimport_round_trips(tmp_path, api, ext, kw):
    api.geom.box((1, 3, 1, 2, 0, 1), name="B")
    p = str(tmp_path / f"out{ext}")
    assert api.geom.export_geometry(p, **kw) == 12
    api2 = FdsApi()
    g = api2.geom.import_file(p)
    assert g.bbox() == pytest.approx((1, 3, 1, 2, 0, 1))


def test_export_units_up_axis_and_obstructions(tmp_path, api):
    api.obstructions.add_obstruction([0, 1, 0, 2, 0, 3])
    p = str(tmp_path / "o.obj")
    assert api.geom.export_geometry(p, include_obstructions=True, units="mm", up_axis="Y") == 12
    g = FdsApi().geom.import_file(p, units="mm", up_axis="Y")
    assert g.bbox() == pytest.approx((0, 1, 0, 2, 0, 3))
    with pytest.raises(ValueError, match="nothing to export"):
        api.geom.export_geometry(str(tmp_path / "e.stl"))
    with pytest.raises(ValueError, match=r"\.stl or \.obj"):
        api.geom.export_geometry(str(tmp_path / "e.dxf"))


# -- floor-plan backgrounds and tracing ---------------------------------------------------------
def _plan_png(path):
    from PIL import Image
    a = np.full((40, 100), 255, dtype=np.uint8)                 # 100x40 px = 10 x 4 m at 10 px/m
    a[0:3, :] = 0                                               # top wall, 0.3 m thick
    a[:, 0:3] = 0                                               # left wall
    Image.fromarray(a).save(path)
    return str(path)


def test_trace_merges_runs_into_few_boxes():
    g = np.full((40, 100), 255.0)
    g[0:3, :] = 0
    g[:, 0:3] = 0
    rects = trace(g, width_m=10, cell=0.1)
    assert 1 <= len(rects) <= 3
    assert sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in rects) == pytest.approx(10 * 0.3 + 4 * 0.3 - 0.09)
    assert max(r[3] for r in rects) == pytest.approx(4.0)       # top of the picture = +Y
    assert merge_rects(np.zeros((3, 3), bool)) == []


def test_background_add_update_remove_undo_and_save(tmp_path, api):
    png = _plan_png(tmp_path / "plan.png")
    b = api.backgrounds.add(png, width=10, x=1, y=2, opacity=0.4)
    assert api.backgrounds.extent("plan") == pytest.approx([1, 11, 2, 6])
    api.backgrounds.update("plan", opacity=0.8, visible=False)
    saved = tmp_path / "m.pyfds"
    Serializer().save(api.project, str(saved))
    loaded = Serializer().load(str(saved))
    lb = loaded.editor.backgrounds["plan"]
    assert (lb.x, lb.y, lb.opacity, lb.visible) == (1, 2, 0.8, False)
    api.history.undo()
    assert api.backgrounds.get("plan").opacity == 0.4
    api.history.undo()
    assert not api.backgrounds.all()
    api.history.redo()
    assert b.name == "plan" and api.backgrounds.get("plan")
    with pytest.raises(ValueError, match="already exists"):
        api.backgrounds.add(png)
    with pytest.raises(AttributeError):
        api.backgrounds.update("plan", path="x")
    with pytest.raises(ValueError, match="unsupported"):
        api.backgrounds.add(str(tmp_path / "x.doc"))


def test_trace_background_makes_walls_in_one_undo_step(tmp_path, api):
    api.backgrounds.add(_plan_png(tmp_path / "plan.png"), width=10, x=0, y=0, z=0.5)
    obsts = api.backgrounds.trace("plan", height=2.5, cell=0.1)
    assert obsts and all(o.z_min == 0.5 and o.z_max == 3.0 for o in obsts)
    assert max(o.x_max for o in obsts) == pytest.approx(10.0)
    api.history.undo()
    assert not api.obstructions.all()
    with pytest.raises(ValueError, match="too|limit"):
        api.backgrounds.trace("plan", cell=0.1, max_boxes=0)


def test_pdf_plan_traces_like_an_image(tmp_path, api):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.draw_rect(fitz.Rect(20, 20, 280, 30), color=(0, 0, 0), fill=(0, 0, 0))
    pdf = tmp_path / "plan.pdf"
    doc.save(str(pdf))
    bg = api.backgrounds.add(str(pdf), width=9)
    assert bg.kind == "pdf"
    obsts = api.backgrounds.trace("plan", cell=0.1, min_fill=0.5)
    assert obsts and max(o.x_max for o in obsts) < 9.0


# -- agent tools ------------------------------------------------------------------------------
def test_agent_tools_cover_the_new_operations(tmp_path, api):
    d = AgentToolDispatcher(api)
    png = _plan_png(tmp_path / "plan.png")
    assert d.call("add_background", {"path": png, "width": 10}) is not None
    assert d.call("trace_background", {"name": "plan"}) is not None
    assert d.call("list_backgrounds", {}) is not None
    api.geom.box((0, 1, 0, 1, 0, 1), name="B")
    assert d.call("check_geometry", {"name": "B"}) is not None
    assert d.call("export_geometry", {"path": str(tmp_path / "e.stl")}) is not None
    r = d.call("import_geometry_file", {"path": str(tmp_path / "e.stl"), "name": "Again"})
    assert r is not None
    assert d.call("list_bim_types", {}) is not None
