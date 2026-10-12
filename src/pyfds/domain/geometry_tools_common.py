"""Geometry tool helper types."""
from __future__ import annotations

from typing import List, Tuple


_Vertex = Tuple[float, float, float]


_Face   = Tuple[int, int, int]


def _geom_to_polydata(geom: "Geom") -> "pv.PolyData":  # noqa: F821
    """Same triangle-array construction ``viewport_scene.py``'s
    ``build_scene`` already uses to render a Geom — kept as a private
    duplicate rather than a cross-import since ``domain/`` must not depend
    on ``gui/``."""
    import pyvista as pv

    if not geom.verts or not geom.faces:
        raise ValueError(f"Geom '{geom.name}' has no vertices/faces.")
    flat_faces: List[int] = []
    for face in geom.faces:
        flat_faces.append(len(face))
        flat_faces.extend(face)
    return pv.PolyData(geom.verts, flat_faces)
