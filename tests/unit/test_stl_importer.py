"""Unit tests — pyfds.io.stl_importer (StlImporter)."""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from pyfds.io.stl_importer import StlImporter


# ---------------------------------------------------------------------------
# Helpers — build synthetic STL bytes / text
# ---------------------------------------------------------------------------

def _make_ascii_stl(triangles) -> str:
    """Build an ASCII STL string from a list of ((n), (v0),(v1),(v2)) tuples."""
    lines = ["solid test"]
    for normal, v0, v1, v2 in triangles:
        lines.append(f"  facet normal {normal[0]} {normal[1]} {normal[2]}")
        lines.append("    outer loop")
        for v in (v0, v1, v2):
            lines.append(f"      vertex {v[0]} {v[1]} {v[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid test")
    return "\n".join(lines)


def _make_binary_stl(triangles) -> bytes:
    """Build a binary STL bytes from a list of (v0, v1, v2) tuples (normal computed as 0,0,0)."""
    header = b"\x00" * 80
    n = len(triangles)
    body = struct.pack("<I", n)
    for v0, v1, v2 in triangles:
        body += struct.pack("<fff", 0, 0, 0)  # normal
        for v in (v0, v1, v2):
            body += struct.pack("<fff", *v)
        body += struct.pack("<H", 0)  # attribute byte count
    return header + body


ONE_TRIANGLE = [
    ((0, 0, 1), (0, 0, 0), (1, 0, 0), (0, 1, 0))
]
ONE_TRIANGLE_VERTS = [
    ((0, 0, 0), (1, 0, 0), (0, 1, 0))
]
TWO_TRIANGLES = [
    ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 1, 0)),
    ((0, 0, 1), (0, 0, 0), (1, 1, 0), (0, 1, 0)),
]
TWO_TRIANGLES_VERTS = [
    ((0, 0, 0), (1, 0, 0), (1, 1, 0)),
    ((0, 0, 0), (1, 1, 0), (0, 1, 0)),
]


# ---------------------------------------------------------------------------
# ASCII parsing
# ---------------------------------------------------------------------------

