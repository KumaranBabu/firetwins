"""Measurements between points and boxes (UX-14). Pure geometry, SI metres."""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

Point = Sequence[float]


def _pt(p: Point) -> List[float]:
    if len(p) != 3:
        raise ValueError("a point needs three coordinates")
    return [float(v) for v in p]


def distance(p: Point, q: Point) -> Dict[str, float]:
    """Straight-line distance with its components; ``horizontal`` ignores z."""
    a, b = _pt(p), _pt(q)
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    return {"distance": math.sqrt(dx * dx + dy * dy + dz * dz), "dx": dx, "dy": dy, "dz": dz,
            "horizontal": math.hypot(dx, dy)}


def angle(a: Point, vertex: Point, c: Point) -> float:
    """Angle in degrees at *vertex* between the rays to *a* and *c*."""
    va = [x - y for x, y in zip(_pt(a), _pt(vertex))]
    vc = [x - y for x, y in zip(_pt(c), _pt(vertex))]
    na, nc = math.sqrt(sum(x * x for x in va)), math.sqrt(sum(x * x for x in vc))
    if na == 0 or nc == 0:
        raise ValueError("the vertex coincides with one of the points")
    cos = max(-1.0, min(1.0, sum(x * y for x, y in zip(va, vc)) / (na * nc)))
    return math.degrees(math.acos(cos))


def path_length(points: Sequence[Point]) -> float:
    if len(points) < 2:
        raise ValueError("a path needs at least two points")
    return sum(distance(points[i], points[i + 1])["distance"] for i in range(len(points) - 1))


def polygon_area(points: Sequence[Point]) -> float:
    """Area of a planar polygon in 3D (the polygon closes itself)."""
    if len(points) < 3:
        raise ValueError("a polygon needs at least three points")
    pts = [_pt(p) for p in points]
    sx = sy = sz = 0.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sx += a[1] * b[2] - a[2] * b[1]
        sy += a[2] * b[0] - a[0] * b[2]
        sz += a[0] * b[1] - a[1] * b[0]
    return 0.5 * math.sqrt(sx * sx + sy * sy + sz * sz)


def box_gap(b1: Sequence[float], b2: Sequence[float]) -> Dict[str, float]:
    """Smallest distance between two boxes [x0,x1,y0,y1,z0,z1] (0 when they touch or overlap) and between centres."""
    gaps = [max(b1[2 * i] - b2[2 * i + 1], b2[2 * i] - b1[2 * i + 1], 0.0) for i in range(3)]
    c1 = [(b1[2 * i] + b1[2 * i + 1]) / 2 for i in range(3)]
    c2 = [(b2[2 * i] + b2[2 * i + 1]) / 2 for i in range(3)]
    return {"gap": math.sqrt(sum(g * g for g in gaps)), "gap_x": gaps[0], "gap_y": gaps[1], "gap_z": gaps[2],
            "center_distance": distance(c1, c2)["distance"]}


def box_size(b: Sequence[float]) -> Dict[str, float]:
    dx, dy, dz = b[1] - b[0], b[3] - b[2], b[5] - b[4]
    return {"dx": dx, "dy": dy, "dz": dz, "volume": dx * dy * dz,
            "diagonal": math.sqrt(dx * dx + dy * dy + dz * dz)}
