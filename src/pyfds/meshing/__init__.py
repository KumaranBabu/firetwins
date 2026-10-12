"""
PyFDS Meshing Subsystem
========================
Multi-engine geometry and mesh generation for FDS, FireFOAM, and OpenFOAM
workflows.

Quick start
-----------
::

    from pyfds import FdsApi
    from pyfds.domain.geometry import BoundingBox

    api    = FdsApi()
    domain = BoundingBox(0, 20, 0, 10, 0, 5)

    # Detect which engines are installed
    for status in api.meshing.detect_engines():
        print(status.name, status.available, status.version)

    # Generate FDS mesh blocks (4 MPI ranks, 0.2 m cells)
    result = api.meshing.create_fds_mesh(domain, target_cell_size=0.2, n_mpi_ranks=4)
    for m in result.fds_meshes:
        api.meshes.add_mesh(ijk=list(m.ijk), xb=m.xb, id=m.id)

    # Import STL geometry and generate a surface mesh (requires gmsh)
    geo    = api.meshing.import_geometry("building.stl")
    smesh  = api.meshing.mesh_surface("building.stl", target_edge_length=0.05)

    # Generate volume mesh for FireFOAM (requires gmsh / tetgen / netgen)
    vmesh  = api.meshing.mesh_volume("building.stl", target_cell_size=0.1)

Public API
----------
The objects below are the stable public interface.
"""
from .base import (
    BoundingBoxGeometry,
    ElementType,
    EngineCapabilities,
    EngineStatus,
    FdsStructuredMesh,
    FileGeometry,
    GeometryImportRequest,
    GeometryResult,
    LicenseType,
    MeshData,
    MeshResult,
    MeshingEngine,
    MeshingEngineBase,
    StructuredMeshRequest,
    SurfaceMeshGeometry,
    SurfaceMeshRequest,
    VolumeMeshRequest,
)
from .manager import MeshingManager
from .registry import EngineRegistry, get_engine_registry, reset_engine_registry
from .engines import (
    BuiltinStructuredEngine,
    GmshEngine,
    NetgenEngine,
    TetGenEngine,
)

__all__ = [
    # Base types
    "BoundingBoxGeometry",
    "ElementType",
    "EngineCapabilities",
    "EngineStatus",
    "FdsStructuredMesh",
    "FileGeometry",
    "GeometryImportRequest",
    "GeometryResult",
    "LicenseType",
    "MeshData",
    "MeshResult",
    "MeshingEngine",
    "MeshingEngineBase",
    "StructuredMeshRequest",
    "SurfaceMeshGeometry",
    "SurfaceMeshRequest",
    "VolumeMeshRequest",
    # Manager & registry
    "MeshingManager",
    "EngineRegistry",
    "get_engine_registry",
    "reset_engine_registry",
    # Engine classes
    "BuiltinStructuredEngine",
    "GmshEngine",
    "NetgenEngine",
    "TetGenEngine",
]
