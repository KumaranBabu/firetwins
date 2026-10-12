"""
Tests for pyfds.meshing — engine registry, built-in engine, and manager.

All tests run without any optional meshing library installed.
External-engine tests are skipped unless the library is present.
"""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def small_box():
    return BoundingBox(0.0, 4.0, 0.0, 4.0, 0.0, 3.0)


@pytest.fixture()
def registry():
    """Isolated registry with only the built-in engine."""
    reg = EngineRegistry()
    reg.register(BuiltinStructuredEngine)
    return reg


@pytest.fixture()
def manager(registry):
    return MeshingManager(registry=registry)


# ---------------------------------------------------------------------------
# EngineCapabilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# BuiltinStructuredEngine — availability and detection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# BuiltinStructuredEngine — structured mesh generation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# EngineRegistry
# ---------------------------------------------------------------------------

class TestEngineRegistry:
    def test_register_and_detect(self, registry):
        statuses = registry.detect_all()
        names = [s.name for s in statuses]
        assert "builtin" in names

    def test_builtin_is_available(self, registry):
        registry.detect_all()
        status = registry.status("builtin")
        assert status is not None
        assert status.available is True

    def test_get_engine_structured_returns_builtin(self, registry):
        engine = registry.get_engine("structured_mesh")
        assert engine is not None
        assert engine.__class__.name == "builtin"

    def test_get_engine_surface_returns_none_without_optional_libs(self, registry):
        engine = registry.get_engine("surface_mesh")
        assert engine is None   # no surface engines in this isolated registry

    def test_register_idempotent(self, registry):
        before = len(registry)
        registry.register(BuiltinStructuredEngine)
        assert len(registry) == before

    def test_unregister(self, registry):
        removed = registry.unregister("builtin")
        assert removed is True
        assert len(registry) == 0

    def test_set_preferred(self, registry):
        registry.set_preferred("structured_mesh", "builtin")
        assert registry.get_preferred("structured_mesh") == "builtin"

    def test_clear_preferred(self, registry):
        registry.set_preferred("structured_mesh", "builtin")
        registry.set_preferred("structured_mesh", "")
        assert registry.get_preferred("structured_mesh") is None

    def test_detect_force_re_probes(self, registry):
        registry.detect_all()
        statuses1 = registry.detect_all(force=True)
        assert any(s.name == "builtin" for s in statuses1)

    def test_unknown_capability_returns_none(self, registry):
        engine = registry.get_engine("nonexistent_capability")
        assert engine is None

    def test_all_registered_names(self, registry):
        assert "builtin" in registry.all_registered_names()


# ---------------------------------------------------------------------------
# MeshingManager
# ---------------------------------------------------------------------------

class TestMeshingManager:
    def test_create_fds_mesh_success(self, manager, small_box):
        result = manager.create_fds_mesh(small_box, target_cell_size=0.5)
        assert result.success is True
        assert len(result.fds_meshes) == 1

    def test_create_fds_mesh_mpi(self, manager, small_box):
        result = manager.create_fds_mesh(small_box, target_cell_size=0.5, n_mpi_ranks=2)
        assert len(result.fds_meshes) == 2

    def test_split_domain_for_mpi(self, manager, small_box):
        result = manager.split_domain_for_mpi(small_box, n_ranks=3,
                                               target_cell_size=0.5)
        assert len(result.fds_meshes) == 3

    def test_mesh_surface_no_engine(self, manager, small_box):
        result = manager.mesh_surface(small_box, target_edge_length=0.1)
        assert result.success is False
        assert "No surface meshing engine" in result.errors[0]

    def test_mesh_volume_no_engine(self, manager, small_box):
        result = manager.mesh_volume(small_box, target_cell_size=0.1)
        assert result.success is False
        assert "No volume meshing engine" in result.errors[0]

    def test_import_geometry_no_engine(self, manager):
        result = manager.import_geometry("nonexistent.stl")
        assert result.success is False

    def test_detect_engines_returns_list(self, manager):
        statuses = manager.detect_engines()
        assert isinstance(statuses, list)
        assert any(s.name == "builtin" for s in statuses)

    def test_available_engines_builtin(self, manager):
        manager.detect_engines()
        available = manager.available_engines()
        assert any(s.name == "builtin" for s in available)

    def test_engine_status_lookup(self, manager):
        manager.detect_engines()
        status = manager.engine_status("builtin")
        assert status is not None
        assert status.available is True

    def test_set_preferred_engine(self, manager):
        manager.set_preferred_engine("structured_mesh", "builtin")
        engine = manager._registry.get_engine("structured_mesh")
        assert engine.__class__.name == "builtin"

    def test_geometry_normalise_bounding_box(self):
        box = BoundingBox(0, 1, 0, 1, 0, 1)
        result = MeshingManager._normalise_geometry(box)
        assert isinstance(result, BoundingBoxGeometry)
        assert result.box is box

    def test_geometry_normalise_string(self):
        from pyfds.meshing.base import FileGeometry
        result = MeshingManager._normalise_geometry("/tmp/mesh.stl")
        assert isinstance(result, FileGeometry)
        assert result.path == "/tmp/mesh.stl"

    def test_register_engine(self, manager):
        class DummyEngine(MeshingEngineBase):
            name         = "dummy"
            display_name = "Dummy"
            priority     = 5
            license_type = LicenseType.OPEN_SOURCE
            capabilities = EngineCapabilities()

            @classmethod
            def is_available(cls):
                return True

        manager.register_engine(DummyEngine)
        assert "dummy" in manager._registry.all_registered_names()


