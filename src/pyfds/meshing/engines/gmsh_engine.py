"""
PyFDS Gmsh Engine Adapter
==========================
Adapter for the Gmsh open-source meshing library.

Install:  pip install gmsh

Supports
--------
- Structured hexahedral mesh blocks (FDS compatible) via transfinite meshing
- Surface mesh generation from geometry files (STL, STEP, IGES …)
- Volume mesh generation (tetrahedral and hexahedral)
- CAD geometry import and bounding-box extraction

Gmsh API lifecycle
------------------
Each public method calls ``gmsh.initialize()`` and ``gmsh.finalize()``
to ensure clean state.  Suppress terminal output by default.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import numpy as np

from pyfds.domain.geometry import BoundingBox, GeometryHelper

from ..base import (
    BoundingBoxGeometry, ElementType, EngineCapabilities,
    FdsStructuredMesh, FileGeometry, GeometryImportRequest, GeometryResult,
    LicenseType, MeshData, MeshResult, MeshingEngineBase,
    StructuredMeshRequest, SurfaceMeshRequest, VolumeMeshRequest,
)
from .builtin import BuiltinStructuredEngine

logger = logging.getLogger(__name__)


class GmshEngine(MeshingEngineBase):
    """
    Gmsh meshing adapter.

    Handles all four operation types.  For structured FDS meshes the
    FDS block parameters are computed identically to the built-in engine;
    the Gmsh library additionally produces a full hex mesh for visualization.
    """

    name         = "gmsh"
    display_name = "Gmsh"
    priority     = 70
    license_type = LicenseType.OPEN_SOURCE
    capabilities = EngineCapabilities(
        structured_mesh=True,
        surface_mesh=True,
        volume_mesh=True,
        geometry_import=True,
        mesh_refinement=True,
        mesh_optimization=True,
        boundary_layers=True,
        parallel=True,
        formats_in=["stl", "step", "iges", "brep", "geo", "msh", "bdf", "cgns"],
        formats_out=["msh", "stl", "vtk", "med"],
    )

    @classmethod
    def is_available(cls) -> bool:
        try:
            import gmsh  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def get_version(cls) -> Optional[str]:
        try:
            import gmsh
            return gmsh.__version__
        except Exception:
            return None

    # ── Structured mesh (FDS) ─────────────────────────────────────────────────

    def generate_structured_mesh(self, request: StructuredMeshRequest) -> MeshResult:
        """
        Generate FDS mesh blocks and optionally a full hex mesh for visualization.

        FDS parameters (IJK, XB) are computed with GeometryHelper (identical to
        the built-in engine).  Gmsh additionally builds a transfinite hex mesh
        for the full domain for use in GUI visualization.
        """
        t0 = time.monotonic()

        # Compute FDS parameters using the built-in algorithm
        builtin    = BuiltinStructuredEngine()
        fds_result = builtin.generate_structured_mesh(request)
        if not fds_result.success:
            return fds_result

        # Optionally generate visualization mesh for the full domain
        mesh_data: Optional[MeshData] = None
        first = fds_result.fds_meshes[0]
        try:
            mesh_data = self._gmsh_hex_block(
                BoundingBox.from_xb(first.xb), *first.ijk
            )
        except Exception as exc:
            logger.debug("GmshEngine: visualization mesh skipped: %s", exc)

        return MeshResult(
            success=True,
            engine_used=self.name,
            fds_meshes=fds_result.fds_meshes,
            mesh_data=mesh_data,
            warnings=fds_result.warnings,
            elapsed_s=time.monotonic() - t0,
            stats=fds_result.stats,
        )

    # ── Surface mesh ──────────────────────────────────────────────────────────

    def generate_surface_mesh(self, request: SurfaceMeshRequest) -> MeshResult:
        """Generate a triangulated surface mesh using Gmsh."""
        import gmsh

        t0 = time.monotonic()
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        try:
            gmsh.model.add("surface_mesh")
            self._load_geometry(request.geometry)
            gmsh.model.occ.synchronize()

            target = request.target_edge_length
            gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target)
            gmsh.option.setNumber("Mesh.CharacteristicLengthMin",
                                  request.min_edge_length or target * 0.1)
            if request.curvature_adapt:
                gmsh.option.setNumber("Mesh.CharacteristicLengthFromCurvature", 1)

            gmsh.model.mesh.generate(2)
            gmsh.model.mesh.optimize("Laplace2D")

            vertices, triangles = self._extract_surface_mesh()
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
            logger.error("GmshEngine.generate_surface_mesh: %s", exc)
            return MeshResult.failure(self.name, str(exc))
        finally:
            gmsh.finalize()

    # ── Volume mesh ───────────────────────────────────────────────────────────

    def generate_volume_mesh(self, request: VolumeMeshRequest) -> MeshResult:
        """Generate a 3-D unstructured mesh using Gmsh."""
        import gmsh

        t0 = time.monotonic()
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        try:
            gmsh.model.add("volume_mesh")
            self._load_geometry(request.geometry)
            gmsh.model.occ.synchronize()

            gmsh.option.setNumber("Mesh.CharacteristicLengthMax", request.target_cell_size)
            if request.boundary_layers:
                gmsh.option.setNumber("Mesh.BoundaryLayerFanElements",
                                      request.n_boundary_layers)

            gmsh.model.mesh.generate(3)
            gmsh.model.mesh.optimize("Netgen")

            node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
            vertices = np.array(node_coords, dtype=np.float64).reshape(-1, 3)
            tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

            elem_type_id = 4  # TET4
            elements: Optional[np.ndarray] = None
            for et, _, node_list in zip(*gmsh.model.mesh.getElements(3)):
                if et == elem_type_id:
                    n_elems = len(node_list) // 4
                    raw = np.array(node_list, dtype=np.int64).reshape(n_elems, 4)
                    elements = np.vectorize(tag_to_idx.get)(raw).astype(np.int32)
                    break

            if elements is None:
                return MeshResult.failure(self.name, "No tetrahedral elements in output")

            mesh_data = MeshData(
                vertices=vertices,
                elements=elements,
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
                stats={"n_vertices": len(vertices), "n_elements": len(elements)},
            )
        except Exception as exc:
            logger.error("GmshEngine.generate_volume_mesh: %s", exc)
            return MeshResult.failure(self.name, str(exc))
        finally:
            gmsh.finalize()

    # ── Geometry import ───────────────────────────────────────────────────────

    def import_geometry(self, request: GeometryImportRequest) -> GeometryResult:
        """Import a CAD file and extract bounding box and surface mesh."""
        import gmsh

        t0 = time.monotonic()
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        try:
            gmsh.model.add("import")
            gmsh.merge(request.file_path)
            gmsh.model.occ.synchronize()

            if request.repair:
                try:
                    gmsh.model.occ.healShapes()
                    gmsh.model.occ.synchronize()
                except Exception:
                    pass

            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
            bbox = BoundingBox(xmin, xmax, ymin, ymax, zmin, zmax)

            gmsh.option.setNumber("Mesh.CharacteristicLengthMax",
                                  max(bbox.dx, bbox.dy, bbox.dz) / 20)
            gmsh.model.mesh.generate(2)
            vertices, triangles = self._extract_surface_mesh()

            mesh_data = MeshData(
                vertices=vertices,
                elements=triangles,
                element_type=ElementType.TRI3,
                engine_name=self.name,
                generation_time_s=time.monotonic() - t0,
            )
            return GeometryResult(
                success=True,
                engine_used=self.name,
                surface_mesh=mesh_data,
                bounding_box=bbox,
                elapsed_s=time.monotonic() - t0,
            )
        except Exception as exc:
            logger.error("GmshEngine.import_geometry: %s", exc)
            return GeometryResult.failure(self.name, str(exc))
        finally:
            gmsh.finalize()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_geometry(self, geometry) -> None:
        """Load geometry into the current Gmsh model."""
        import gmsh

        if isinstance(geometry, BoundingBoxGeometry):
            b = geometry.box
            gmsh.model.occ.addBox(b.x_min, b.y_min, b.z_min, b.dx, b.dy, b.dz)
        elif isinstance(geometry, FileGeometry):
            gmsh.merge(geometry.path)
        else:
            raise ValueError(f"GmshEngine: unsupported geometry type {type(geometry)}")

    def _extract_surface_mesh(self):
        """Return (vertices, triangles) numpy arrays from the current Gmsh model."""
        import gmsh

        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        vertices = np.array(node_coords, dtype=np.float64).reshape(-1, 3)
        tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

        tri_list = []
        for et, _, node_list in zip(*gmsh.model.mesh.getElements(2)):
            if et == 2:  # TRI3
                n_tris = len(node_list) // 3
                raw = np.array(node_list, dtype=np.int64).reshape(n_tris, 3)
                mapped = np.vectorize(tag_to_idx.get)(raw).astype(np.int32)
                tri_list.append(mapped)

        triangles = np.vstack(tri_list) if tri_list else np.zeros((0, 3), dtype=np.int32)
        return vertices, triangles

    def _gmsh_hex_block(
        self,
        box: BoundingBox,
        nx: int,
        ny: int,
        nz: int,
    ) -> MeshData:
        """Build a transfinite structured hex mesh for *box* with nx×ny×nz cells."""
        import gmsh

        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        try:
            gmsh.model.add("hex_block")
            gmsh.model.occ.addBox(box.x_min, box.y_min, box.z_min,
                                  box.dx, box.dy, box.dz)
            gmsh.model.occ.synchronize()

            # Assign transfinite node counts to each edge
            for dim, tag in gmsh.model.getEntities(1):
                bb = gmsh.model.getBoundingBox(dim, tag)
                dx_e = abs(bb[3] - bb[0])
                dy_e = abs(bb[4] - bb[1])
                dz_e = abs(bb[5] - bb[2])
                if dx_e >= dy_e and dx_e >= dz_e:
                    n_pts = nx + 1
                elif dy_e >= dz_e:
                    n_pts = ny + 1
                else:
                    n_pts = nz + 1
                gmsh.model.mesh.setTransfiniteCurve(tag, n_pts)

            for dim, tag in gmsh.model.getEntities(2):
                gmsh.model.mesh.setTransfiniteSurface(tag)
                gmsh.model.mesh.setRecombine(dim, tag)

            for dim, tag in gmsh.model.getEntities(3):
                gmsh.model.mesh.setTransfiniteVolume(tag)
                gmsh.model.mesh.setRecombine(dim, tag)

            gmsh.model.mesh.generate(3)

            node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
            vertices = np.array(node_coords, dtype=np.float64).reshape(-1, 3)
            tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

            elements = None
            for et, _, node_list in zip(*gmsh.model.mesh.getElements(3)):
                if et == 5:  # HEX8
                    n_hexes = len(node_list) // 8
                    raw = np.array(node_list, dtype=np.int64).reshape(n_hexes, 8)
                    elements = np.vectorize(tag_to_idx.get)(raw).astype(np.int32)
                    break

            if elements is None:
                raise RuntimeError("No hex elements produced")

            return MeshData(
                vertices=vertices,
                elements=elements,
                element_type=ElementType.HEX8,
                engine_name=self.name,
            )
        finally:
            gmsh.finalize()
