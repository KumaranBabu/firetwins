"""
PyFDS MeshingManager
=====================
High-level API for all meshing and geometry operations.

This is the object exposed as ``api.meshing`` on ``FdsApi``.  It delegates
to the ``EngineRegistry`` for engine selection and emits EventBus events
around every operation so the GUI can react without tight coupling.

Typical usage
-------------
::

    from pyfds import FdsApi
    from pyfds.domain.geometry import BoundingBox

    api = FdsApi()
    box    = BoundingBox(0, 10, 0, 10, 0, 5)
    result = api.meshing.create_fds_mesh(box, target_cell_size=0.25)
    for m in result.fds_meshes:
        api.meshes.add_mesh(ijk=list(m.ijk), xb=m.xb, id=m.id)

Engine detection
----------------
Engines are probed lazily on first use.  Call
``api.meshing.detect_engines()`` to run detection explicitly and cache
results for all subsequent calls.
"""
from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from pyfds.domain.model import FdsProject

from pyfds.domain.geometry import BoundingBox

from .base import (
    BoundingBoxGeometry, ElementType, EngineStatus,
    FileGeometry, GeometryImportRequest, GeometryResult,
    MeshResult, StructuredMeshRequest, SurfaceMeshRequest,
    VolumeMeshRequest,
)
from .registry import EngineRegistry, get_engine_registry

logger = logging.getLogger(__name__)


