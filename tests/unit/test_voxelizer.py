"""Unit tests — pyfds.domain.voxelizer (Voxelizer)."""
from __future__ import annotations

import pytest

from pyfds.domain.geometry_tools import GeometryTools
from pyfds.domain.model import Geom, Mesh, Obstruction
from pyfds.domain.voxelizer import Voxelizer, _triangle_aabb_overlap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mesh(nx=10, ny=10, nz=10,
          x0=0.0, x1=10.0, y0=0.0, y1=10.0, z0=0.0, z1=10.0):
    return Mesh(name="test_mesh", cell_count=(nx, ny, nz),
                x_min=x0, x_max=x1, y_min=y0, y_max=y1, z_min=z0, z_max=z1)


def _box_geom(xb=(1, 5, 1, 5, 1, 5)):
    return GeometryTools.box_geom(xb, surf_id="INERT", name="TestBox")


# ---------------------------------------------------------------------------
# SAT AABB-triangle overlap test
# ---------------------------------------------------------------------------

class TestTriangleAabbOverlap:
    def test_triangle_fully_inside_aabb(self):
        v0, v1, v2 = (0.1, 0.1, 0.1), (0.4, 0.1, 0.1), (0.2, 0.4, 0.1)
        bmin, bmax = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        assert _triangle_aabb_overlap(v0, v1, v2, bmin, bmax)

    def test_triangle_completely_outside_aabb(self):
        v0, v1, v2 = (5.0, 0.0, 0.0), (6.0, 0.0, 0.0), (5.5, 1.0, 0.0)
        bmin, bmax = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        assert not _triangle_aabb_overlap(v0, v1, v2, bmin, bmax)

    def test_triangle_crossing_aabb_face(self):
        # Triangle spans from inside to outside the box along X
        v0, v1, v2 = (0.5, 0.5, 0.5), (1.5, 0.5, 0.5), (1.0, 0.5, 1.5)
        bmin, bmax = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        assert _triangle_aabb_overlap(v0, v1, v2, bmin, bmax)

    def test_flat_triangle_in_plane(self):
        # Flat Z=0 triangle overlapping box from z=-0.5 to z=0.5
        v0, v1, v2 = (0.5, 0.5, 0.0), (2.0, 0.5, 0.0), (1.0, 2.0, 0.0)
        bmin, bmax = (0.0, 0.0, -0.5), (3.0, 3.0, 0.5)
        assert _triangle_aabb_overlap(v0, v1, v2, bmin, bmax)

    def test_triangle_just_touching_corner(self):
        # Triangle's vertex exactly at box corner — should overlap
        v0, v1, v2 = (1.0, 1.0, 1.0), (2.0, 1.0, 1.0), (1.5, 2.0, 1.0)
        bmin, bmax = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        assert _triangle_aabb_overlap(v0, v1, v2, bmin, bmax)


# ---------------------------------------------------------------------------
# Voxelizer — surface mode
# ---------------------------------------------------------------------------

class TestVoxelizerSurface:
    def test_box_geom_produces_obstructions(self):
        geom = _box_geom()
        mesh = _mesh()
        obsts = Voxelizer.voxelize(geom, mesh, mode="surface")
        assert len(obsts) > 0

    def test_returns_obstruction_instances(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), mode="surface")
        for o in obsts:
            assert isinstance(o, Obstruction)

    def test_surf_id_applied(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), surf_id="CONCRETE", mode="surface")
        assert all(o.surface_id == "CONCRETE" for o in obsts)

    def test_name_prefix_applied(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), name_prefix="bldg", mode="surface")
        assert all(o.name.startswith("bldg_") for o in obsts)

    def test_obstruction_bounds_within_mesh(self):
        geom = _box_geom()
        m = _mesh()
        obsts = Voxelizer.voxelize(geom, m, mode="surface")
        for o in obsts:
            assert o.x_min >= m.x_min - 1e-9
            assert o.x_max <= m.x_max + 1e-9
            assert o.y_min >= m.y_min - 1e-9
            assert o.y_max <= m.y_max + 1e-9
            assert o.z_min >= m.z_min - 1e-9
            assert o.z_max <= m.z_max + 1e-9

    def test_obstruction_dimensions_equal_cell_size(self):
        m = _mesh(nx=10, ny=10, nz=10)
        dx = (m.x_max - m.x_min) / m.cell_count[0]
        dy = (m.y_max - m.y_min) / m.cell_count[1]
        dz = (m.z_max - m.z_min) / m.cell_count[2]
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, m, mode="surface")
        for o in obsts:
            assert (o.x_max - o.x_min) == pytest.approx(dx, rel=1e-6)
            assert (o.y_max - o.y_min) == pytest.approx(dy, rel=1e-6)
            assert (o.z_max - o.z_min) == pytest.approx(dz, rel=1e-6)

    def test_geom_outside_mesh_returns_empty(self):
        geom = GeometryTools.box_geom([50, 60, 50, 60, 50, 60])
        mesh = _mesh(x0=0, x1=10, y0=0, y1=10, z0=0, z1=10)
        obsts = Voxelizer.voxelize(geom, mesh, mode="surface")
        assert obsts == []

    def test_empty_geom_returns_empty(self):
        geom = Geom(name="empty", surf_id="INERT", verts=[], faces=[])
        obsts = Voxelizer.voxelize(geom, _mesh(), mode="surface")
        assert obsts == []

    def test_color_applied(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), color="RED", mode="surface")
        assert all(o.color == "RED" for o in obsts)


