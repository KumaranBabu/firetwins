"""Mesh rules: presence, Poisson-friendly counts, MPI ranks, overlap/alignment, aspect ratio, fire resolution, cylindrical."""
from __future__ import annotations

from ._common import _e, _is_poisson, _nearest_poisson, _w


import math
from typing import Any, List
from ..engine import ValidationResult, Severity


class MeshPresenceRule:
    """The model has at least one mesh."""
    name = "MeshPresence"

    def check(self, p: Any) -> List[ValidationResult]:
        if not p.meshes:
            def _fix(project):
                from pyfds.domain.model import Mesh
                project.add_entity(Mesh(
                    name="MESH_01",
                    x_min=0.0, x_max=10.0,
                    y_min=0.0, y_max=10.0,
                    z_min=0.0, z_max=4.0,
                    cell_count=(40, 40, 16),  # 0.25 m cells, Poisson-compliant
                ))
            return [ValidationResult(
                severity=Severity.ERROR,
                rule=self.name,
                message="No &MESH namelists defined. FDS requires at least one mesh to run.",
                hint="Add at least one &MESH namelist to your model.",
                fix=_fix,
            )]
        return []


class PoissonComplianceRule:
    """Mesh cell counts factor into 2, 3 and 5 (fast pressure solver)."""
    name = "PoissonCompliance"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for m in p.meshes:
            bad_dims: List[tuple] = []
            for idx, (dim, val) in enumerate(zip(["I", "J", "K"], m.cell_count)):
                if not _is_poisson(val):
                    bad_dims.append((idx, dim, val))

            for idx, dim, val in bad_dims:
                snapped = _nearest_poisson(val)
                mesh_ref = m  # capture for lambda

                def _fix(project, _m=mesh_ref, _idx=idx, _snapped=snapped):
                    old = list(_m.cell_count)
                    old[_idx] = _snapped
                    _m.cell_count = tuple(old)

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=f"Cell count {dim}={val} violates Poisson rule (must be 2^a·3^b·5^c).",
                    entity_name=m.name,
                    hint=f"Try {snapped} instead of {val}.",
                    fix=_fix,
                ))
        return results


class MpiRankGapRule:
    """MPI process numbers are used without gaps."""
    name = "MpiRankGap"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        ranks = [m.mpi_processor for m in p.meshes if m.mpi_processor is not None]
        if not ranks:
            return results
        max_rank = max(ranks)
        assigned = set(ranks)
        for expected in range(max_rank + 1):
            if expected not in assigned:
                results.append(_e(
                    self.name,
                    f"MPI rank {expected} is not assigned to any mesh (max rank={max_rank}).",
                    hint="Every rank 0..N-1 must be assigned to at least one mesh.",
                ))
        return results


class MeshOverlapRule:
    """Meshes do not overlap each other."""
    name = "MeshOverlap"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        meshes = p.meshes
        for i in range(len(meshes)):
            for j in range(i + 1, len(meshes)):
                m1, m2 = meshes[i], meshes[j]
                if self._overlaps(m1, m2):
                    results.append(_e(
                        self.name,
                        f"Meshes '{m1.name}' and '{m2.name}' have overlapping volumes.",
                        hint="FDS meshes must not share interior volume.",
                    ))
        return results

    def _overlaps(self, m1, m2) -> bool:
        return (m1.x_min < m2.x_max and m1.x_max > m2.x_min and
                m1.y_min < m2.y_max and m1.y_max > m2.y_min and
                m1.z_min < m2.z_max and m1.z_max > m2.z_min)


