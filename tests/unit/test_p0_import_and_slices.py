"""P0 partial rows, batch 4: OBJ/DXF import (IMP-02) and slice display (RES-04)."""
from __future__ import annotations

import struct

import numpy as np
import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.io import mesh_importers as mi
from pyfds.results.reader import ReaderResult, SliceHeader
from pyfds.results import slice_display as sd


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 8, 10), xb=(0, 10, 0, 8, 0, 5), name="M")
    return a


CUBE_OBJ = """# cube
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
vn 0 0 1
f 1//1 4//1 3//1 2//1
f 5/1/1 6/2/1 7/3/1 8/4/1
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""


def _dxf_face(pts):
    out = ["0", "3DFACE", "8", "0"]
    for k, (x, y, z) in enumerate(pts):
        out += [str(10 + k), str(x), str(20 + k), str(y), str(30 + k), str(z)]
    return out


def _dxf(faces, units=None):
    head = ["0", "SECTION", "2", "HEADER"]
    if units is not None:
        head += ["9", "$INSUNITS", "70", str(units)]
    head += ["0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    body = [t for f in faces for t in _dxf_face(f)]
    return "\n".join(head + body + ["0", "ENDSEC", "0", "EOF"]) + "\n"


# -- OBJ ---------------------------------------------------------------------------------------
def test_obj_cube(api, tmp_path):
    f = tmp_path / "cube.obj"
    f.write_text(CUBE_OBJ)
    g = api.geom.import_file(str(f), surf_id="CONCRETE")
    assert g.name == "cube" and g.surf_id == "CONCRETE"
    assert len(g.verts) == 8 and len(g.faces) == 12            # 6 quads fanned into 12 triangles
    assert g.bbox() == (0, 1, 0, 1, 0, 1)
    api.history.undo()
    assert not api.geom.all()


def test_obj_units_up_axis_translate(api, tmp_path):
    f = tmp_path / "c.obj"
    f.write_text(CUBE_OBJ)
    g = api.geom.import_file(str(f), units="mm", up_axis="Y", translate=(1, 2, 3), name="Z")
    x0, x1, y0, y1, z0, z1 = g.bbox()
    assert (x1 - x0) == pytest.approx(0.001) and x0 == pytest.approx(1)
    assert y0 == pytest.approx(2 - 0.001) and z0 == pytest.approx(3)    # Y-up: old Z becomes -Y
    assert g.name == "Z"


def test_obj_negative_indices_and_comments(tmp_path):
    f = tmp_path / "t.obj"
    f.write_text("v 0 0 0 # a\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")
    assert mi.ObjImporter.load(str(f)).faces == [(0, 1, 2)]


@pytest.mark.parametrize("text", ["v 0 0 0\nf 1 2 3\n", "v 0 0 0\nv 1 0 0\nf 1 2\n", "v a b c\n", "v 0 0 0\n", "f x y z\n",
                                  "v 0 0 0\nv 0 0 0\nv 0 0 0\nf 1 2 3\n"])
def test_obj_bad_files(tmp_path, text):
    f = tmp_path / "b.obj"
    f.write_text(text)
    with pytest.raises(ValueError):
        mi.ObjImporter.load(str(f))


# -- DXF ---------------------------------------------------------------------------------------
def test_dxf_triangle_and_quad(api, tmp_path):
    f = tmp_path / "m.dxf"
    f.write_text(_dxf([[(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 0)], [(0, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1)]]))
    g = api.geom.import_file(str(f))
    assert len(g.faces) == 3                                    # triangle + quad (2)
    assert g.bbox() == (0, 1, 0, 1, 0, 1)


def test_dxf_units_from_header_and_override(tmp_path):
    f = tmp_path / "u.dxf"
    f.write_text(_dxf([[(0, 0, 0), (1000, 0, 0), (0, 1000, 0), (0, 1000, 0)]], units=4))   # millimetres
    assert mi.DxfImporter.load(str(f)).bbox()[1] == pytest.approx(1.0)
    assert mi.DxfImporter.load(str(f), units="m").bbox()[1] == pytest.approx(1000.0)


def test_dxf_errors(tmp_path):
    f = tmp_path / "e.dxf"
    f.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n0\nENDSEC\n0\nEOF\n")
    with pytest.raises(ValueError, match="3DFACE"):
        mi.DxfImporter.load(str(f))
    f.write_bytes(b"AutoCAD Binary DXF\r\n\x1a\x00")
    with pytest.raises(ValueError, match="binary"):
        mi.DxfImporter.load(str(f))
    f.write_text("0\nSECTION\n2\nENTITIES\n0\n3DFACE\n10\n0\n20\n0\n0\nENDSEC\n0\nEOF\n")
    with pytest.raises(ValueError, match="missing"):
        mi.DxfImporter.load(str(f))


# -- registry ----------------------------------------------------------------------------------
def test_registry_dispatch_and_refusals(api, tmp_path):
    assert {".dxf", ".obj", ".stl"} <= set(mi.supported_formats())
    for name, msg in (("a.fbx", "not available"), ("a.xyz", "unknown file type")):
        with pytest.raises(ValueError, match=msg):
            api.geom.import_file(str(tmp_path / name))
    with pytest.raises(FileNotFoundError):
        api.geom.import_file(str(tmp_path / "missing.obj"))
    with pytest.raises(ValueError):
        mi.unit_factor("furlong")
    # an STL goes through the same door and the same unit handling
    api.geom.box([0, 2, 0, 2, 0, 2], name="B")
    from pyfds.domain.geometry_tools import GeometryTools
    stl = tmp_path / "b.stl"
    verts, faces = api.geom.all()[0].verts, api.geom.all()[0].faces
    lines = ["solid x"]
    for a, b, c in faces:
        lines += ["facet normal 0 0 0", "outer loop"] + [f"vertex {' '.join(map(str, verts[i]))}" for i in (a, b, c)] + \
                 ["endloop", "endfacet"]
    stl.write_text("\n".join(lines + ["endsolid x"]))
    g = api.geom.import_file(str(stl), units="cm", name="S")
    assert g.bbox() == pytest.approx((0, 0.02, 0, 0.02, 0, 0.02))


def test_imported_geom_can_become_blocks(api, tmp_path):
    pytest.importorskip("pyvista")
    f = tmp_path / "cube.obj"
    f.write_text(CUBE_OBJ)
    api.geom.import_file(str(f), translate=(2, 2, 1), units="m", name="C", scale=2.0)
    blocks = api.geom.convert_to_blocks("C", mode="solid")
    assert blocks and all(2 <= o.x_min and o.x_max <= 5.01 for o in blocks)   # the voxel grid reaches one cell past a surface on a cell boundary


# -- slice display -----------------------------------------------------------------------------
def _slice(n_frames=3, shape=(10, 1, 8), quantity="TEMPERATURE"):
    rng = np.arange(np.prod(shape)).reshape(shape).astype(float)
    data = np.stack([rng + 100 * k for k in range(n_frames)])
    hdr = SliceHeader(quantity, "temp", "C", 0, shape[0] - 1, 3, 3, 0, shape[2] - 1)
    return ReaderResult(source_file="x.sf", quantity=quantity, units="C", times=np.arange(n_frames) * 5.0,
                        data=data, metadata={"header": hdr})


def test_display_validation():
    assert sd.SliceDisplay().problems() == []
    for bad in (dict(colormap="nope"), dict(vmin=5, vmax=1), dict(levels=1), dict(levels=999), dict(bounds_from="x"),
                dict(levels=True)):
        assert sd.SliceDisplay(**bad).problems(), bad
        with pytest.raises(ValueError):
            sd.SliceDisplay(**bad).checked()
    assert sd.SliceDisplay(colormap="viridis_r").problems() == []


def test_defaults_per_quantity(api):
    assert api.slice_view.defaults("visibility").colormap == "turbo_r"
    assert api.slice_view.defaults("temperature").colormap == "turbo"
    assert api.slice_view.defaults("something else").colormap == "turbo"
    assert "viridis" in api.slice_view.colormaps()
    with pytest.raises(TypeError):
        api.slice_view.display("TEMPERATURE", wibble=1)


def test_bounds_modes_and_overrides(api):
    r = _slice()
    assert api.slice_view.bounds(r) == (0.0, 79.0 + 200)           # all frames
    assert api.slice_view.bounds(r, 0, bounds_from="frame") == (0.0, 79.0)
    assert api.slice_view.bounds(r, 1, vmin=-5.0) == (-5.0, 279.0)
    assert api.slice_view.bounds(r, 1, vmax=500.0, bounds_from="frame") == (100.0, 500.0)
    flat = _slice(1)
    flat.data[:] = 7.0
    lo, hi = api.slice_view.bounds(flat)
    assert lo == 7.0 and hi > lo
    empty = ReaderResult(source_file="e", quantity="T")
    with pytest.raises(ValueError):
        api.slice_view.bounds(empty)


def test_render_png_with_mesh_coordinates(api, tmp_path):
    import matplotlib.image as mpimg
    r = _slice()
    out = api.slice_view.render(r, str(tmp_path / "s" / "t.png"), 1, mesh="M")
    assert out.endswith("t.png")
    assert open(out, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    img = mpimg.imread(out)
    assert img.shape[0] > 100 and img[..., :3].std() > 0.05          # not blank
    nocb = api.slice_view.render(r, str(tmp_path / "n.png"), 1, colorbar=False)
    assert mpimg.imread(nocb).shape[1] == mpimg.imread(out).shape[1]  # same figure size either way
    assert mpimg.imread(nocb).tolist() != img.tolist()


def test_render_frames_share_one_colour_range(api, tmp_path):
    import matplotlib.image as mpimg
    r = _slice()
    paths = api.slice_view.render_frames(r, str(tmp_path), "f", mesh=api.meshes.get("M"))
    assert [p[-10:] for p in paths] == ["f_0000.png", "f_0001.png", "f_0002.png"]
    a, b = (mpimg.imread(p)[..., :3] for p in paths[:2])
    assert not np.allclose(a, b)                                      # shared scale -> frames differ in colour
    sub = api.slice_view.render_frames(r, str(tmp_path / "x"), "g", frames=[2])
    assert len(sub) == 1 and sub[0].endswith("g_0002.png")


def test_render_errors(api, tmp_path):
    r = _slice()
    with pytest.raises(IndexError):
        api.slice_view.render(r, str(tmp_path / "a.png"), 9)
    with pytest.raises(ValueError):
        api.slice_view.render(r, str(tmp_path / "a.png"), 0, colormap="nope")
    vol = _slice(shape=(4, 4, 4))
    with pytest.raises(ValueError, match="volume"):
        api.slice_view.render(vol, str(tmp_path / "v.png"), 0)


def _write_sf(path, data, times, ijk=(0, 9, 3, 3, 0, 7)):
    def rec(b):
        return struct.pack("<i", len(b)) + b + struct.pack("<i", len(b))
    out = rec(b"TEMPERATURE".ljust(30)) + rec(b"temp".ljust(30)) + rec(b"C".ljust(30)) + rec(struct.pack("<6i", *ijk))
    for t, frame in zip(times, data):
        out += rec(struct.pack("<f", t)) + rec(frame.astype("<f4").tobytes(order="F"))
    path.write_bytes(out)


def test_render_from_sf_file_and_tool(api, tmp_path):
    r = _slice(2)
    sf = tmp_path / "case_01.sf"
    _write_sf(sf, r.data, r.times)
    out = api.slice_view.render(str(sf), str(tmp_path / "f.png"), -1, mesh="M")
    assert open(out, "rb").read(4) == b"\x89PNG"
    d = AgentToolDispatcher(api)
    p = d.call("render_slice_image", {"slice_file": str(sf), "filepath": str(tmp_path / "t.png"), "frame": 0,
                                      "colormap": "viridis", "vmin": 0, "vmax": 300})
    assert p.endswith("t.png")
    cube = tmp_path / "cube.obj"
    cube.write_text(CUBE_OBJ)
    assert d.call("import_geometry_file", {"path": str(cube), "units": "m"}) == "cube"
