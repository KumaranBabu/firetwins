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
import time
from typing import TYPE_CHECKING, Any, List, Optional

from pyfds.domain.geometry import BoundingBox
from .base import EngineStatus, MeshResult, StructuredMeshRequest
from .registry import EngineRegistry, get_engine_registry

from .manager_optimize import (  # noqa: F401  (re-exported)
    MeshingManagerOptimizeMixin,
)
from .manager_surface import (  # noqa: F401  (re-exported)
    MeshingManagerSurfaceMixin,
)


if TYPE_CHECKING:
    from pyfds.domain.model import FdsProject


logger = logging.getLogger(__name__)


class MeshingManager(MeshingManagerOptimizeMixin, MeshingManagerSurfaceMixin):
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
