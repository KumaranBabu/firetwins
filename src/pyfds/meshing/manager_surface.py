"""MeshingManager: surface and volume meshing, geometry import."""
from __future__ import annotations

import time
from typing import Any, Optional

from pyfds.domain.geometry import BoundingBox
from .base import (
    BoundingBoxGeometry,
    ElementType,
    FileGeometry,
    GeometryImportRequest,
    GeometryResult,
    MeshResult,
    SurfaceMeshRequest,
    VolumeMeshRequest,
)


class MeshingManagerSurfaceMixin:
    def mesh_surface(
        self,
        geometry: Any,
        target_edge_length: float,
        min_edge_length: Optional[float] = None,
        max_edge_length: Optional[float] = None,
        curvature_adapt: bool = True,
        preferred_engine: Optional[str] = None,
    ) -> MeshResult:
        """
        Generate a triangulated surface mesh from geometry.

        *geometry* may be a ``BoundingBox``, a file path string, a
        ``SurfaceMeshGeometry``, ``BoundingBoxGeometry``, or
        ``FileGeometry`` instance.

        Install ``gmsh``, ``netgen-mesher``, or ``wildmeshing`` to enable
        this operation.
        """
        geom_input = self._normalise_geometry(geometry)
        engine = self._registry.get_engine("surface_mesh",
                                           preferred_name=preferred_engine)
        if engine is None:
            return MeshResult.failure("none",
                "No surface meshing engine available. "
                "Install gmsh, netgen-mesher, or wildmeshing.")

        request = SurfaceMeshRequest(
            geometry=geom_input,
            target_edge_length=target_edge_length,
            min_edge_length=min_edge_length,
            max_edge_length=max_edge_length,
            curvature_adapt=curvature_adapt,
            preferred_engine=preferred_engine,
        )
        self._emit("MESH_GENERATION_STARTED",
                   {"engine": engine.__class__.name, "type": "surface"})
        t0 = time.monotonic()
        try:
            result = engine.generate_surface_mesh(request)
            result.elapsed_s = time.monotonic() - t0
            self._emit("MESH_GENERATION_COMPLETED",
                       {"engine": engine.__class__.name, "type": "surface"})
            return result
        except Exception as exc:
            self._emit("MESH_GENERATION_FAILED",
                       {"engine": engine.__class__.name, "error": str(exc)})
            return MeshResult.failure(engine.__class__.name, str(exc))

    def mesh_volume(
        self,
        geometry: Any,
        target_cell_size: float,
        element_type: ElementType = ElementType.TET4,
        boundary_layers: bool = False,
        n_boundary_layers: int = 3,
        min_quality: float = 0.2,
        preferred_engine: Optional[str] = None,
    ) -> MeshResult:
        """
        Generate an unstructured volume mesh for external CFD solvers.

        Suitable for FireFOAM / OpenFOAM workflows requiring unstructured
        tetrahedral or hex-dominant grids.

        Install ``gmsh``, ``tetgen``, ``netgen-mesher``, or ``wildmeshing``
        to enable this operation.
        """
        geom_input = self._normalise_geometry(geometry)
        engine = self._registry.get_engine("volume_mesh",
                                           preferred_name=preferred_engine)
        if engine is None:
            return MeshResult.failure("none",
                "No volume meshing engine available. "
                "Install gmsh, tetgen, netgen-mesher, or wildmeshing.")

        request = VolumeMeshRequest(
            geometry=geom_input,
            target_cell_size=target_cell_size,
            element_type=element_type,
            boundary_layers=boundary_layers,
            n_boundary_layers=n_boundary_layers,
            min_quality=min_quality,
            preferred_engine=preferred_engine,
        )
        self._emit("MESH_GENERATION_STARTED",
                   {"engine": engine.__class__.name, "type": "volume"})
        t0 = time.monotonic()
        try:
            result = engine.generate_volume_mesh(request)
            result.elapsed_s = time.monotonic() - t0
            self._emit("MESH_GENERATION_COMPLETED",
                       {"engine": engine.__class__.name, "type": "volume"})
            return result
        except Exception as exc:
            self._emit("MESH_GENERATION_FAILED",
                       {"engine": engine.__class__.name, "error": str(exc)})
            return MeshResult.failure(engine.__class__.name, str(exc))

    def import_geometry(
        self,
        file_path: str,
        repair: bool = True,
        preferred_engine: Optional[str] = None,
    ) -> GeometryResult:
        """
        Import a CAD geometry file (STL, STEP, IGES, GEO …).

        Returns a ``GeometryResult`` containing the surface mesh and
        bounding box for the imported geometry.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the geometry file.
        repair:
            Attempt automatic geometry repair (fix normals, fill gaps).
        preferred_engine:
            Override automatic engine selection.
        """
        engine = self._registry.get_engine("geometry_import",
                                           preferred_name=preferred_engine)
        if engine is None:
            return GeometryResult.failure("none",
                "No geometry import engine available. "
                "Install gmsh or netgen-mesher.")

        request = GeometryImportRequest(
            file_path=file_path,
            repair=repair,
            preferred_engine=preferred_engine,
        )
        self._emit("GEOMETRY_IMPORTED",
                   {"engine": engine.__class__.name, "path": file_path})
        t0 = time.monotonic()
        try:
            result = engine.import_geometry(request)
            result.elapsed_s = time.monotonic() - t0
            return result
        except Exception as exc:
            return GeometryResult.failure(engine.__class__.name, str(exc))

    @staticmethod
    def _normalise_geometry(geometry: Any):
        """Accept BoundingBox, file path string, or geometry input object."""
        if isinstance(geometry, BoundingBox):
            return BoundingBoxGeometry(box=geometry)
        if isinstance(geometry, str):
            return FileGeometry(path=geometry)
        return geometry
