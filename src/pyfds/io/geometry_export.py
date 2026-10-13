"""Write ``Geom`` shapes (or obstructions as boxes) to STL / OBJ (IMP-07).

FDS coordinates are metres, Z up. ``units`` converts to the target file's length unit and
``up_axis="Y"`` rotates to a Y-up convention, the exact inverse of the importers.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from .mesh_importers import unit_factor

Tri = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]


def box_triangles(xb: Sequence[float]) -> List[Tuple[Tuple[float, float, float], ...]]:
    """The 12 outward-facing triangles of an axis-aligned box."""
    x0, x1, y0, y1, z0, z1 = xb
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    idx = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
           (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]
    return [tuple(p[i] for i in t) for t in idx]


def _convert(pt, k, up_axis):
    x, y, z = pt[0] * k, pt[1] * k, pt[2] * k
    return (x, z, -y) if up_axis.upper() == "Y" else (x, y, z)


def _check(units: str, up_axis: str) -> float:
    if up_axis.upper() not in ("Y", "Z"):
        raise ValueError("up_axis must be 'Y' or 'Z'")
    return 1.0 / unit_factor(units)


def collect(geoms: Iterable, obstructions: Iterable = ()) -> List[Tuple[str, List[Tri]]]:
    """``[(name, triangles)]`` for the given Geoms and (as boxes) obstructions."""
    shapes: List[Tuple[str, List[Tri]]] = []
    for g in geoms:
        if not g.verts or not g.faces:
            continue
        shapes.append((g.name, [tuple(g.verts[i] for i in f) for f in g.faces]))
    for o in obstructions:
        shapes.append((o.name, box_triangles((o.x_min, o.x_max, o.y_min, o.y_max, o.z_min, o.z_max))))
    return shapes


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    m = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
    return (0.0, 0.0, 0.0) if m == 0 else (n[0] / m, n[1] / m, n[2] / m)


def write_stl(path: str, shapes: List[Tuple[str, List[Tri]]], *, units: str = "m", up_axis: str = "Z",
              ascii_format: bool = False) -> int:
    """Write all shapes into one STL file; returns the triangle count."""
    k = _check(units, up_axis)
    tris = [tuple(_convert(p, k, up_axis) for p in t) for _, ts in shapes for t in ts]
    if not tris:
        raise ValueError("nothing to export: no geometry with triangles")
    p = Path(path)
    if ascii_format:
        lines = ["solid pyfds"]
        for a, b, c in tris:
            n = _normal(a, b, c)
            lines += [f"facet normal {n[0]:.6g} {n[1]:.6g} {n[2]:.6g}", " outer loop"]
            lines += [f"  vertex {q[0]:.9g} {q[1]:.9g} {q[2]:.9g}" for q in (a, b, c)]
            lines += [" endloop", "endfacet"]
        lines.append("endsolid pyfds")
        p.write_text("\n".join(lines) + "\n", encoding="ascii")
    else:
        out = bytearray(b"PyFDS binary STL".ljust(80, b" "))
        out += struct.pack("<I", len(tris))
        for a, b, c in tris:
            out += struct.pack("<12fH", *_normal(a, b, c), *a, *b, *c, 0)
        p.write_bytes(bytes(out))
    return len(tris)


def write_obj(path: str, shapes: List[Tuple[str, List[Tri]]], *, units: str = "m", up_axis: str = "Z") -> int:
    """Write an OBJ with one ``o`` group per shape; returns the triangle count."""
    k = _check(units, up_axis)
    if not any(ts for _, ts in shapes):
        raise ValueError("nothing to export: no geometry with triangles")
    lines = ["# exported by PyFDS"]
    base, count = 1, 0
    for name, tris in shapes:
        index, pts, faces = {}, [], []
        for t in tris:
            row = []
            for q in t:
                q = tuple(round(c, 9) for c in _convert(q, k, up_axis))
                if q not in index:
                    index[q] = len(pts)
                    pts.append(q)
                row.append(index[q] + base)
            faces.append(row)
        lines.append(f"o {name.replace(' ', '_')}")
        lines += [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in pts]
        lines += [f"f {a} {b} {c}" for a, b, c in faces]
        base += len(pts)
        count += len(faces)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count
