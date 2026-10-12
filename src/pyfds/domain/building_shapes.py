"""Building-element generators (B2): walls, slabs, rooms, curved walls, stairs, roofs, trusses.

Pure geometry, no project access: every function returns a list of axis-aligned boxes
``(x_min, x_max, y_min, y_max, z_min, z_max)`` because ``&OBST`` is an axis-aligned box.
Anything not aligned to the axes (diagonal walls, arcs, sloped roofs, truss members) is
stair-stepped onto a grid of cell size ``res`` -- the same thing FDS itself would do.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

Box = Tuple[float, float, float, float, float, float]
Pt = Tuple[float, float]

_EPS = 1e-9


# -- 2-D rasterising -------------------------------------------------------------------------
def _inside(poly: Sequence[Pt], x: float, y: float) -> bool:
    n, hit = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def rasterize(poly: Sequence[Pt], res: float) -> List[Tuple[float, float, float, float]]:
    """Cover a 2-D polygon with rectangles ``(a0, a1, b0, b1)`` on a grid of pitch *res*."""
    return rasterize_union([poly], res)


def rasterize_union(polys: Sequence[Sequence[Pt]], res: float) -> List[Tuple[float, float, float, float]]:
    """Cover the union of several polygons on a grid of pitch *res* without overlaps.

    A grid cell is kept when its centre is inside any polygon; runs along the first axis are
    merged, so a rectangle comes back as one rectangle."""
    if res <= 0:
        raise ValueError("resolution must be positive")
    cells = set()
    for poly in polys:
        if len(poly) < 3:
            raise ValueError("a polygon needs at least 3 points")
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        i0, i1 = math.floor(min(xs) / res + _EPS), math.ceil(max(xs) / res - _EPS)
        j0, j1 = math.floor(min(ys) / res + _EPS), math.ceil(max(ys) / res - _EPS)
        for j in range(j0, j1):
            for i in range(i0, i1):
                if _inside(poly, (i + 0.5) * res, (j + 0.5) * res):
                    cells.add((i, j))
    out: List[Tuple[float, float, float, float]] = []
    rows: dict = {}
    for i, j in cells:
        rows.setdefault(j, []).append(i)
    for j in sorted(rows):
        run = prev = None
        for i in sorted(rows[j]) + [None]:
            if run is not None and (i is None or i != prev + 1):
                out.append((run * res, (prev + 1) * res, j * res, (j + 1) * res))
                run = None
            if i is not None and run is None:
                run = i
            prev = i
    return _merge_rows(out)


def _merge_rows(rects):
    """Merge rows with identical x-extent that touch in y."""
    rects = sorted(rects, key=lambda r: (r[0], r[1], r[2]))
    merged: list = []
    for r in rects:
        if merged and abs(merged[-1][0] - r[0]) < _EPS and abs(merged[-1][1] - r[1]) < _EPS \
                and abs(merged[-1][3] - r[2]) < _EPS:
            merged[-1] = (r[0], r[1], merged[-1][2], r[3])
        else:
            merged.append(r)
    return merged


def _boxes(rects, z0: float, z1: float) -> List[Box]:
    return [(a0, a1, b0, b1, z0, z1) for a0, a1, b0, b1 in rects]


# -- walls -----------------------------------------------------------------------------------
_ALIGN = {"L": (0.0, 1.0), "C": (-0.5, 0.5), "R": (-1.0, 0.0)}


def _check_align(align: str) -> Tuple[float, float]:
    try:
        return _ALIGN[align.upper()]
    except KeyError:
        raise ValueError("alignment must be L, C or R (left of / centred on / right of the path)") from None


def wall(path: Sequence[Pt], thickness: float, z0: float, height: float, align: str = "C",
         res: float = 0.1, closed: bool = False) -> List[Box]:
    """A wall of constant *thickness* along a polyline.

    *align* says which side of the walking direction the thickness is on. Straight (axis
    parallel) runs are exact boxes and right-angle corners are filled; diagonal runs are
    stair-stepped at *res*."""
    if thickness <= 0 or height <= 0:
        raise ValueError("thickness and height must be positive")
    pts = [(float(x), float(y)) for x, y in path]
    if closed and pts[0] != pts[-1]:
        pts.append(pts[0])
    if len(pts) < 2:
        raise ValueError("a wall needs at least two points")
    lo_f, hi_f = _check_align(align)
    lo, hi = lo_f * thickness, hi_f * thickness
    segs = list(zip(pts[:-1], pts[1:]))
    segs = [s for s in segs if math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]) > _EPS]
    if not segs:
        raise ValueError("wall path has zero length")
    boxes: List[Box] = []
    for k, ((ax, ay), (bx, by)) in enumerate(segs):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux                                   # left normal
        # extend the ends at joints so right-angle corners are filled
        e0 = _joint_extension(segs[k - 1] if (k > 0 or closed) else None, (ux, uy), lo, hi, start=True)
        e1 = _joint_extension(segs[(k + 1) % len(segs)] if (k < len(segs) - 1 or closed) else None,
                              (ux, uy), lo, hi, start=False)
        p0 = (ax - ux * e0, ay - uy * e0)
        p1 = (bx + ux * e1, by + uy * e1)
        quad = [(p0[0] + nx * lo, p0[1] + ny * lo), (p1[0] + nx * lo, p1[1] + ny * lo),
                (p1[0] + nx * hi, p1[1] + ny * hi), (p0[0] + nx * hi, p0[1] + ny * hi)]
        if abs(ux) < 1e-9 or abs(uy) < 1e-9:               # axis parallel: exact box
            xs, ys = [q[0] for q in quad], [q[1] for q in quad]
            boxes.append((min(xs), max(xs), min(ys), max(ys), z0, z0 + height))
        else:
            boxes.extend(_boxes(rasterize(quad, res), z0, z0 + height))
    return boxes


def _joint_extension(other, u, lo, hi, start: bool) -> float:
    """How far to extend a segment end so it fills the corner with the neighbouring segment."""
    if other is None:
        return 0.0
    (ox, oy), (px, py) = other
    olen = math.hypot(px - ox, py - oy)
    vx, vy = (px - ox) / olen, (py - oy) / olen
    if abs(u[0] * vx + u[1] * vy) > 1e-9:                  # only right angles
        return 0.0
    # the neighbour's across-range, projected on our direction
    nx, ny = -vy, vx
    proj = [lo * (nx * u[0] + ny * u[1]), hi * (nx * u[0] + ny * u[1])]
    sign = -1.0 if start else 1.0
    return max(0.0, *(sign * p for p in proj))


def curved_wall(center: Pt, radius: float, start_deg: float, end_deg: float, thickness: float,
                z0: float, height: float, align: str = "C", res: float = 0.1,
                segments: int = None) -> List[Box]:
    """A wall along a circular arc (angles in degrees, counter-clockwise from +X)."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    sweep = end_deg - start_deg
    if abs(sweep) < _EPS:
        raise ValueError("arc has zero length")
    n = segments or max(8, int(math.ceil(abs(sweep) / 360.0 * 2 * math.pi * radius / res)))
    pts = [(center[0] + radius * math.cos(math.radians(start_deg + sweep * i / n)),
            center[1] + radius * math.sin(math.radians(start_deg + sweep * i / n))) for i in range(n + 1)]
    closed = abs(abs(sweep) - 360.0) < 1e-6
    if closed:
        pts = pts[:-1]
    # per-segment rasterising (no right-angle corner fill: arcs have no right angles)
    lo_f, hi_f = _check_align(align)
    lo, hi = lo_f * thickness, hi_f * thickness
    quads = []
    ring = pts + [pts[0]] if closed else pts
    for (ax, ay), (bx, by) in zip(ring[:-1], ring[1:]):
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        nx, ny = -uy, ux
        # a little overlap along the run keeps the stair-stepped joints closed
        a = (ax - ux * thickness * 0.1, ay - uy * thickness * 0.1)
        b = (bx + ux * thickness * 0.1, by + uy * thickness * 0.1)
        quad = [(a[0] + nx * lo, a[1] + ny * lo), (b[0] + nx * lo, b[1] + ny * lo),
                (b[0] + nx * hi, b[1] + ny * hi), (a[0] + nx * hi, a[1] + ny * hi)]
        quads.append(quad)
    return _boxes(rasterize_union(quads, res), z0, z0 + height)