class MeshingManager:
    """
    Primary meshing API used by ``FdsApi``, CLI commands, and AI agents.

    Parameters
    ----------
    registry:
        Engine registry to use.  Defaults to the process-wide global.
    event_bus:
        EventBus for lifecycle events.  Defaults to the global bus when None.
    """

    def __init__(
        self,
        registry: Optional[EngineRegistry] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._registry = registry or get_engine_registry()
        self._bus      = event_bus

    # ── Structured mesh (FDS primary workflow) ────────────────────────────────

    def create_fds_mesh(
        self,
        domain: BoundingBox,
        target_cell_size: float,
        n_mpi_ranks: int = 1,
        force_poisson: bool = True,
        split_axis: Optional[str] = None,
        mesh_id_prefix: str = "MESH",
        preferred_engine: Optional[str] = None,
    ) -> MeshResult:
        """
        Generate one or more FDS-compatible structured mesh blocks.

        For ``n_mpi_ranks > 1`` the domain is split into contiguous slabs
        (one per MPI rank).  Cell counts are rounded up to Poisson numbers
        (2^a·3^b·5^c) by default.

        Parameters
        ----------
        domain:
            Full simulation domain bounding box.
        target_cell_size:
            Desired cell edge length (metres).
        n_mpi_ranks:
            Number of MPI processes; produces one MESH block per rank.
        force_poisson:
            Snap cell counts to Poisson-compliant values.
        split_axis:
            'X', 'Y', or 'Z' forces a split direction; None picks the
            longest axis automatically.
        mesh_id_prefix:
            Prefix for generated mesh IDs (e.g. "MESH" → "MESH_01").
        preferred_engine:
            Override automatic engine selection by name.

        Returns
        -------
        MeshResult
        """
        engine = self._registry.get_engine("structured_mesh",
                                           preferred_name=preferred_engine)
        if engine is None:
            return MeshResult.failure("none", "No structured meshing engine available")

        request = StructuredMeshRequest(
            domain=domain,
            target_cell_size=target_cell_size,
            n_mpi_ranks=n_mpi_ranks,
            force_poisson=force_poisson,
            split_axis=split_axis,
            mesh_id_prefix=mesh_id_prefix,
            preferred_engine=preferred_engine,
        )
        self._emit("MESH_GENERATION_STARTED",
                   {"engine": engine.__class__.name, "type": "structured"})
        t0 = time.monotonic()
        try:
            result = engine.generate_structured_mesh(request)
            result.elapsed_s = time.monotonic() - t0
            self._emit("MESH_GENERATION_COMPLETED",
                       {"engine": engine.__class__.name, "n_blocks": len(result.fds_meshes)})
            logger.info(
                "MeshingManager: structured mesh via %r — %d block(s) in %.2fs",
                engine.__class__.name, len(result.fds_meshes), result.elapsed_s,
            )
            return result
        except Exception as exc:
            self._emit("MESH_GENERATION_FAILED",
                       {"engine": engine.__class__.name, "error": str(exc)})
            logger.error("MeshingManager: structured meshing failed: %s", exc)
            return MeshResult.failure(engine.__class__.name, str(exc))

    def split_domain_for_mpi(
        self,
        domain: BoundingBox,
        n_ranks: int,
        target_cell_size: float,
        axis: Optional[str] = None,
        force_poisson: bool = True,
    ) -> MeshResult:
        """Convenience wrapper — split *domain* into *n_ranks* mesh blocks."""
        return self.create_fds_mesh(
            domain=domain,
            target_cell_size=target_cell_size,
            n_mpi_ranks=n_ranks,
            force_poisson=force_poisson,
            split_axis=axis,
        )

    # ── Surface meshing ───────────────────────────────────────────────────────

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

    # ── Volume meshing (FireFOAM / OpenFOAM) ──────────────────────────────────

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

    # ── Geometry import ───────────────────────────────────────────────────────

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

    # ── Engine management ─────────────────────────────────────────────────────

    def detect_engines(self, force: bool = False) -> List[EngineStatus]:
        """
        Probe all registered engines and return detection results.

        Results are cached; pass ``force=True`` to re-probe (e.g. after
        installing a new meshing library).
        """
        statuses = self._registry.detect_all(force=force)
        self._emit("MESH_ENGINE_DETECTED", {"statuses": statuses})
        return statuses

    def available_engines(self) -> List[EngineStatus]:
        """Return status objects for all currently-available engines."""
        return self._registry.available_engines()

    def engine_status(self, engine_name: str) -> Optional[EngineStatus]:
        """Return the detection status for a specific engine by name."""
        return self._registry.status(engine_name)

    def set_preferred_engine(self, capability: str, engine_name: str) -> None:
        """
        Pin *engine_name* for *capability*.

        Pass ``engine_name=''`` to clear and revert to automatic selection.

        Valid capability names:
            structured_mesh, surface_mesh, volume_mesh, geometry_import,
            mesh_refinement, mesh_optimization, boundary_layers
        """
        self._registry.set_preferred(capability, engine_name)

    def register_engine(self, engine_class: Any) -> None:
        """
        Register a third-party engine class with the registry.

        The class must subclass ``MeshingEngineBase`` or implement the
        ``MeshingEngine`` protocol.
        """
        self._registry.register(engine_class)

    # ── Fire-driven mesh optimisation ────────────────────────────────────────

    def optimize_for_fire(
        self,
        project: "FdsProject",
        surf_id: str,
        target_ratio: float = 10.0,
        fire_area: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Recommend cell sizes based on the D* / dx criterion for a fire surface.

        Uses the characteristic fire diameter D* (McGrattan et al., FDS Guide):

            D* = (Q̇ / (ρ∞ · cₚ · T∞ · √g))^0.4

        where Q̇ is the total fire HRR in kW.  The recommended cell size is
        ``D* / target_ratio``; FDS guidance suggests 10 ≤ D*/dx ≤ 20 for
        well-resolved flames.

        Parameters
        ----------
        project:
            The FdsProject whose meshes and surfaces are inspected.
        surf_id:
            Name of the burning SURF entity (must have ``heat_release_rate``
            set — i.e. HRRPUA in kW/m²).
        target_ratio:
            Desired D*/dx ratio (default 10).
        fire_area:
            Override the estimated fire area (m²).  When *None* the method
            sums the horizontal footprint of all OBSTructions referencing
            *surf_id*; if none are found, 1 m² is assumed.

        Returns
        -------
        dict with keys:
            ``surf_id``, ``hrrpua_kW_m2``, ``fire_area_m2``, ``Q_total_kW``,
            ``D_star_m``, ``recommended_dx_m``, ``target_ratio``,
            ``meshes``  — per-mesh dict with ``current_dx``, ``action``,
                          and ``message``.
        """
        # ── 1. Locate the surface ─────────────────────────────────────────────
        surface = next(
            (s for s in project.surfaces if s.name == surf_id), None
        )
        hrrpua = (surface.heat_release_rate if surface is not None else None) or 0.0

        # ── 2. Estimate fire area ─────────────────────────────────────────────
        if fire_area is None:
            area = 0.0
            for obst in project.obstructions:
                if obst.surface_id == surf_id:
                    dx = abs(obst.x_max - obst.x_min)
                    dy = abs(obst.y_max - obst.y_min)
                    dz = abs(obst.z_max - obst.z_min)
                    dims = sorted([dx, dy, dz])
                    # smallest two dims give the burning face footprint
                    area += dims[0] * dims[1] if dims[0] > 0 else dims[1] * dims[2]
            fire_area = area if area > 0.0 else 1.0

        q_total = hrrpua * fire_area  # kW

        # ── 3. Compute D* ─────────────────────────────────────────────────────
        # D* = (Q / (rho * cp * T * sqrt(g)))^0.4  [SI: kW, kg/m³, kJ/(kg·K), K, m/s²]
        rho  = 1.2      # kg/m³
        cp   = 1.0      # kJ/(kg·K)
        t_amb = 293.0   # K
        g    = 9.81     # m/s²
        denom = rho * cp * t_amb * math.sqrt(g)  # kW·m^{-2.5}
        d_star = (q_total / denom) ** 0.4 if q_total > 0 else 0.0
        recommended_dx = d_star / target_ratio if d_star > 0 else None

        # ── 4. Assess existing meshes ─────────────────────────────────────────
        mesh_report: Dict[str, Dict[str, Any]] = {}
        for mesh in project.meshes:
            lx = abs(mesh.x_max - mesh.x_min)
            ly = abs(mesh.y_max - mesh.y_min)
            lz = abs(mesh.z_max - mesh.z_min)
            nx, ny, nz = mesh.cell_count
            dx = lx / nx if nx else float("inf")
            dy = ly / ny if ny else float("inf")
            dz = lz / nz if nz else float("inf")
            current_dx = max(dx, dy, dz)

            if recommended_dx is None or d_star == 0:
                action = "unknown"
                msg = "Cannot determine — HRRPUA is 0 or surface not found."
            else:
                ratio = d_star / current_dx
                if ratio >= target_ratio * 0.9:
                    action = "ok"
                    msg = f"D*/dx ≈ {ratio:.1f} — within target ({target_ratio})."
                elif ratio >= target_ratio * 0.5:
                    action = "refine"
                    msg = (
                        f"D*/dx ≈ {ratio:.1f} — below target. "
                        f"Refine to ≤ {recommended_dx:.3f} m."
                    )
                else:
                    action = "coarsen_or_refine"
                    msg = (
                        f"D*/dx ≈ {ratio:.1f} — significantly under-resolved. "
                        f"Target dx ≤ {recommended_dx:.3f} m."
                    )

            mesh_report[mesh.name] = {
                "current_dx": round(current_dx, 5),
                "action": action,
                "message": msg,
            }

        return {
            "surf_id":           surf_id,
            "hrrpua_kW_m2":      hrrpua,
            "fire_area_m2":      round(fire_area, 4),
            "Q_total_kW":        round(q_total, 3),
            "D_star_m":          round(d_star, 4),
            "recommended_dx_m":  round(recommended_dx, 4) if recommended_dx else None,
            "target_ratio":      target_ratio,
            "meshes":            mesh_report,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _normalise_geometry(geometry: Any):
        """Accept BoundingBox, file path string, or geometry input object."""
        if isinstance(geometry, BoundingBox):
            return BoundingBoxGeometry(box=geometry)
        if isinstance(geometry, str):
            return FileGeometry(path=geometry)
        return geometry

    def _emit(self, event_name: str, payload: Any = None) -> None:
        bus = self._bus
        if bus is None:
            try:
                from pyfds.core.events import get_global_bus
                bus = get_global_bus()
            except Exception:
                return
        try:
            from pyfds.core.events import EventType
            etype = getattr(EventType, event_name, None)
            if etype:
                bus.emit(etype, payload, source="MeshingManager")
        except Exception:
            pass
