"""Shared helper for the geometry transform commands."""
from __future__ import annotations


def _verts_centroid(verts: list) -> tuple:
    """Bbox centroid of a vertex list — shared default-origin helper for
    the Geom transform commands above. (0, 0, 0) for an empty mesh."""
    if not verts:
        return (0.0, 0.0, 0.0)
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