class TestAsciiParsing:
    def test_single_triangle_vertices(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "tri.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.verts) == 3
        assert len(geom.faces) == 1

    def test_two_triangles(self, tmp_path):
        txt = _make_ascii_stl(TWO_TRIANGLES)
        p = tmp_path / "two.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.verts) == 6
        assert len(geom.faces) == 2

    def test_face_indices_correct(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "idx.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=False)
        assert geom.faces[0] == (0, 1, 2)

    def test_surf_id_applied(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "surf.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), surf_id="CONCRETE")
        assert geom.surf_id == "CONCRETE"

    def test_name_defaults_to_stem(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "building.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p))
        assert geom.name == "building"

    def test_custom_name(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "x.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), name="MyWall")
        assert geom.name == "MyWall"


# ---------------------------------------------------------------------------
# Binary parsing
# ---------------------------------------------------------------------------

class TestBinaryParsing:
    def test_single_triangle(self, tmp_path):
        data = _make_binary_stl(ONE_TRIANGLE_VERTS)
        p = tmp_path / "bin.stl"
        p.write_bytes(data)
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.verts) == 3
        assert len(geom.faces) == 1

    def test_two_triangles(self, tmp_path):
        data = _make_binary_stl(TWO_TRIANGLES_VERTS)
        p = tmp_path / "bin2.stl"
        p.write_bytes(data)
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.verts) == 6
        assert len(geom.faces) == 2

    def test_vertex_coordinates_preserved(self, tmp_path):
        data = _make_binary_stl([((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))])
        p = tmp_path / "coords.stl"
        p.write_bytes(data)
        geom = StlImporter.load(str(p), weld=False)
        assert geom.verts[0] == pytest.approx((1.0, 2.0, 3.0))
        assert geom.verts[2] == pytest.approx((7.0, 8.0, 9.0))


# ---------------------------------------------------------------------------
# Vertex welding
# ---------------------------------------------------------------------------

class TestVertexWelding:
    def test_shared_vertices_merged(self, tmp_path):
        # Two triangles sharing an edge → 4 unique verts instead of 6
        txt = _make_ascii_stl(TWO_TRIANGLES)
        p = tmp_path / "weld.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=True)
        assert len(geom.verts) == 4
        assert len(geom.faces) == 2

    def test_weld_false_keeps_duplicates(self, tmp_path):
        txt = _make_ascii_stl(TWO_TRIANGLES)
        p = tmp_path / "noweld.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.verts) == 6

    def test_degenerate_triangles_removed(self, tmp_path):
        # Triangle with two identical vertices → degenerate, removed after welding
        txt = _make_ascii_stl([
            ((0, 0, 1), (0, 0, 0), (0, 0, 0), (1, 0, 0)),  # degenerate (v0==v1)
            ((0, 0, 1), (0, 0, 0), (1, 0, 0), (0, 1, 0)),  # valid
        ])
        p = tmp_path / "degen.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=True)
        assert len(geom.faces) == 1   # degenerate removed


# ---------------------------------------------------------------------------
# Scale and translate
# ---------------------------------------------------------------------------

class TestTransformations:
    def test_scale_applied(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "scale.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), scale=0.001, weld=False)
        # (1,0,0) → (0.001, 0, 0)
        xs = [v[0] for v in geom.verts]
        assert max(xs) == pytest.approx(0.001)

    def test_translate_applied(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "trans.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), translate=(10, 20, 30), weld=False)
        zs = [v[2] for v in geom.verts]
        assert all(z == pytest.approx(30.0) for z in zs)

    def test_scale_then_translate(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "st.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), scale=2.0, translate=(5, 0, 0), weld=False)
        xs = sorted(v[0] for v in geom.verts)
        assert xs[0] == pytest.approx(5.0)   # (0*2)+5
        assert xs[-1] == pytest.approx(7.0)  # (1*2)+5


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            StlImporter.load(str(tmp_path / "nonexistent.stl"))

    def test_truncated_binary_raises(self, tmp_path):
        # Header only, no triangle count — should raise or return 0 faces gracefully
        p = tmp_path / "trunc.stl"
        p.write_bytes(b"\x00" * 80 + b"\x01\x00\x00\x00")  # says 1 tri but no data
        geom = StlImporter.load(str(p), weld=False)
        assert len(geom.faces) == 0


# ---------------------------------------------------------------------------
# Utility methods
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_bounds(self, tmp_path):
        txt = _make_ascii_stl(ONE_TRIANGLE)
        p = tmp_path / "bounds.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=False)
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = StlImporter.bounds(geom)
        assert xmin == pytest.approx(0.0)
        assert xmax == pytest.approx(1.0)
        assert zmin == pytest.approx(0.0)
        assert zmax == pytest.approx(0.0)

    def test_bounds_empty_geom(self):
        from pyfds.domain.model import Geom
        g = Geom(name="empty", surf_id="INERT", verts=[], faces=[])
        result = StlImporter.bounds(g)
        assert result == ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))

    def test_vertex_count(self, tmp_path):
        txt = _make_ascii_stl(TWO_TRIANGLES)
        p = tmp_path / "vc.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=True)
        assert StlImporter.vertex_count(geom) == len(geom.verts)
        assert StlImporter.vertex_count(geom) == 4

    def test_face_count(self, tmp_path):
        txt = _make_ascii_stl(TWO_TRIANGLES)
        p = tmp_path / "fc.stl"
        p.write_text(txt)
        geom = StlImporter.load(str(p), weld=True)
        assert StlImporter.face_count(geom) == 2

    def test_vertex_count_empty(self):
        from pyfds.domain.model import Geom
        g = Geom(name="e", surf_id="INERT")
        assert StlImporter.vertex_count(g) == 0
        assert StlImporter.face_count(g) == 0