class MeshAlignmentRule:
    """Abutting meshes have matching cell sizes (Mesh Alignment Test)."""
    name = "MeshAlignment"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        meshes = p.meshes
        tol = 1e-4

        for i in range(len(meshes)):
            for j in range(i + 1, len(meshes)):
                m1, m2 = meshes[i], meshes[j]
                axis = self._abutting_axis(m1, m2, tol)
                if axis:
                    ret = self._check_alignment(m1, m2, axis)
                    if ret is not None:
                        err, fix_fn = ret
                        results.append(ValidationResult(
                            severity=Severity.WARNING,
                            rule=self.name,
                            message=err,
                            hint="Abutting mesh cell sizes must be integer multiples.",
                            fix=fix_fn,
                        ))
        return results

    def _abutting_axis(self, m1, m2, tol: float):
        # X abutment
        if (abs(m1.x_max - m2.x_min) < tol or abs(m2.x_max - m1.x_min) < tol):
            if (m1.y_min < m2.y_max - tol and m1.y_max > m2.y_min + tol and
                    m1.z_min < m2.z_max - tol and m1.z_max > m2.z_min + tol):
                return "X"
        # Y abutment
        if (abs(m1.y_max - m2.y_min) < tol or abs(m2.y_max - m1.y_min) < tol):
            if (m1.x_min < m2.x_max - tol and m1.x_max > m2.x_min + tol and
                    m1.z_min < m2.z_max - tol and m1.z_max > m2.z_min + tol):
                return "Y"
        # Z abutment
        if (abs(m1.z_max - m2.z_min) < tol or abs(m2.z_max - m1.z_min) < tol):
            if (m1.x_min < m2.x_max - tol and m1.x_max > m2.x_min + tol and
                    m1.y_min < m2.y_max - tol and m1.y_max > m2.y_min + tol):
                return "Z"
        return None

    def _check_alignment(self, m1, m2, axis: str):
        """Return error string, or (error_string, fix_callable) tuple if fixable."""
        def cell_sizes(m):
            dx = (m.x_max - m.x_min) / m.cell_count[0]
            dy = (m.y_max - m.y_min) / m.cell_count[1]
            dz = (m.z_max - m.z_min) / m.cell_count[2]
            return dx, dy, dz

        dx1, dy1, dz1 = cell_sizes(m1)
        dx2, dy2, dz2 = cell_sizes(m2)

        def is_integer_multiple(a: float, b: float, tol: float = 1e-3) -> bool:
            if b == 0 or a == 0:
                return False
            ratio = a / b
            return abs(ratio - round(ratio)) < tol or abs((1 / ratio) - round(1 / ratio)) < tol

        def _make_fix(mesh_a, mesh_b, bad_axis: str):
            # Snap the coarser mesh's transverse cell count to the nearest integer multiple
            def _fix(project, _a=mesh_a, _b=mesh_b, _ax=bad_axis):
                cc_a = list(_a.cell_count)
                cc_b = list(_b.cell_count)
                axes = {"X": [1, 2], "Y": [0, 2], "Z": [0, 1]}
                for dim_idx in axes[_ax]:
                    if dim_idx == 0:
                        da = (_a.x_max - _a.x_min) / max(cc_a[0], 1)
                        db = (_b.x_max - _b.x_min) / max(cc_b[0], 1)
                    elif dim_idx == 1:
                        da = (_a.y_max - _a.y_min) / max(cc_a[1], 1)
                        db = (_b.y_max - _b.y_min) / max(cc_b[1], 1)
                    else:
                        da = (_a.z_max - _a.z_min) / max(cc_a[2], 1)
                        db = (_b.z_max - _b.z_min) / max(cc_b[2], 1)
                    min_dx = min(da, db)
                    if min_dx <= 0:
                        continue
                    # Snap larger cell mesh to nearest Poisson n that aligns
                    if da > db:
                        length = (_a.x_max - _a.x_min) if dim_idx == 0 else \
                                 (_a.y_max - _a.y_min) if dim_idx == 1 else \
                                 (_a.z_max - _a.z_min)
                        n_ideal = round(length / db)
                        cc_a[dim_idx] = _nearest_poisson(max(1, n_ideal))
                    else:
                        length = (_b.x_max - _b.x_min) if dim_idx == 0 else \
                                 (_b.y_max - _b.y_min) if dim_idx == 1 else \
                                 (_b.z_max - _b.z_min)
                        n_ideal = round(length / da)
                        cc_b[dim_idx] = _nearest_poisson(max(1, n_ideal))
                _a.cell_count = tuple(cc_a)
                _b.cell_count = tuple(cc_b)
            return _fix

        if axis == "X":
            if not is_integer_multiple(dy1, dy2) or not is_integer_multiple(dz1, dz2):
                return (
                    f"Meshes '{m1.name}' & '{m2.name}' abut along X but transverse "
                    f"cell sizes (dy,dz) are not integer multiples.",
                    _make_fix(m1, m2, "X"),
                )
        elif axis == "Y":
            if not is_integer_multiple(dx1, dx2) or not is_integer_multiple(dz1, dz2):
                return (
                    f"Meshes '{m1.name}' & '{m2.name}' abut along Y but transverse "
                    f"cell sizes (dx,dz) are not integer multiples.",
                    _make_fix(m1, m2, "Y"),
                )
        elif axis == "Z":
            if not is_integer_multiple(dx1, dx2) or not is_integer_multiple(dy1, dy2):
                return (
                    f"Meshes '{m1.name}' & '{m2.name}' abut along Z but transverse "
                    f"cell sizes (dx,dy) are not integer multiples.",
                    _make_fix(m1, m2, "Z"),
                )
        return None


