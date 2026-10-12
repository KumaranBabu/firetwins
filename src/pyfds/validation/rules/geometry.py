"""Entity-bounds rules (obstructions, vents, holes, devices, inits, slices)."""
from __future__ import annotations

from ._common import _e, _w, box_covered


from typing import Any, List
from ..engine import ValidationResult, Severity


class HoleContainmentRule:
    """Holes lie inside the obstructions they cut."""
    name = "HoleContainment"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for hole in p.holes:
            contained = any(
                hole.x_min >= o.x_min and hole.x_max <= o.x_max and
                hole.y_min >= o.y_min and hole.y_max <= o.y_max and
                hole.z_min >= o.z_min and hole.z_max <= o.z_max
                for o in p.obstructions
            )
            if not contained:
                results.append(_e(self.name,
                    f"HOLE '{hole.name}' is not fully contained within any obstruction.",
                    entity=hole.name,
                    hint="A &HOLE must lie entirely inside an existing &OBST."))
        return results


class ObstBoundsRule:
    """Obstructions lie inside a mesh."""
    name = "ObstBounds"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for o in p.obstructions:
            for axis, lo_attr, hi_attr in [
                ("X", "x_min", "x_max"),
                ("Y", "y_min", "y_max"),
                ("Z", "z_min", "z_max"),
            ]:
                lo = getattr(o, lo_attr)
                hi = getattr(o, hi_attr)
                if lo > hi:
                    obst_ref = o
                    lo_a, hi_a = lo_attr, hi_attr

                    def _fix(project, _o=obst_ref, _la=lo_a, _ha=hi_a):
                        old_lo = getattr(_o, _la)
                        old_hi = getattr(_o, _ha)
                        setattr(_o, _la, min(old_lo, old_hi))
                        setattr(_o, _ha, max(old_lo, old_hi))

                    results.append(ValidationResult(
                        severity=Severity.ERROR,
                        rule=self.name,
                        message=f"Obstruction '{o.name}' has inverted bounds on {axis} "
                                f"(min={lo} > max={hi}).",
                        entity_name=o.name,
                        hint=f"Swap {lo_attr} and {hi_attr} values.",
                        fix=_fix,
                    ))
        # Check all obstructions lie within at least one mesh
        if p.meshes:
            for o in p.obstructions:
                inside = box_covered((o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max), p.meshes)
                if not inside:
                    results.append(_w(self.name,
                        f"Obstruction '{o.name}' lies partially or entirely outside all meshes.",
                        entity=o.name,
                        hint="FDS will clip or ignore geometry outside the mesh domain."))
        return results


class VentCoplanarRule:
    """Vents lie on a solid face or mesh boundary."""
    name = "VentCoplanar"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for v in p.vents:
            dims = [
                abs(v.x_max - v.x_min),
                abs(v.y_max - v.y_min),
                abs(v.z_max - v.z_min),
            ]
            zero_count = sum(1 for d in dims if d < 1e-9)
            if zero_count != 1:
                vent_ref = v

                def _fix(project, _v=vent_ref, _dims=dims):
                    # Collapse the smallest non-zero dimension to zero (midpoint)
                    smallest_idx = min(
                        (i for i, d in enumerate(_dims) if d >= 1e-9),
                        key=lambda i: _dims[i],
                        default=None,
                    )
                    if smallest_idx is None:
                        return
                    if smallest_idx == 0:
                        mid = (_v.x_min + _v.x_max) / 2.0
                        _v.x_min = mid; _v.x_max = mid
                    elif smallest_idx == 1:
                        mid = (_v.y_min + _v.y_max) / 2.0
                        _v.y_min = mid; _v.y_max = mid
                    else:
                        mid = (_v.z_min + _v.z_max) / 2.0
                        _v.z_min = mid; _v.z_max = mid

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=(
                        f"VENT '{v.name}' XB is not planar (exactly one dimension must be zero). "
                        f"dims=({dims[0]:.4f},{dims[1]:.4f},{dims[2]:.4f})"
                    ),
                    entity_name=v.name,
                    hint="Set exactly one pair of min/max XB coordinates equal to collapse the vent to a face.",
                    fix=_fix,
                ))
        return results


class DeviceBoundsRule:
    """Devices lie inside a mesh."""
    name = "DeviceBounds"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        if not p.meshes:
            return results
        for dev in p.devices:
            inside = any(
                m.x_min <= dev.x <= m.x_max and
                m.y_min <= dev.y <= m.y_max and
                m.z_min <= dev.z <= m.z_max
                for m in p.meshes
            )
            if not inside:
                results.append(_w(
                    self.name,
                    f"DEVC '{dev.name}' at ({dev.x},{dev.y},{dev.z}) is outside all mesh domains.",
                    entity=dev.name,
                    hint="Move the device inside the mesh domain or extend the mesh to include it.",
                ))
        return results


class InitBoundsRule:
    """Initial-condition regions lie inside a mesh."""
    name = "InitBounds"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        if not p.meshes or not p.inits:
            return results
        for init in p.inits:
            inside = box_covered((init.x_min, init.x_max, init.y_min, init.y_max, init.z_min, init.z_max), p.meshes)
            if not inside:
                results.append(_w(
                    self.name,
                    f"INIT '{init.name}' XB region lies outside all mesh domains.",
                    entity=init.name,
                    hint="Ensure the INIT region is fully contained within at least one mesh.",
                ))
        return results


class SliceBoundsRule:
    """Slices lie inside a mesh."""
    name = "SliceBounds"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        if not p.meshes or not p.slices:
            return results
        for slc in p.slices:
            plane = slc.plane.upper()
            pos = slc.position
            if plane == "X":
                in_bounds = any(m.x_min <= pos <= m.x_max for m in p.meshes)
            elif plane == "Y":
                in_bounds = any(m.y_min <= pos <= m.y_max for m in p.meshes)
            elif plane == "Z":
                in_bounds = any(m.z_min <= pos <= m.z_max for m in p.meshes)
            else:
                continue
            if not in_bounds:
                results.append(_w(
                    self.name,
                    f"SLCF '{slc.name}' at {plane}={pos} is outside all mesh bounds on the {plane} axis.",
                    entity=slc.name,
                    hint="Move the slice plane inside the mesh domain or adjust the mesh extents.",
                ))
        return results