# -- slabs, rooms ----------------------------------------------------------------------------
def slab(polygon: Sequence[Pt], z_top: float, thickness: float, res: float = 0.1) -> List[Box]:
    """A floor/ceiling slab: *polygon* extruded down from *z_top* by *thickness*."""
    if thickness <= 0:
        raise ValueError("thickness must be positive")
    pts = [(float(x), float(y)) for x, y in polygon]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if len(pts) == 4 and _is_axis_rect(pts):
        return [(min(xs), max(xs), min(ys), max(ys), z_top - thickness, z_top)]
    return _boxes(rasterize(pts, res), z_top - thickness, z_top)


def _is_axis_rect(pts) -> bool:
    xs, ys = sorted({round(p[0], 9) for p in pts}), sorted({round(p[1], 9) for p in pts})
    return len(xs) == 2 and len(ys) == 2


_SIDES = {"S": 0, "E": 1, "N": 2, "W": 3}


def room(x0: float, x1: float, y0: float, y1: float, z0: float, height: float,
         wall_thickness: float, position: str = "inside", floor_thickness: float = 0.0,
         ceiling_thickness: float = 0.0) -> Tuple[List[Tuple[str, Box]], Box]:
    """Four walls (plus optional floor and ceiling) round a rectangle.

    *position*: ``inside`` keeps the walls inside the rectangle, ``outside`` puts them round it,
    ``centre`` centres them on its edges. Returns ``([(part, box), ...], interior_box)`` where
    *part* is S/E/N/W/floor/ceiling and *interior_box* is the clear space."""
    if x1 <= x0 or y1 <= y0 or height <= 0 or wall_thickness <= 0:
        raise ValueError("room needs x1>x0, y1>y0, positive height and wall thickness")
    t = wall_thickness
    off = {"inside": (0.0, t), "centre": (-t / 2, t / 2), "center": (-t / 2, t / 2),
           "outside": (-t, 0.0)}
    try:
        lo, hi = off[position.lower()]
    except KeyError:
        raise ValueError("position must be inside, centre or outside") from None
    # outer / inner rectangle of the wall ring
    ox0, ox1, oy0, oy1 = x0 + lo, x1 - lo, y0 + lo, y1 - lo
    ix0, ix1, iy0, iy1 = x0 + hi, x1 - hi, y0 + hi, y1 - hi
    if ix1 - ix0 <= 0 or iy1 - iy0 <= 0:
        raise ValueError("walls are thicker than the room")
    zt = z0 + height
    parts = [("S", (ox0, ox1, oy0, iy0, z0, zt)), ("N", (ox0, ox1, iy1, oy1, z0, zt)),
             ("W", (ox0, ix0, iy0, iy1, z0, zt)), ("E", (ix1, ox1, iy0, iy1, z0, zt))]
    if floor_thickness > 0:
        parts.append(("floor", (ox0, ox1, oy0, oy1, z0 - floor_thickness, z0)))
    if ceiling_thickness > 0:
        parts.append(("ceiling", (ox0, ox1, oy0, oy1, zt, zt + ceiling_thickness)))
    return parts, (ix0, ix1, iy0, iy1, z0, zt)


