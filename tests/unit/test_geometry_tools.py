"""Unit tests — pyfds.domain.geometry_tools (GeometryTools). (part 1 of 1)."""


from __future__ import annotations

import math

import pytest

from pyfds.domain.geometry_tools import GeometryTools
from pyfds.domain.model import Geom


def _bounds(geom):
    """Return ((xmin,xmax),(ymin,ymax),(zmin,zmax))."""
    return GeometryTools.bounds(geom)


class TestBoxGeom:
    def test_vertex_count(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        assert len(g.verts) == 8

    def test_face_count(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        assert len(g.faces) == 12   # 6 faces × 2 triangles

    def test_bounds_match_xb(self):
        g = GeometryTools.box_geom([1, 3, 2, 5, 0, 4])
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = _bounds(g)
        assert xmin == pytest.approx(1.0) and xmax == pytest.approx(3.0)
        assert ymin == pytest.approx(2.0) and ymax == pytest.approx(5.0)
        assert zmin == pytest.approx(0.0) and zmax == pytest.approx(4.0)

    def test_surf_id_applied(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1], surf_id="STEEL")
        assert g.surf_id == "STEEL"

    def test_name_applied(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1], name="Cube")
        assert g.name == "Cube"

    def test_returns_geom_instance(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        assert isinstance(g, Geom)

    def test_all_face_indices_valid(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        n = len(g.verts)
        for face in g.faces:
            assert all(0 <= idx < n for idx in face)

    def test_no_degenerate_faces(self):
        g = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        for a, b, c in g.faces:
            assert a != b and b != c and a != c

class TestSphere:
    def test_vertex_count_formula(self):
        # 1 top + (n_lat-1)*n_lon + 1 bottom
        n_lat, n_lon = 4, 6
        g = GeometryTools.sphere((0, 0, 0), 1.0, n_lat=n_lat, n_lon=n_lon)
        expected = 2 + (n_lat - 1) * n_lon
        assert len(g.verts) == expected

    def test_face_count_formula(self):
        n_lat, n_lon = 4, 6
        g = GeometryTools.sphere((0, 0, 0), 1.0, n_lat=n_lat, n_lon=n_lon)
        # top cap: n_lon + middle bands: (n_lat-2)*n_lon*2 + bottom cap: n_lon
        expected = n_lon + (n_lat - 2) * n_lon * 2 + n_lon
        assert len(g.faces) == expected

    def test_bounds_within_radius(self):
        r = 2.5
        cx, cy, cz = 1.0, 2.0, 3.0
        tol = 1e-4
        g = GeometryTools.sphere((cx, cy, cz), r, n_lat=8, n_lon=16)
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = _bounds(g)
        assert xmin >= cx - r - tol
        assert xmax <= cx + r + tol
        assert zmax <= cz + r + tol
        assert zmin >= cz - r - tol

    def test_minimum_resolution_clamped(self):
        # n_lat/n_lon < 3 should be clamped to 3
        g = GeometryTools.sphere((0, 0, 0), 1.0, n_lat=1, n_lon=1)
        assert len(g.verts) > 0
        assert len(g.faces) > 0

    def test_surf_id(self):
        g = GeometryTools.sphere((0, 0, 0), 1.0, surf_id="GLASS")
        assert g.surf_id == "GLASS"

    def test_all_face_indices_valid(self):
        g = GeometryTools.sphere((0, 0, 0), 1.0)
        n = len(g.verts)
        for face in g.faces:
            assert all(0 <= idx < n for idx in face)

class TestCylinder:
    def test_vertex_count_with_caps(self):
        n = 8
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 2.0, n_sides=n)
        # bottom ring + top ring + 2 cap centres
        assert len(g.verts) == 2 * n + 2

    def test_vertex_count_no_caps(self):
        n = 8
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 2.0, n_sides=n,
                                   cap_top=False, cap_bottom=False)
        assert len(g.verts) == 2 * n

    def test_face_count_with_caps(self):
        n = 6
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 2.0, n_sides=n)
        # n*2 side + n top + n bottom
        assert len(g.faces) == n * 2 + n + n

    def test_face_count_no_caps(self):
        n = 6
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 2.0, n_sides=n,
                                   cap_top=False, cap_bottom=False)
        assert len(g.faces) == n * 2

    def test_height_in_bounds(self):
        g = GeometryTools.cylinder((0, 0, 5), 1.0, 3.0)
        (_, _), (_, _), (zmin, zmax) = _bounds(g)
        assert zmin == pytest.approx(5.0)
        assert zmax == pytest.approx(8.0)

    def test_minimum_sides_clamped(self):
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 1.0, n_sides=1)
        assert len(g.verts) > 0

    def test_all_face_indices_valid(self):
        g = GeometryTools.cylinder((0, 0, 0), 1.0, 2.0)
        n = len(g.verts)
        for face in g.faces:
            assert all(0 <= idx < n for idx in face)

