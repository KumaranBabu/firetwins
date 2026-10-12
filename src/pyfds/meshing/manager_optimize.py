"""MeshingManager: fire-aware mesh optimisation."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from pyfds.domain.model import FdsProject


class MeshingManagerOptimizeMixin:
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