def opening_box(parts, side: str, centre: float, width: float, height: float, sill: float,
                z0: float) -> Box:
    """A hole box that cuts clean through wall *side* (S/E/N/W) at *centre* along it."""
    s = side.upper()
    if s not in _SIDES:
        raise ValueError("side must be S, E, N or W")
    wall_box = dict(parts)[s]
    za, zb = z0 + sill, z0 + sill + height
    a, b = centre - width / 2, centre + width / 2
    if s in "SN":
        return (a, b, wall_box[2], wall_box[3], za, zb)
    return (wall_box[0], wall_box[1], a, b, za, zb)


# -- stairs ----------------------------------------------------------------------------------
_DIRS = {"+X": (1, 0), "-X": (-1, 0), "+Y": (0, 1), "-Y": (0, -1)}


def stairs(x: float, y: float, z0: float, direction: str, width: float, steps: int,
           riser: float, tread: float, landing: float = 0.0) -> List[Box]:
    """A straight flight of solid steps.

    (x, y) is the foot of the lowest step's centre line edge; the flight climbs towards
    *direction* (+X, -X, +Y or -Y). Step *i* (1-based) is ``i*riser`` high. An optional
    *landing* adds a flat top of that length at the full height."""
    if steps < 1 or riser <= 0 or tread <= 0 or width <= 0:
        raise ValueError("steps >= 1 and positive riser, tread and width are required")
    try:
        dx, dy = _DIRS[direction.upper().replace(" ", "")]
    except KeyError:
        raise ValueError("direction must be +X, -X, +Y or -Y") from None
    boxes: List[Box] = []
    runs = [(i * tread, (i + 1) * tread, (i + 1) * riser) for i in range(steps)]
    if landing > 0:
        runs.append((steps * tread, steps * tread + landing, steps * riser))
    for a, b, h in runs:
        if dx:                                              # runs along x
            xa, xb = sorted((x + dx * a, x + dx * b))
            boxes.append((xa, xb, y - width / 2, y + width / 2, z0, z0 + h))
        else:
            ya, yb = sorted((y + dy * a, y + dy * b))
            boxes.append((x - width / 2, x + width / 2, ya, yb, z0, z0 + h))
    return boxes


