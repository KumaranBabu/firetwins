"""Tests for pyfds.meshing — engine registry, built-in engine, and manager. (part 1 of 1). (part 2 of 3)."""


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

@pytest.fixture()
def registry():
    """Isolated registry with only the built-in engine."""
    reg = EngineRegistry()
    reg.register(BuiltinStructuredEngine)
    return reg

@pytest.fixture()
def manager(registry):
    return MeshingManager(registry=registry)

@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Ensure each test sees a clean global registry."""
    yield
    reset_engine_registry()


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