class TestCone:
    def test_vertex_count_with_cap(self):
        n = 8
        g = GeometryTools.cone((0, 0, 0), 1.0, 2.0, n_sides=n)
        # base ring + apex + cap centre
        assert len(g.verts) == n + 1 + 1

    def test_vertex_count_no_cap(self):
        n = 8
        g = GeometryTools.cone((0, 0, 0), 1.0, 2.0, n_sides=n, cap_bottom=False)
        assert len(g.verts) == n + 1

    def test_face_count_with_cap(self):
        n = 6
        g = GeometryTools.cone((0, 0, 0), 1.0, 2.0, n_sides=n)
        # n side + n base cap
        assert len(g.faces) == n + n

    def test_apex_at_top(self):
        g = GeometryTools.cone((0, 0, 0), 1.0, 5.0)
        (_, _), (_, _), (zmin, zmax) = _bounds(g)
        assert zmax == pytest.approx(5.0)
        assert zmin == pytest.approx(0.0)

    def test_all_face_indices_valid(self):
        g = GeometryTools.cone((0, 0, 0), 1.0, 2.0)
        n = len(g.verts)
        for face in g.faces:
            assert all(0 <= idx < n for idx in face)

class TestExtrudePolygon:
    def test_vertex_count_square(self):
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        g = GeometryTools.extrude_polygon(sq, 0.0, 3.0)
        assert len(g.verts) == 8   # 4 bottom + 4 top

    def test_face_count_square_with_caps(self):
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        n = len(sq)
        g = GeometryTools.extrude_polygon(sq, 0.0, 3.0)
        # walls: n*2, bottom cap: n-2, top cap: n-2
        assert len(g.faces) == n * 2 + (n - 2) + (n - 2)

    def test_face_count_no_caps(self):
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        n = len(sq)
        g = GeometryTools.extrude_polygon(sq, 0.0, 3.0,
                                          cap_top=False, cap_bottom=False)
        assert len(g.faces) == n * 2

    def test_z_extents_correct(self):
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        g = GeometryTools.extrude_polygon(sq, z_bottom=2.0, z_top=5.0)
        (_, _), (_, _), (zmin, zmax) = _bounds(g)
        assert zmin == pytest.approx(2.0)
        assert zmax == pytest.approx(5.0)

    def test_raises_less_than_3_verts(self):
        with pytest.raises(ValueError):
            GeometryTools.extrude_polygon([(0, 0), (1, 0)], 0.0, 1.0)

    def test_all_face_indices_valid(self):
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        g = GeometryTools.extrude_polygon(sq, 0.0, 1.0)
        n = len(g.verts)
        for face in g.faces:
            assert all(0 <= idx < n for idx in face)

class TestMerge:
    def test_vertex_count_is_sum(self):
        a = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        b = GeometryTools.box_geom([2, 3, 0, 1, 0, 1])
        m = GeometryTools.merge(a, b)
        assert len(m.verts) == len(a.verts) + len(b.verts)

    def test_face_count_is_sum(self):
        a = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        b = GeometryTools.box_geom([2, 3, 0, 1, 0, 1])
        m = GeometryTools.merge(a, b)
        assert len(m.faces) == len(a.faces) + len(b.faces)

    def test_face_indices_offset_correctly(self):
        a = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])  # 8 verts
        b = GeometryTools.box_geom([2, 3, 0, 1, 0, 1])  # 8 verts
        m = GeometryTools.merge(a, b)
        # All face indices must be in [0, 16)
        n = len(m.verts)
        for face in m.faces:
            assert all(0 <= idx < n for idx in face)

    def test_merge_empty_geoms(self):
        a = Geom(name="e", surf_id="INERT", verts=[], faces=[])
        b = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        m = GeometryTools.merge(a, b)
        assert len(m.verts) == len(b.verts)

    def test_name_and_surf_id_applied(self):
        a = GeometryTools.box_geom([0, 1, 0, 1, 0, 1])
        b = GeometryTools.box_geom([2, 3, 0, 1, 0, 1])
        m = GeometryTools.merge(a, b, name="Combined", surf_id="WOOD")
        assert m.name == "Combined"
        assert m.surf_id == "WOOD"

class TestParameterValidation:
    def test_sphere_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            GeometryTools.sphere((0, 0, 0), 0.0)

    def test_sphere_negative_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            GeometryTools.sphere((0, 0, 0), -1.0)

    def test_cylinder_zero_height_raises(self):
        with pytest.raises(ValueError, match="height"):
            GeometryTools.cylinder((0, 0, 0), 1.0, 0.0)

    def test_cylinder_negative_height_raises(self):
        with pytest.raises(ValueError, match="height"):
            GeometryTools.cylinder((0, 0, 0), 1.0, -3.0)

    def test_cylinder_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            GeometryTools.cylinder((0, 0, 0), 0.0, 2.0)

    def test_cone_negative_height_raises(self):
        with pytest.raises(ValueError, match="height"):
            GeometryTools.cone((0, 0, 0), 1.0, -1.0)

    def test_cone_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            GeometryTools.cone((0, 0, 0), 0.0, 1.0)