# -- roofs -----------------------------------------------------------------------------------
def roof(x0: float, x1: float, y0: float, y1: float, z_eave: float, pitch_deg: float,
         thickness: float, kind: str = "gable", ridge_axis: str = "X", overhang: float = 0.0,
         res: float = 0.1) -> List[Box]:
    """A pitched roof as stepped strips running along the ridge.

    *kind* ``gable`` (two slopes meeting at a ridge) or ``shed`` (one slope rising towards +Y,
    or +X when the ridge axis is Y). *ridge_axis* is the direction the ridge runs along.
    Each strip of width *res* is a box of the roof's thickness at that strip's height."""
    if not 0 < pitch_deg < 85:
        raise ValueError("pitch must be between 0 and 85 degrees")
    if thickness <= 0:
        raise ValueError("thickness must be positive")
    if kind not in ("gable", "shed"):
        raise ValueError("kind must be gable or shed")
    ax = ridge_axis.upper()
    if ax not in ("X", "Y"):
        raise ValueError("ridge_axis must be X or Y")
    x0, x1, y0, y1 = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang
    a0, a1, b0, b1 = (y0, y1, x0, x1) if ax == "X" else (x0, x1, y0, y1)   # a = across, b = along
    t = math.tan(math.radians(pitch_deg))
    n = max(1, int(math.ceil((a1 - a0) / res)))
    mid = (a0 + a1) / 2
    boxes: List[Box] = []
    for i in range(n):
        s0, s1 = a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n
        c = (s0 + s1) / 2
        rise = (mid - abs(c - mid)) if kind == "gable" else (c - a0)
        zb = z_eave + rise * t
        if ax == "X":
            boxes.append((b0, b1, s0, s1, zb, zb + thickness))
        else:
            boxes.append((s0, s1, b0, b1, zb, zb + thickness))
    return _merge_equal_strips(boxes, ax)


def _merge_equal_strips(boxes: List[Box], ridge_axis: str) -> List[Box]:
    k = (2, 3) if ridge_axis == "X" else (0, 1)             # across-axis index pair
    out: List[Box] = []
    for b in boxes:
        if out and abs(out[-1][4] - b[4]) < _EPS and abs(out[-1][k[1]] - b[k[0]]) < _EPS:
            p = list(out[-1])
            p[k[1]] = b[k[1]]
            out[-1] = tuple(p)
        else:
            out.append(b)
    return out


# -- trusses ---------------------------------------------------------------------------------
def truss(x: float, y: float, z0: float, span: float, rise: float, panels: int, member: float,
          depth: float, along: str = "X", res: float = 0.05) -> List[Box]:
    """A planar Warren truss: flat bottom chord, pitched (peaked) top chord, zig-zag web.

    The truss lies in the vertical plane through (x, y) running along *along* (X or Y); its
    *span* is measured from (x, y); *rise* is the height of the apex above the bottom chord's
    top; *member* is the chord/web thickness in the plane, *depth* its thickness across it."""
    if span <= 0 or rise <= 0 or panels < 2 or member <= 0 or depth <= 0:
        raise ValueError("span, rise, member and depth must be positive and panels >= 2")
    ax = along.upper()
    if ax not in ("X", "Y"):
        raise ValueError("along must be X or Y")
    half = span / 2

    def top(u):                                             # centre line of the top chord
        return member + rise * (1 - abs(u - half) / half)

    polys = [[(0, 0), (span, 0), (span, member), (0, member)]]          # bottom chord
    n = panels
    us = [span * i / n for i in range(n + 1)]
    for a, b in zip(us[:-1], us[1:]):                       # top chord, panel by panel
        polys.append([(a, top(a) - member), (b, top(b) - member), (b, top(b)), (a, top(a))])
    for i, (a, b) in enumerate(zip(us[:-1], us[1:])):       # web: alternate diagonals
        lo_u, hi_u = (a, b) if i % 2 == 0 else (b, a)
        p, q = (lo_u, member), (hi_u, top(hi_u) - member)
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L * member / 2, dx / L * member / 2
        polys.append([(p[0] + nx, p[1] + ny), (q[0] + nx, q[1] + ny), (q[0] - nx, q[1] - ny),
                      (p[0] - nx, p[1] - ny)])
    boxes: List[Box] = []
    for u0, u1, v0, v1 in rasterize_union(polys, res):
        if ax == "X":
            boxes.append((x + u0, x + u1, y - depth / 2, y + depth / 2, z0 + v0, z0 + v1))
        else:
            boxes.append((x - depth / 2, x + depth / 2, y + u0, y + u1, z0 + v0, z0 + v1))
    return boxes
