"""Snapping engine (UX-04): where does a cursor point land?

Pure geometry over a project's boxes and meshes, so the 3D view, the 2D view, scripts and agents all
snap the same way. Priority (first class with a hit inside the tolerance wins, nearest hit within it):

    vertex > edge > face > mesh_point > mesh_line > mesh_plane > grid

* ``vertex`` / ``edge`` / ``face`` - corners, edges and surfaces of obstructions, holes, vents,
  init regions and meshes, plus the vertices of ``&GEOM`` surfaces.
* ``mesh_point`` / ``mesh_line`` / ``mesh_plane`` - where 3, 2 or 1 coordinates sit on solution-mesh
  grid lines (cell boundaries); this is what makes drawn objects line up with the FDS grid.
* ``grid`` - the sketch grid, multiples of ``grid_size``.

Constraints are applied first, relative to an *anchor* (the previous point of the shape being drawn):
``ortho`` keeps only the dominant axis, ``polar_step_deg`` rounds the XY angle to a multiple of the
step, ``lock_direction`` (Shift held) keeps motion along a fixed direction. A constrained point may
still snap to the grid along its line. ``enabled=False`` (ALT held) returns the point untouched.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]

PRIORITY = ("vertex", "edge", "face", "mesh_point", "mesh_line", "mesh_plane", "grid")


@dataclass(frozen=True)
class SnapResult:
    point: Vec
    kind: str                      # one of PRIORITY, "ortho", "polar", "locked", or "none"
    entity: Optional[str] = None   # name of the object snapped to
    distance: float = 0.0          # how far the point moved


def _box(e) -> Optional[Tuple[float, ...]]:
    try:
        return (e.x_min, e.x_max, e.y_min, e.y_max, e.z_min, e.z_max)
    except AttributeError:
        return None


def _d(a: Sequence[float], b: Sequence[float]) -> float:
    return math.dist(a, b)


def _corners(b) -> List[Vec]:
    return [(x, y, z) for x in b[0:2] for y in b[2:4] for z in b[4:6]]


def _edges(b):
    c = {(i, j, k): (b[i], b[2 + j], b[4 + k]) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    for j in (0, 1):
        for k in (0, 1):
            yield c[(0, j, k)], c[(1, j, k)]
    for i in (0, 1):
        for k in (0, 1):
            yield c[(i, 0, k)], c[(i, 1, k)]
    for i in (0, 1):
        for j in (0, 1):
            yield c[(i, j, 0)], c[(i, j, 1)]


def _on_segment(p: Vec, a: Vec, b: Vec) -> Vec:
    ab = [b[i] - a[i] for i in range(3)]
    n = sum(v * v for v in ab)
    if n == 0:
        return a
    t = max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n))
    return (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)


def _on_box_surface(p: Vec, b) -> Vec:
    q = [min(max(p[i], b[2 * i]), b[2 * i + 1]) for i in range(3)]
    if all(b[2 * i] < p[i] < b[2 * i + 1] for i in range(3)):       # inside: push to the nearest face
        i = min(range(3), key=lambda a: min(p[a] - b[2 * a], b[2 * a + 1] - p[a]))
        q[i] = b[2 * i] if p[i] - b[2 * i] < b[2 * i + 1] - p[i] else b[2 * i + 1]
    return (q[0], q[1], q[2])


def _grid_lines(lo: float, hi: float, n: int) -> List[float]:
    return [lo + (hi - lo) * i / n for i in range(n + 1)]


def _mesh_hits(p: Vec, mesh, tol: float):
    """Nearest grid-line coordinate per axis (within tol), or None."""
    hits = []
    for a in range(3):
        lo, hi, n = getattr(mesh, "xyz"[a] + "_min"), getattr(mesh, "xyz"[a] + "_max"), mesh.cell_count[a]
        if not (lo - tol <= p[a] <= hi + tol) or n <= 0:
            hits.append(None)
            continue
        step = (hi - lo) / n
        i = round((p[a] - lo) / step)
        v = lo + min(max(i, 0), n) * step
        hits.append(v if abs(v - p[a]) <= tol else None)
    return hits


def constrain(point: Vec, anchor: Vec, *, ortho: bool = False, polar_step_deg: Optional[float] = None,
              lock_direction: Optional[Vec] = None, plane: Optional[Tuple[str, float]] = None):
    """Apply the ortho / polar / lock constraint; returns ``(point, kind or None)``."""
    d = [point[i] - anchor[i] for i in range(3)]
    if plane is not None:
        d["xyz".index(plane[0].lower())] = 0.0
    if lock_direction is not None:
        n = math.sqrt(sum(v * v for v in lock_direction))
        if n == 0:
            raise ValueError("lock_direction must not be the zero vector")
        u = [v / n for v in lock_direction]
        t = sum(d[i] * u[i] for i in range(3))
        return (anchor[0] + u[0] * t, anchor[1] + u[1] * t, anchor[2] + u[2] * t), "locked"
    if ortho:
        axes = [i for i in range(3) if not (plane and "xyz"[i] == plane[0].lower())]
        k = max(axes, key=lambda i: abs(d[i]))
        out = list(anchor)
        out[k] = anchor[k] + d[k]
        return (out[0], out[1], out[2]), "ortho"
    if polar_step_deg:
        r = math.hypot(d[0], d[1])
        if r > 0:
            ang = math.degrees(math.atan2(d[1], d[0]))
            ang = round(ang / polar_step_deg) * polar_step_deg
            return (anchor[0] + r * math.cos(math.radians(ang)), anchor[1] + r * math.sin(math.radians(ang)),
                    anchor[2] + d[2]), "polar"
    return point, None


def snap(point: Sequence[float], project: Any, *, tolerance: float = 0.25, grid_size: Optional[float] = 0.1,
         kinds: Iterable[str] = PRIORITY, enabled: bool = True, anchor: Optional[Sequence[float]] = None,
         ortho: bool = False, polar_step_deg: Optional[float] = None,
         lock_direction: Optional[Sequence[float]] = None,
         plane: Optional[Tuple[str, float]] = None) -> SnapResult:
    """Snap *point* (x, y, z) as described in the module docstring."""
    if len(point) != 3:
        raise ValueError("point needs three coordinates")
    if tolerance < 0 or (grid_size is not None and grid_size < 0):
        raise ValueError("tolerance and grid_size must not be negative")
    kinds = set(kinds)
    unknown = kinds - set(PRIORITY)
    if unknown:
        raise ValueError(f"unknown snap kinds: {sorted(unknown)}")
    p: Vec = (float(point[0]), float(point[1]), float(point[2]))
    if not enabled:
        return SnapResult(p, "none")
    if plane is not None:
        i = "xyz".index(plane[0].lower())
        p = tuple(plane[1] if k == i else p[k] for k in range(3))     # type: ignore[assignment]
    start = p

    constrained = None
    if anchor is not None and (ortho or polar_step_deg or lock_direction is not None):
        a = (float(anchor[0]), float(anchor[1]), float(anchor[2]))
        p, constrained = constrain(p, a, ortho=ortho, polar_step_deg=polar_step_deg,
                                   lock_direction=tuple(lock_direction) if lock_direction is not None else None,
                                   plane=plane)
        if constrained and grid_size and "grid" in kinds:      # round the length to the grid, keep the line
            length = _d(p, a)
            if length > 0:
                k = round(length / grid_size) * grid_size
                p = tuple(a[i] + (p[i] - a[i]) * k / length for i in range(3))     # type: ignore[assignment]
        return SnapResult(p, constrained, None, _d(p, start))

    best = {}

    def offer(kind, q, name=None, limit=tolerance):
        dist = _d(p, q)
        if dist <= limit and (kind not in best or dist < best[kind][0]):
            best[kind] = (dist, q, name)

    for coll in ("obstructions", "holes", "vents", "inits", "meshes"):
        for e in getattr(project, coll, []):
            b = _box(e)
            if b is None:
                continue
            nm = getattr(e, "name", None)
            if "vertex" in kinds:
                for c in _corners(b):
                    offer("vertex", c, nm)
            if "edge" in kinds:
                for s, t in _edges(b):
                    offer("edge", _on_segment(p, s, t), nm)
            if "face" in kinds:
                offer("face", _on_box_surface(p, b), nm)
    if "vertex" in kinds:
        for g in getattr(project, "geoms", []):
            for v in g.verts or []:
                offer("vertex", (float(v[0]), float(v[1]), float(v[2])), g.name)
    if kinds & {"mesh_point", "mesh_line", "mesh_plane"}:
        for m in getattr(project, "meshes", []):
            hits = _mesh_hits(p, m, tolerance)
            n = sum(h is not None for h in hits)
            if n == 0:
                continue
            q = tuple(h if h is not None else p[i] for i, h in enumerate(hits))
            kind = {3: "mesh_point", 2: "mesh_line", 1: "mesh_plane"}[n]
            if kind in kinds:
                offer(kind, q, m.name, tolerance * math.sqrt(n))
    if "grid" in kinds and grid_size:
        offer("grid", tuple(round(c / grid_size) * grid_size for c in p))

    for kind in PRIORITY:
        if kind in best:
            dist, q, name = best[kind]
            return SnapResult((q[0], q[1], q[2]), kind, name, _d(q, start))
    return SnapResult(p, "none")