class TestEdgeCases:
    def test_box_geom_zero_volume_does_not_crash(self):
        g = GeometryTools.box_geom([0, 0, 0, 0, 0, 0])
        assert isinstance(g, Geom)
        assert len(g.verts) == 8   # vertices created, all coincident
        assert len(g.faces) == 12

    def test_merge_both_empty(self):
        a = Geom(name="e1", surf_id="INERT", verts=[], faces=[])
        b = Geom(name="e2", surf_id="INERT", verts=[], faces=[])
        m = GeometryTools.merge(a, b)
        assert len(m.verts) == 0
        assert len(m.faces) == 0

    def test_sphere_extreme_resolution_formula_holds(self):
        n_lat, n_lon = 32, 64
        g = GeometryTools.sphere((0, 0, 0), 1.0, n_lat=n_lat, n_lon=n_lon)
        expected_verts = 2 + (n_lat - 1) * n_lon
        expected_faces = n_lon + (n_lat - 2) * n_lon * 2 + n_lon
        assert len(g.verts) == expected_verts
        assert len(g.faces) == expected_faces

    def test_extrude_self_intersecting_polygon_produces_geometry(self):
        # Hourglass / bowtie — geometrically degenerate but should not crash
        hourglass = [(0, 0), (1, 1), (1, 0), (0, 1)]
        g = GeometryTools.extrude_polygon(hourglass, 0.0, 1.0)
        assert len(g.verts) >= 4

    def test_bounds_large_coordinates(self):
        g = GeometryTools.box_geom([-1e12, 1e12, -1e12, 1e12, -1e12, 1e12])
        (xmin, xmax), _, _ = GeometryTools.bounds(g)
        assert xmin == pytest.approx(-1e12)
        assert xmax == pytest.approx(1e12)

class TestBounds:
    def test_empty_geom_returns_zeros(self):
        g = Geom(name="e", surf_id="INERT", verts=[], faces=[])
        assert GeometryTools.bounds(g) == ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))

    def test_correct_extents(self):
        g = GeometryTools.box_geom([-1, 2, -3, 4, -5, 6])
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = GeometryTools.bounds(g)
        assert xmin == pytest.approx(-1.0) and xmax == pytest.approx(2.0)
        assert ymin == pytest.approx(-3.0) and ymax == pytest.approx(4.0)
        assert zmin == pytest.approx(-5.0) and zmax == pytest.approx(6.0)

class TestBoolean:
    def _volume(self, geom):
        import pyvista as pv
        flat = []
        for f in geom.faces:
            flat.append(len(f))
            flat.extend(f)
        return pv.PolyData(geom.verts, flat).triangulate().volume

    def test_union_volume(self):
        # Two 2x2x2 boxes (volume 8 each) overlapping in a 1x1x1 region.
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        result = GeometryTools.boolean("union", a, b, name="U")
        assert self._volume(result) == pytest.approx(15.0, abs=1e-6)

    def test_difference_volume(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        result = GeometryTools.boolean("difference", a, b, name="D")
        assert self._volume(result) == pytest.approx(7.0, abs=1e-6)

    def test_intersection_volume(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        result = GeometryTools.boolean("intersection", a, b, name="I")
        assert self._volume(result) == pytest.approx(1.0, abs=1e-6)

    def test_result_is_independent_new_geom(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        original_a_verts = list(a.verts)
        result = GeometryTools.boolean("union", a, b, name="U")
        assert a.verts == original_a_verts  # source untouched
        assert result.name == "U"
        assert result is not a and result is not b

    def test_result_faces_are_all_triangles(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        result = GeometryTools.boolean("union", a, b, name="U")
        assert all(len(f) == 3 for f in result.faces)

    def test_rejects_invalid_op(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="a")
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        with pytest.raises(ValueError, match="op must be"):
            GeometryTools.boolean("bogus", a, b)

    def test_rejects_non_manifold_first_geom(self):
        a = GeometryTools.box_geom([0, 2, 0, 2, 0, 2], name="open_box")
        a.faces = a.faces[:-2]  # drop the top cap -> open mesh
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        with pytest.raises(ValueError, match="not a closed mesh"):
            GeometryTools.boolean("union", a, b)

    def test_rejects_empty_geom(self):
        a = Geom(name="empty", surf_id="INERT", verts=[], faces=[])
        b = GeometryTools.box_geom([1, 3, 1, 3, 1, 3], name="b")
        with pytest.raises(ValueError):
            GeometryTools.boolean("union", a, b)