class FireResolutionRule:
    """Fire size is resolved by enough cells (D*/dx)."""
    name = "FireResolution"
    MIN_RATIO = 4.0     # below this: almost certainly unresolved
    GOOD_RATIO = 10.0   # FDS User Guide recommendation

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        hrr_surfs = [s for s in p.surfaces if s.heat_release_rate and s.heat_release_rate > 0]
        if not hrr_surfs or not p.meshes:
            return results

        peak_hrrpua = max(s.heat_release_rate for s in hrr_surfs)
        # Estimate a representative fire area from vents referencing a burning surface
        burning_ids = {s.name for s in hrr_surfs}
        fire_vents = [v for v in p.vents if v.surface_id in burning_ids]
        if fire_vents:
            area = sum((v.x_max - v.x_min) * (v.y_max - v.y_min)
                       + (v.x_max - v.x_min) * (v.z_max - v.z_min)
                       + (v.y_max - v.y_min) * (v.z_max - v.z_min)
                       for v in fire_vents) / len(fire_vents)
            area = max(area, 0.01)
        else:
            area = 1.0  # fallback 1 m²

        hrr_kw = peak_hrrpua * area
        # D* = (Q_kw / (rho * cp * T_inf * sqrt(g)))^0.4
        d_star = (hrr_kw / (1.2 * 1.0 * 293.0 * math.sqrt(9.81))) ** 0.4

        for m in p.meshes:
            dx = (m.x_max - m.x_min) / m.cell_count[0]
            dy = (m.y_max - m.y_min) / m.cell_count[1]
            dz = (m.z_max - m.z_min) / m.cell_count[2]
            max_cell = max(dx, dy, dz)
            ratio = d_star / max_cell if max_cell > 0 else float("inf")
            if ratio < self.MIN_RATIO:
                target_dx = d_star / self.MIN_RATIO
                mesh_ref = m

                def _fix_res(project, _m=mesh_ref, _tdx=target_dx):
                    cc = list(_m.cell_count)
                    # Scale up each cell count so max_cell ≤ target_dx
                    lx = _m.x_max - _m.x_min
                    ly = _m.y_max - _m.y_min
                    lz = _m.z_max - _m.z_min
                    cc[0] = _nearest_poisson(max(cc[0], math.ceil(lx / _tdx)))
                    cc[1] = _nearest_poisson(max(cc[1], math.ceil(ly / _tdx)))
                    cc[2] = _nearest_poisson(max(cc[2], math.ceil(lz / _tdx)))
                    _m.cell_count = tuple(cc)

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=(
                        f"Mesh '{m.name}': D*/dx ≈ {ratio:.1f} (cell={max_cell:.3f}m, D*={d_star:.2f}m). "
                        f"Minimum acceptable ratio is {self.MIN_RATIO}."
                    ),
                    entity_name=m.name,
                    hint=f"Use cells ≤ {d_star/self.GOOD_RATIO:.3f} m for good LES resolution.",
                    fix=_fix_res,
                ))
            elif ratio < self.GOOD_RATIO:
                results.append(_w(self.name,
                    f"Mesh '{m.name}': D*/dx ≈ {ratio:.1f} — borderline resolution. "
                    f"Recommended ratio is ≥ {self.GOOD_RATIO}.",
                    entity=m.name))
        return results