# ---------------------------------------------------------------------------
# MeshResult helpers
# ---------------------------------------------------------------------------

class TestMeshResult:
    def test_failure_classmethod(self):
        result = MeshResult.failure("test_engine", "something went wrong")
        assert result.success is False
        assert result.engine_used == "test_engine"
        assert result.errors[0] == "something went wrong"
        assert result.fds_meshes == []

    def test_failed_property(self):
        ok  = MeshResult(success=True, engine_used="x", fds_meshes=[])
        bad = MeshResult.failure("x", "oops")
        assert ok.failed is False
        assert bad.failed is True


# ---------------------------------------------------------------------------
# FdsApi integration
# ---------------------------------------------------------------------------

class TestFdsApiIntegration:
    def test_api_has_meshing_manager(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert hasattr(api, "meshing")
        assert isinstance(api.meshing, MeshingManager)

    def test_api_meshing_create_fds_mesh(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        box = BoundingBox(0, 8, 0, 8, 0, 4)
        result = api.meshing.create_fds_mesh(box, target_cell_size=0.5)
        assert result.success is True
        nx, ny, nz = result.fds_meshes[0].ijk
        assert nx == 16  # 8/0.5=16 (Poisson ✓)
        assert ny == 16
        assert nz == 8

    def test_api_meshing_detect_engines(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        statuses = api.meshing.detect_engines()
        assert any(s.name == "builtin" and s.available for s in statuses)


# ---------------------------------------------------------------------------
# Global registry reset (prevents test-order pollution)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Ensure each test sees a clean global registry."""
    yield
    reset_engine_registry()


# ---------------------------------------------------------------------------
# Skip markers for optional engines
# ---------------------------------------------------------------------------

gmsh_available   = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("gmsh"),
    reason="gmsh not installed",
)
netgen_available = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("netgen"),
    reason="netgen-mesher not installed",
)


def _tetgen_binary_available() -> bool:
    from pyfds.meshing.engines.tetgen_engine import _find_tetgen_exe
    return _find_tetgen_exe() is not None


tetgen_available = pytest.mark.skipif(
    not _tetgen_binary_available(),
    reason="tetgen binary not found (set TETGEN_EXE or place tetgen.exe in C:\\bin\\)",
)


@gmsh_available
class TestGmshEngineAvailability:
    def test_is_available(self):
        from pyfds.meshing.engines.gmsh_engine import GmshEngine
        assert GmshEngine.is_available() is True

    def test_has_version(self):
        from pyfds.meshing.engines.gmsh_engine import GmshEngine
        ver = GmshEngine.get_version()
        assert ver is not None

    def test_structured_mesh_returns_fds_blocks(self):
        from pyfds.meshing.engines.gmsh_engine import GmshEngine
        engine  = GmshEngine()
        box     = BoundingBox(0, 4, 0, 4, 0, 2)
        request = StructuredMeshRequest(domain=box, target_cell_size=0.5)
        result  = engine.generate_structured_mesh(request)
        assert result.success is True
        assert len(result.fds_meshes) >= 1


@tetgen_available
class TestTetGenEngineAvailability:
    def test_is_available(self):
        from pyfds.meshing.engines.tetgen_engine import TetGenEngine
        assert TetGenEngine.is_available() is True

    def test_get_version_returns_string(self):
        from pyfds.meshing.engines.tetgen_engine import TetGenEngine
        ver = TetGenEngine.get_version()
        assert ver is not None
        assert isinstance(ver, str)

    def test_binary_path_resolves(self):
        from pyfds.meshing.engines.tetgen_engine import _find_tetgen_exe
        exe = _find_tetgen_exe()
        assert exe is not None
        assert exe.is_file()
