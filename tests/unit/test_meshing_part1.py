"""Tests for pyfds.meshing — engine registry, built-in engine, and manager. (part 1 of 1). (part 1 of 3)."""


from __future__ import annotations

import pytest

from pyfds.domain.geometry import BoundingBox
from pyfds.meshing.base import (
    BoundingBoxGeometry, ElementType, EngineCapabilities,
    FdsStructuredMesh, LicenseType, MeshResult, MeshingEngineBase,
    StructuredMeshRequest,
)
from pyfds.meshing.engines.builtin import BuiltinStructuredEngine
from pyfds.meshing.manager import MeshingManager
from pyfds.meshing.registry import EngineRegistry, reset_engine_registry


@pytest.fixture()
def small_box():
    return BoundingBox(0.0, 4.0, 0.0, 4.0, 0.0, 3.0)

@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Ensure each test sees a clean global registry."""
    yield
    reset_engine_registry()


class TestEngineCapabilities:
    def test_defaults_all_false(self):
        caps = EngineCapabilities()
        assert caps.structured_mesh is False
        assert caps.surface_mesh is False
        assert caps.volume_mesh is False
        assert caps.geometry_import is False

    def test_partial_declaration(self):
        caps = EngineCapabilities(structured_mesh=True, formats_out=["fds"])
        assert caps.structured_mesh is True
        assert caps.surface_mesh is False
        assert caps.formats_out == ["fds"]

class TestBuiltinEngineAvailability:
    def test_always_available(self):
        assert BuiltinStructuredEngine.is_available() is True

    def test_has_version(self):
        ver = BuiltinStructuredEngine.get_version()
        assert ver is not None
        assert isinstance(ver, str)

    def test_capabilities(self):
        caps = BuiltinStructuredEngine.capabilities
        assert caps.structured_mesh is True
        assert caps.surface_mesh is False
        assert caps.volume_mesh is False

    def test_priority(self):
        assert BuiltinStructuredEngine.priority == 10

    def test_license_type(self):
        assert BuiltinStructuredEngine.license_type == LicenseType.OPEN_SOURCE

class TestBuiltinStructuredMesh:
    def test_single_block(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(
            domain=small_box,
            target_cell_size=0.5,
        )
        result = engine.generate_structured_mesh(request)

        assert result.success is True
        assert result.engine_used == "builtin"
        assert len(result.fds_meshes) == 1

        m = result.fds_meshes[0]
        assert m.id == "MESH"
        assert len(m.ijk) == 3
        assert all(n > 0 for n in m.ijk)
        assert m.xb == small_box.xb
        assert m.mpi_rank is None

    def test_cell_count_reasonable(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5)
        result  = engine.generate_structured_mesh(request)

        nx, ny, nz = result.fds_meshes[0].ijk
        # 4/0.5 = 8 expected (Poisson ≥ 8 → 8 = 2^3 ✓)
        assert nx == 8
        assert ny == 8
        # 3/0.5 = 6 (Poisson ≥ 6 → 6 = 2·3 ✓)
        assert nz == 6

    def test_poisson_compliance(self, small_box):
        from pyfds.domain.geometry import GeometryHelper

        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.3,
                                        force_poisson=True)
        result  = engine.generate_structured_mesh(request)
        nx, ny, nz = result.fds_meshes[0].ijk
        assert GeometryHelper.is_poisson_compliant(nx)
        assert GeometryHelper.is_poisson_compliant(ny)
        assert GeometryHelper.is_poisson_compliant(nz)

    def test_no_poisson_when_disabled(self):
        box     = BoundingBox(0, 7, 0, 7, 0, 7)
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=box, target_cell_size=1.0,
                                        force_poisson=False)
        result  = engine.generate_structured_mesh(request)
        assert result.fds_meshes[0].ijk == (7, 7, 7)

    def test_mpi_split_produces_n_blocks(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5,
                                        n_mpi_ranks=4)
        result  = engine.generate_structured_mesh(request)

        assert len(result.fds_meshes) == 4
        for i, m in enumerate(result.fds_meshes):
            assert m.mpi_rank == i
            assert m.id == f"MESH_{i+1:02d}"

    def test_mpi_blocks_cover_domain(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5,
                                        n_mpi_ranks=4, split_axis="X")
        result  = engine.generate_structured_mesh(request)

        x_mins = [BoundingBox.from_xb(m.xb).x_min for m in result.fds_meshes]
        x_maxs = [BoundingBox.from_xb(m.xb).x_max for m in result.fds_meshes]
        assert min(x_mins) == pytest.approx(small_box.x_min)
        assert max(x_maxs) == pytest.approx(small_box.x_max)

    def test_split_y_axis(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5,
                                        n_mpi_ranks=2, split_axis="Y")
        result  = engine.generate_structured_mesh(request)
        y_maxs = sorted(BoundingBox.from_xb(m.xb).y_max for m in result.fds_meshes)
        assert y_maxs[-1] == pytest.approx(small_box.y_max)

    def test_invalid_split_axis_raises(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5,
                                        n_mpi_ranks=2, split_axis="W")
        with pytest.raises(ValueError, match="Invalid split axis"):
            engine.generate_structured_mesh(request)

    def test_custom_mesh_id_prefix(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5,
                                        n_mpi_ranks=2, mesh_id_prefix="DOMAIN")
        result  = engine.generate_structured_mesh(request)
        assert result.fds_meshes[0].id == "DOMAIN_01"

    def test_stats_total_cells(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5)
        result  = engine.generate_structured_mesh(request)
        nx, ny, nz = result.fds_meshes[0].ijk
        assert result.stats["total_cells"] == nx * ny * nz

    def test_elapsed_time_recorded(self, small_box):
        engine  = BuiltinStructuredEngine()
        request = StructuredMeshRequest(domain=small_box, target_cell_size=0.5)
        result  = engine.generate_structured_mesh(request)
        assert result.elapsed_s >= 0.0

    def test_unsupported_surface_mesh_raises(self, small_box):
        from pyfds.meshing.base import SurfaceMeshRequest
        engine  = BuiltinStructuredEngine()
        request = SurfaceMeshRequest(
            geometry=BoundingBoxGeometry(small_box),
            target_edge_length=0.5,
        )
        with pytest.raises(NotImplementedError):
            engine.generate_surface_mesh(request)