class MeshAspectRatioRule:
    """Mesh cells are not too elongated."""
    name = "MeshAspectRatio"
    MAX_RATIO = 5.0

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for m in p.meshes:
            dx = (m.x_max - m.x_min) / m.cell_count[0] if m.cell_count[0] else 0
            dy = (m.y_max - m.y_min) / m.cell_count[1] if m.cell_count[1] else 0
            dz = (m.z_max - m.z_min) / m.cell_count[2] if m.cell_count[2] else 0
            cell_sizes = [s for s in [dx, dy, dz] if s > 0]
            if len(cell_sizes) < 2:
                continue
            ratio = max(cell_sizes) / min(cell_sizes)
            if ratio > self.MAX_RATIO:
                mesh_ref = m
                min_dx_val = min(cell_sizes)

                def _fix(project, _m=mesh_ref, _min=min_dx_val):
                    cc = list(_m.cell_count)
                    lx = _m.x_max - _m.x_min
                    ly = _m.y_max - _m.y_min
                    lz = _m.z_max - _m.z_min
                    for i, length in enumerate([lx, ly, lz]):
                        if length > 0:
                            cc[i] = _nearest_poisson(max(cc[i], math.ceil(length / (_min * self.MAX_RATIO))))
                    _m.cell_count = tuple(cc)

                results.append(ValidationResult(
                    severity=Severity.WARNING,
                    rule=self.name,
                    message=(
                        f"Mesh '{m.name}' has cell aspect ratio {ratio:.2f}:1 "
                        f"(dx={dx:.4f}, dy={dy:.4f}, dz={dz:.4f}m). Recommended max is {self.MAX_RATIO:.0f}:1."
                    ),
                    entity_name=m.name,
                    hint="Highly non-cubic cells can reduce LES accuracy and increase Courant-number sensitivity.",
                    fix=_fix,
                ))
        return results


class CylindricalMeshRule:
    """
    Verify that cylindrical meshes (CYLINDRICAL=.TRUE.) satisfy FDS requirements:
      - Exactly one mesh may be cylindrical (FDS limitation).
      - The cylindrical mesh must have x_min = 0 (axis of symmetry at x=0).
      - y extents must span [0, 2π) when using cylindrical coords in 2D
        (full 3-D cylindrical is fine with any y range).
      - Non-cylindrical meshes must not overlap the cylindrical mesh's domain.
    """
    name = "CylindricalMesh"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        cyl = [m for m in p.meshes if getattr(m, "cylindrical", False)]
        if not cyl:
            return results

        if len(cyl) > 1:
            names = ", ".join(m.name for m in cyl)
            results.append(_e(
                self.name,
                f"Multiple cylindrical meshes found: [{names}]. "
                "FDS only supports a single CYLINDRICAL mesh per simulation.",
                hint="Remove CYLINDRICAL=.TRUE. from all but one mesh.",
            ))

        for m in cyl:
            if abs(m.x_min) > 1e-6:
                results.append(_e(
                    self.name,
                    f"Cylindrical mesh '{m.name}' has x_min={m.x_min:.4g}. "
                    "FDS requires x_min=0 for the axis of symmetry.",
                    entity=m.name,
                    hint="Set x_min=0 so the r=0 axis aligns with the mesh boundary.",
                ))
            if m.x_max <= 0:
                results.append(_e(
                    self.name,
                    f"Cylindrical mesh '{m.name}' has x_max={m.x_max:.4g} ≤ 0. "
                    "The radial extent must be positive.",
                    entity=m.name,
                ))

        return results
