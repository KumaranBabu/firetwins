"""Tests for pyfds.meshing — engine registry, built-in engine, and manager. (part 1 of 1). (part 3 of 3)."""


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


@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Ensure each test sees a clean global registry."""
    yield
    reset_engine_registry()

gmsh_available   = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("gmsh"),
    reason="gmsh not installed",
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
