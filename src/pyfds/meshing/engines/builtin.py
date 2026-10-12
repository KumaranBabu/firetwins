"""
PyFDS Built-in Structured Meshing Engine
==========================================
Pure-Python engine for FDS structured hexahedral mesh generation.
Always available — zero external dependencies.

Capabilities
------------
- Single and multi-block FDS &MESH generation from a bounding box
- MPI domain decomposition by splitting along X, Y, or Z
- Poisson-compliant (2^a · 3^b · 5^c) cell-count enforcement
- Aspect-ratio warnings
- Fire-resolution heuristics (D*/dx) via GeometryHelper
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from pyfds.domain.geometry import BoundingBox, GeometryHelper

from ..base import (
    EngineCapabilities, FdsStructuredMesh, LicenseType,
    MeshResult, MeshingEngineBase, StructuredMeshRequest,
)


class BuiltinStructuredEngine(MeshingEngineBase):
    """
    Pure-Python structured meshing engine.

    Generates FDS &MESH blocks from a BoundingBox and target cell size.
    For multi-rank runs it splits the domain into contiguous slabs along
    the longest axis (or an explicitly specified axis).

    This engine is always selected as the fallback for structured meshing
    when no higher-priority engine is available.
    """

    name         = "builtin"
    display_name = "Built-in Structured Mesher"
    priority     = 10
    license_type = LicenseType.OPEN_SOURCE
    capabilities = EngineCapabilities(
        structured_mesh=True,
        formats_out=["fds"],
    )

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def get_version(cls) -> Optional[str]:
        try:
            from pyfds import __version__
            return __version__
        except Exception:
            return "0.3.0"

    # ── Structured mesh ───────────────────────────────────────────────────────

    def generate_structured_mesh(self, request: StructuredMeshRequest) -> MeshResult:
        t0   = time.monotonic()
        boxes = self._split_domain(request.domain, request.n_mpi_ranks, request.split_axis)
        fds_meshes: List[FdsStructuredMesh] = []
        warnings: List[str] = []

        for rank, box in enumerate(boxes):
            ijk = GeometryHelper.auto_cell_count(
                box,
                dx=request.target_cell_size,
                force_poisson=request.force_poisson,
            )
            dx, dy, dz = GeometryHelper.cell_sizes(box, ijk)
            dmin = max(min(dx, dy, dz), 1e-12)
            aspect = max(dx, dy, dz) / dmin
            if aspect > request.aspect_ratio_limit:
                warnings.append(
                    f"Block {rank + 1}: cell aspect ratio {aspect:.2f} exceeds limit "
                    f"{request.aspect_ratio_limit:.1f} — consider a finer target cell size"
                )

            if request.n_mpi_ranks > 1:
                block_id = f"{request.mesh_id_prefix}_{rank + 1:02d}"
            else:
                block_id = request.mesh_id_prefix

            fds_meshes.append(FdsStructuredMesh(
                id=block_id,
                ijk=ijk,
                xb=box.xb,
                mpi_rank=rank if request.n_mpi_ranks > 1 else None,
            ))

        total_cells = sum(m.ijk[0] * m.ijk[1] * m.ijk[2] for m in fds_meshes)
        return MeshResult(
            success=True,
            engine_used=self.name,
            fds_meshes=fds_meshes,
            warnings=warnings,
            elapsed_s=time.monotonic() - t0,
            stats={
                "total_cells": total_cells,
                "n_blocks": len(fds_meshes),
                "target_cell_size": request.target_cell_size,
            },
        )

    # ── Domain decomposition ──────────────────────────────────────────────────

    @staticmethod
    def _split_domain(
        box: BoundingBox,
        n: int,
        axis: Optional[str],
    ) -> List[BoundingBox]:
        if n <= 1:
            return [box]

        chosen = axis.upper() if axis else BuiltinStructuredEngine._longest_axis(box)

        splitters = {"X": GeometryHelper.split_x,
                     "Y": GeometryHelper.split_y,
                     "Z": GeometryHelper.split_z}
        if chosen not in splitters:
            raise ValueError(
                f"Invalid split axis: {axis!r}. Use 'X', 'Y', or 'Z'."
            )
        return splitters[chosen](box, n)

    @staticmethod
    def _longest_axis(box: BoundingBox) -> str:
        return max({"X": box.dx, "Y": box.dy, "Z": box.dz}, key=lambda k: {"X": box.dx, "Y": box.dy, "Z": box.dz}[k])
