"""Snapping for the viewport drawing tools (plan step F2), free of Qt and VTK.

A picked point is pulled onto the nearest solution-mesh cell boundary, then onto the grid, then onto an object's corner,
whichever the snap settings allow and lie within ``tolerance``. ``ortho`` and ``polar_step_deg`` then limit the
direction from the anchor (the first point of a drawing).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float, float]


def _nearest(value: float, candidates: Iterable[float], tolerance: float) -> Optional[float]:
    best = min(candidates, key=lambda c: abs(c - value), default=None)
    return best if best is not None and abs(best - value) <= tolerance else None


def mesh_lines(meshes: Sequence[Any], axis: int, around: float, span: float) -> List[float]:
    """Cell boundaries along *axis* of every mesh, limited to those within *span* of *around* (a mesh with a million
    cells must not make this slow)."""
    out: List[float] = []
    names = ("x", "y", "z")[axis]
    for m in meshes:
        lo, hi = getattr(m, f"{names}_min"), getattr(m, f"{names}_max")
        n = max(1, int(m.cell_count[axis]))
        h = (hi - lo) / n
        if h <= 0 or around < lo - span or around > hi + span:
            continue
        k0 = max(0, int(math.floor((around - span - lo) / h)))
        k1 = min(n, int(math.ceil((around + span - lo) / h)))
        out.extend(lo + k * h for k in range(k0, k1 + 1))
    return out


def corner_points(entities: Iterable[Any]) -> List[Point]:
    pts: List[Point] = []
    for e in entities:
        b = e.bbox() if hasattr(e, "bbox") else None
        if b is None:
            continue
        for x in (b[0], b[1]):
            for y in (b[2], b[3]):
                for z in (b[4], b[5]):
                    pts.append((x, y, z))
    return pts


def snap_point(point: Sequence[float], settings: Any, meshes: Sequence[Any] = (), objects: Sequence[Any] = (),
               anchor: Optional[Sequence[float]] = None) -> Point:
    """Return *point* moved onto what the snap settings allow. Nothing is changed when snapping is off."""
    p = [float(point[0]), float(point[1]), float(point[2])]
    if not getattr(settings, "enabled", True):
        return tuple(p)                                                    # type: ignore[return-value]
    tol = float(getattr(settings, "tolerance", 0.25))

    if getattr(settings, "snap_to_vertex", False):
        corners = corner_points(objects)
        near = min(corners, key=lambda c: math.dist(c, p), default=None)
        if near is not None and math.dist(near, p) <= tol:
            return near

    if anchor is not None:
        p = _constrain(p, anchor, settings)

    for axis in range(3):
        snapped = None
        if getattr(settings, "snap_to_mesh", False) and meshes:
            snapped = _nearest(p[axis], mesh_lines(meshes, axis, p[axis], tol), tol)
        if snapped is None and getattr(settings, "snap_to_grid", False):
            g = float(getattr(settings, "grid_size", 0.1))
            if g > 0:
                snapped = round(p[axis] / g) * g
        if snapped is not None:
            p[axis] = snapped
    return (p[0], p[1], p[2])


def _constrain(p: List[float], anchor: Sequence[float], settings: Any) -> List[float]:
    dx, dy = p[0] - anchor[0], p[1] - anchor[1]
    step = getattr(settings, "polar_step_deg", None)
    if getattr(settings, "ortho", False):
        if abs(dx) >= abs(dy):
            p[1] = anchor[1]
        else:
            p[0] = anchor[0]
    elif step:
        r = math.hypot(dx, dy)
        ang = round(math.degrees(math.atan2(dy, dx)) / step) * step
        p[0] = anchor[0] + r * math.cos(math.radians(ang))
        p[1] = anchor[1] + r * math.sin(math.radians(ang))
    return p
