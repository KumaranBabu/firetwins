"""Closed triangle meshes for building elements (plan step F1, Draw menu): a hollow pipe and a sloped ramp.

Pure geometry, no project state. Every face is oriented outward (checked against the surface's own geometry, not
assumed), so the result passes the closed-surface check and has a positive volume.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Vec = Tuple[float, float, float]
Tri = Tuple[int, int, int]


def _sub(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normal(verts: List[Vec], tri: Tri) -> Vec:
    a, b, c = (verts[i] for i in tri)
    return _cross(_sub(b, a), _sub(c, a))


def _facing(verts: List[Vec], tri: Tri, wanted: Vec) -> Tri:
    """*tri* wound so its normal points the way *wanted* does."""
    return tri if _dot(_normal(verts, tri), wanted) >= 0 else (tri[0], tri[2], tri[1])


def signed_volume(verts: Sequence[Vec], faces: Sequence[Tri]) -> float:
    """Volume enclosed by an outward-oriented closed surface (negative when the faces point inward)."""
    return sum(_dot(verts[a], _cross(verts[b], verts[c])) for a, b, c in faces) / 6.0


def _basis(axis: Vec) -> Tuple[Vec, Vec]:
    """Two unit vectors perpendicular to *axis* and to each other."""
    helper = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _cross(axis, helper)
    n = math.sqrt(_dot(e1, e1))
    e1 = (e1[0] / n, e1[1] / n, e1[2] / n)
    return e1, _cross(axis, e1)


def pipe_mesh(start: Sequence[float], end: Sequence[float], outer_radius: float, wall: float,
              segments: int = 24) -> Tuple[List[Vec], List[Tri]]:
    """A hollow tube from *start* to *end*: outer radius, wall thickness (a solid rod when *wall* >= the radius)."""
    length = math.dist(start, end)
    if length <= 1e-9:
        raise ValueError("the pipe needs a length: start and end are the same point")
    if outer_radius <= 0 or wall <= 0:
        raise ValueError("radius and wall thickness must be greater than 0")
    if segments < 6:
        raise ValueError("a pipe needs at least 6 segments")
    inner = outer_radius - wall
    hollow = inner > 1e-9
    u = tuple((e - s) / length for s, e in zip(start, end))
    e1, e2 = _basis(u)
    ring = [(math.cos(2 * math.pi * k / segments), math.sin(2 * math.pi * k / segments)) for k in range(segments)]

    def circle(centre: Sequence[float], r: float) -> List[Vec]:
        return [tuple(centre[i] + r * (c * e1[i] + s * e2[i]) for i in range(3)) for c, s in ring]

    n = segments
    verts: List[Vec] = circle(start, outer_radius) + circle(end, outer_radius)                    # 0..n-1, n..2n-1
    if hollow:
        verts += circle(start, inner) + circle(end, inner)                                        # 2n..3n-1, 3n..4n-1
    faces: List[Tri] = []

    def quad(a: int, b: int, c: int, d: int, wanted: Vec) -> None:
        faces.append(_facing(verts, (a, b, c), wanted))
        faces.append(_facing(verts, (a, c, d), wanted))

    for k in range(n):
        k2 = (k + 1) % n
        mid = tuple(sum(verts[i][j] for i in (k, k2)) / 2 - start[j] for j in range(3))
        radial = tuple(mid[j] - u[j] * _dot(mid, u) for j in range(3))
        quad(k, k2, n + k2, n + k, radial)                                                        # outer wall
        if hollow:
            quad(2 * n + k, 2 * n + k2, 3 * n + k2, 3 * n + k, tuple(-r for r in radial))         # inner wall
            quad(k, k2, 2 * n + k2, 2 * n + k, tuple(-x for x in u))                              # start annulus
            quad(n + k, n + k2, 3 * n + k2, 3 * n + k, u)                                         # end annulus
    if not hollow:                                                                                # solid rod: fan the caps
        verts.append(tuple(start))
        verts.append(tuple(end))
        for k in range(n):
            k2 = (k + 1) % n
            faces.append(_facing(verts, (k, k2, 2 * n), tuple(-x for x in u)))
            faces.append(_facing(verts, (n + k, n + k2, 2 * n + 1), u))
    return verts, faces


_DIRECTIONS = {"+X": (1, 0), "-X": (-1, 0), "+Y": (0, 1), "-Y": (0, -1)}


def ramp_mesh(origin: Sequence[float], direction: str, length: float, width: float,
              rise: float) -> Tuple[List[Vec], List[Tri]]:
    """A solid wedge: its low edge starts at *origin* and the surface climbs *rise* over *length* in *direction*
    (``+X`` ``-X`` ``+Y`` ``-Y``); *width* extends to the left of the climbing direction."""
    d = direction.strip().upper()
    if d not in _DIRECTIONS:
        raise ValueError("direction must be +X, -X, +Y or -Y")
    if min(length, width, rise) <= 0:
        raise ValueError("length, width and rise must all be greater than 0")
    fx, fy = _DIRECTIONS[d]                         # forward (climbing) direction
    lx, ly = -fy, fx                                # to the left of it
    x0, y0, z0 = origin

    def at(f: float, w: float, h: float) -> Vec:
        return (x0 + fx * f + lx * w, y0 + fy * f + ly * w, z0 + h)

    verts = [at(0, 0, 0), at(length, 0, 0), at(length, width, 0), at(0, width, 0), at(length, 0, rise),
             at(length, width, rise)]
    centre = tuple(sum(v[j] for v in verts) / len(verts) for j in range(3))
    faces: List[Tri] = []

    def add(tri: Tri) -> None:
        mid = tuple(sum(verts[i][j] for i in tri) / 3 - centre[j] for j in range(3))
        faces.append(_facing(verts, tri, mid))                                                    # outward from the centre

    add((0, 1, 2))
    add((0, 2, 3))                                                                                # bottom
    add((1, 2, 5))
    add((1, 5, 4))                                                                                # high end
    add((0, 4, 5))
    add((0, 5, 3))                                                                                # sloping surface
    add((0, 1, 4))                                                                                # side on the right
    add((3, 5, 2))                                                                                # side on the left
    return verts, faces
