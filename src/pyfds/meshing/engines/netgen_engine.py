"""
PyFDS Netgen Engine Adapter
============================
Adapter for the Netgen mesh generator (part of NGSolve / netgen-mesher).

Install:  pip install netgen-mesher   (standalone)
          pip install ngsolve          (full solver suite, includes netgen)

Supports
--------
- Surface and volume meshing via Netgen's native API
- CAD geometry import through netgen.occ (OpenCASCADE wrapper)
  for STEP, IGES, BREP, and STL files
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from ..base import (
    BoundingBoxGeometry, ElementType, EngineCapabilities,
    FileGeometry, GeometryImportRequest, GeometryResult,
    LicenseType, MeshData, MeshResult, MeshingEngineBase,
    SurfaceMeshRequest, VolumeMeshRequest,
)
from pyfds.domain.geometry import BoundingBox

logger = logging.getLogger(__name__)


class NetgenEngine(MeshingEngineBase):
    """
    Netgen meshing adapter.

    Netgen provides high-quality isotropic and anisotropic meshes using
    an advancing-front algorithm.  OpenCASCADE geometry is handled through
    ``netgen.occ`` when available.
    """

    name         = "netgen"
    display_name = "Netgen"
    priority     = 60
    license_type = LicenseType.OPEN_SOURCE
    capabilities = EngineCapabilities(
        surface_mesh=True,
        volume_mesh=True,
        geometry_import=True,
        mesh_refinement=True,
        mesh_optimization=True,
        formats_in=["stl", "step", "iges", "brep"],
        formats_out=["vol", "vtk", "msh"],
    )

    @classmethod
    def is_available(cls) -> bool:
        try:
            import netgen  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def get_version(cls) -> Optional[str]:
        try:
            import netgen
            return getattr(netgen, "__version__", None)
        except Exception:
            return None

    # ── Surface mesh ──────────────────────────────────────────────────────────

    def generate_surface_mesh(self, request: SurfaceMeshRequest) -> MeshResult:
        """Generate a triangulated surface mesh using Netgen."""
        t0 = time.monotonic()
        try:
            geo  = self._load_netgen_geometry(request.geometry)
            mesh = geo.GenerateMesh(
                maxh=request.target_edge_length,
                minh=request.min_edge_length or 0.0,
            )
            mesh.Refine()

            vertices, triangles = self._extract_surface(mesh)
            mesh_data = MeshData(
                vertices=vertices,
                elements=triangles,
                element_type=ElementType.TRI3,
                engine_name=self.name,
                generation_time_s=time.monotonic() - t0,
            )
            return MeshResult(
                success=True,
                engine_used=self.name,
                fds_meshes=[],
                mesh_data=mesh_data,
                elapsed_s=time.monotonic() - t0,
                stats={"n_vertices": len(vertices), "n_triangles": len(triangles)},
            )
        except Exception as exc:
            logger.error("NetgenEngine.generate_surface_mesh: %s", exc)
            return MeshResult.failure(self.name, str(exc))

    # ── Volume mesh ───────────────────────────────────────────────────────────

    def generate_volume_mesh(self, request: VolumeMeshRequest) -> MeshResult:
        """Generate a tetrahedral volume mesh using Netgen."""
        t0 = time.monotonic()
        try:
            geo  = self._load_netgen_geometry(request.geometry)
            mesh = geo.GenerateMesh(maxh=request.target_cell_size)

            vertices, tets = self._extract_volume(mesh)
            mesh_data = MeshData(
                vertices=vertices,
                elements=tets,
                element_type=ElementType.TET4,
                engine_name=self.name,
                generation_time_s=time.monotonic() - t0,
            )
            return MeshResult(
                success=True,
                engine_used=self.name,
                fds_meshes=[],
                mesh_data=mesh_data,
                elapsed_s=time.monotonic() - t0,
                stats={"n_vertices": len(vertices), "n_elements": len(tets)},
            )
        except Exception as exc:
            logger.error("NetgenEngine.generate_volume_mesh: %s", exc)
            return MeshResult.failure(self.name, str(exc))

    # ── Geometry import ───────────────────────────────────────────────────────

    def import_geometry(self, request: GeometryImportRequest) -> GeometryResult:
        """Import CAD geometry via Netgen/OCC and extract surface mesh + bounding box."""
        t0 = time.monotonic()
        try:
            from netgen.occ import OCCGeometry
            geo  = OCCGeometry(request.file_path)
            mesh = geo.GenerateMesh(maxh=1e10)  # coarse pass for bbox/surface

            vertices, triangles = self._extract_surface(mesh)

            bb_min = vertices.min(axis=0)
            bb_max = vertices.max(axis=0)
            bbox   = BoundingBox(
                bb_min[0], bb_max[0],
                bb_min[1], bb_max[1],
                bb_min[2], bb_max[2],
            )
            mesh_data = MeshData(
                vertices=vertices,
                elements=triangles,
                element_type=ElementType.TRI3,
                engine_name=self.name,
            )
            return GeometryResult(
                success=True,
                engine_used=self.name,
                surface_mesh=mesh_data,
                bounding_box=bbox,
                elapsed_s=time.monotonic() - t0,
            )
        except Exception as exc:
            logger.error("NetgenEngine.import_geometry: %s", exc)
            return GeometryResult.failure(self.name, str(exc))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_netgen_geometry(self, geometry):
        """Convert a GeometryInput into a Netgen geometry object."""
        from netgen.meshing import MeshingParameters

        if isinstance(geometry, BoundingBoxGeometry):
            from netgen.csg import CSGeometry, OrthoBrick, Pnt
            b   = geometry.box
            geo = CSGeometry()
            geo.Add(OrthoBrick(Pnt(b.x_min, b.y_min, b.z_min),
                               Pnt(b.x_max, b.y_max, b.z_max)))
            return geo

        if isinstance(geometry, FileGeometry):
            path = geometry.path.lower()
            if path.endswith(".stl"):
                from netgen.stl import STLGeometry
                return STLGeometry(geometry.path)
            try:
                from netgen.occ import OCCGeometry
                return OCCGeometry(geometry.path)
            except Exception as exc:
                raise ValueError(
                    f"NetgenEngine: cannot load {geometry.path!r}: {exc}"
                ) from exc

        raise ValueError(f"NetgenEngine: unsupported geometry type {type(geometry)}")

    @staticmethod
    def _extract_surface(mesh) -> tuple:
        pts   = np.array([[p[0], p[1], p[2]] for p in mesh.Points()], dtype=np.float64)
        tris  = []
        for el in mesh.Elements2D():
            tris.append([int(v.nr) - 1 for v in el.vertices])
        tris_arr = np.array(tris, dtype=np.int32) if tris else np.zeros((0, 3), np.int32)
        return pts, tris_arr

    @staticmethod
    def _extract_volume(mesh) -> tuple:
        pts  = np.array([[p[0], p[1], p[2]] for p in mesh.Points()], dtype=np.float64)
        tets = []
        for el in mesh.Elements3D():
            tets.append([int(v.nr) - 1 for v in el.vertices])
        tets_arr = np.array(tets, dtype=np.int32) if tets else np.zeros((0, 4), np.int32)
        return pts, tets_arr