# ---------------------------------------------------------------------------
# Voxelizer — additional surface mode checks
# ---------------------------------------------------------------------------

class TestVoxelizerSurfaceExtra:
    def test_all_obstructions_have_expected_color(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), color="BLUE", mode="surface")
        assert len(obsts) > 0
        assert all(o.color == "BLUE" for o in obsts)

    def test_geometry_partially_outside_mesh_still_voxelizes(self):
        # Box from 8→12 on x, but mesh only goes to 10 — partial overlap
        geom = GeometryTools.box_geom([8, 12, 1, 9, 1, 9], surf_id="INERT")
        mesh = _mesh(x0=0, x1=10, y0=0, y1=10, z0=0, z1=10)
        obsts = Voxelizer.voxelize(geom, mesh, mode="surface")
        assert len(obsts) > 0
        # All results must be inside mesh
        for o in obsts:
            assert o.x_max <= mesh.x_max + 1e-9

    def test_name_prefix_with_underscore_valid(self):
        geom = _box_geom()
        obsts = Voxelizer.voxelize(geom, _mesh(), name_prefix="bldg_A", mode="surface")
        assert all(o.name.startswith("bldg_A_") for o in obsts)

    def test_surface_mode_produces_no_interior_duplication(self):
        # surface mode should only hit triangle-overlapping cells, not flood-fill interior
        geom = _box_geom((1, 9, 1, 9, 1, 9))
        mesh = _mesh()
        surface = Voxelizer.voxelize(geom, mesh, mode="surface")
        solid   = Voxelizer.voxelize(geom, mesh, mode="solid")
        # Surface should be a strict subset (or equal when box is thin)
        assert len(surface) <= len(solid)


# ---------------------------------------------------------------------------
# Voxelizer — solid mode
# ---------------------------------------------------------------------------

class TestVoxelizerSolid:
    def test_solid_has_more_or_equal_voxels_than_surface(self):
        geom = _box_geom((1, 9, 1, 9, 1, 9))
        mesh = _mesh()
        surface = Voxelizer.voxelize(geom, mesh, mode="surface")
        solid   = Voxelizer.voxelize(geom, mesh, mode="solid")
        assert len(solid) >= len(surface)

    def test_solid_fills_interior(self):
        # A large box should have filled interior cells
        geom = _box_geom((1, 9, 1, 9, 1, 9))
        mesh = _mesh()
        solid = Voxelizer.voxelize(geom, mesh, mode="solid")
        # All 8x8x8 = 512 interior + surface cells should be filled
        assert len(solid) >= 8 * 8 * 8


# ---------------------------------------------------------------------------
# Voxelizer — STL path input
# ---------------------------------------------------------------------------

class TestVoxelizerStlInput:
    def test_stl_path_accepted_via_importer_and_api(self, tmp_path):
        import struct
        # Build a minimal binary STL (single triangle spanning mesh cells)
        header = b"\x00" * 80
        body = struct.pack("<I", 2)
        for v0, v1, v2 in [
            ((0.5, 0.5, 0.0), (5.5, 0.5, 0.0), (3.0, 5.5, 0.0)),
            ((0.5, 0.5, 0.0), (5.5, 0.5, 5.5), (3.0, 5.5, 5.5)),
        ]:
            body += struct.pack("<fff", 0, 0, 1)
            for v in (v0, v1, v2):
                body += struct.pack("<fff", *v)
            body += struct.pack("<H", 0)
        stl_path = tmp_path / "simple.stl"
        stl_path.write_bytes(header + body)

        from pyfds.io.stl_importer import StlImporter
        mesh = _mesh()
        geom = StlImporter.load(str(stl_path), surf_id="INERT")
        obsts = Voxelizer.voxelize(geom, mesh, mode="surface")
        assert len(obsts) > 0

        # The API facade still accepts a bare STL path (loading is an io concern).
        from pyfds import FdsApi
        api = FdsApi()
        api.project.meshes.append(mesh)
        assert len(api.geom.voxelize(str(stl_path), add_to_project=False)) > 0
