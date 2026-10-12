"""What a click in the 3D view hit (pure numpy): the clicked object's name, its extent and the value under the pointer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

from .data3d import sample_point
from .primitives import ErrorBoxes, GeometryBoxes, GridSurface, PointCloud, RectilinearVolume, TriMesh, VectorField

XB = Tuple[float, float, float, float, float, float]


@dataclass
class PickInfo:
    node_id: str
    kind: str                                  # obstruction | vent | open_vent | mesh | slice | isosurface | volume | ...
    label: str
    point: Tuple[float, float, float]
    text: str                                  # one line for the status bar
    box: Optional[XB] = None                   # the picked box, to highlight
    value: Optional[float] = None
    units: str = ""


def _inside(xb: XB, p: Sequence[float], tol: float) -> bool:
    return all(xb[2 * a] - tol <= p[a] <= xb[2 * a + 1] + tol for a in range(3))


def _nearest_box(boxes, p, tol: float) -> Optional[int]:
    """Index of the box the point lies in (or touches); of several, the smallest one (a burner sits on a floor slab)."""
    hits = [i for i, b in enumerate(boxes) if _inside(b, p, tol)]
    if not hits:
        return None
    return min(hits, key=lambda i: float(np.prod([max(boxes[i][2 * a + 1] - boxes[i][2 * a], 1e-9) for a in range(3)])))


def describe(node_id: str, node_label: str, prim, point: Sequence[float], tol: float = 1e-3) -> PickInfo:
    """Describe what is under *point* on primitive *prim*."""
    p = tuple(float(c) for c in point)
    where = f"({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}) m"
    if isinstance(prim, (GeometryBoxes, ErrorBoxes)):
        i = _nearest_box(prim.boxes, p, tol)
        kind = getattr(prim, "kind", "error")
        if i is None:
            return PickInfo(node_id, kind, node_label, p, f"{node_label} at {where}")
        xb = tuple(float(c) for c in prim.boxes[i])
        names = getattr(prim, "labels", None) or []
        name = names[i] if i < len(names) and names[i] else node_label
        what = {"obstruction": "Obstruction", "vent": "Vent", "open_vent": "Open boundary", "mesh": "Mesh"}.get(kind, kind.title())
        size = f"{xb[1] - xb[0]:.2f} x {xb[3] - xb[2]:.2f} x {xb[5] - xb[4]:.2f} m"
        return PickInfo(node_id, kind, name, p, f"{what} {name}: XB = {', '.join(f'{c:g}' for c in xb)}  ({size})", xb)
    if isinstance(prim, GridSurface):
        d = (prim.x - p[0]) ** 2 + (prim.y - p[1]) ** 2 + (prim.z - p[2]) ** 2
        k = np.unravel_index(int(np.argmin(d)), d.shape)
        v = float(prim.values[k])
        return PickInfo(node_id, "slice", node_label, p, f"{node_label}: {prim.quantity} = {v:.4g} {prim.units} at {where}", None, v,
                        prim.units)
    if isinstance(prim, RectilinearVolume):
        v = sample_point(prim, p)
        v = None if np.isnan(v) else v
        txt = f"{node_label}: {prim.quantity} = {v:.4g} {prim.units} at {where}" if v is not None else f"{node_label} at {where}"
        return PickInfo(node_id, "volume", node_label, p, txt, None, v, prim.units)
    if isinstance(prim, TriMesh):
        lvl = f" = {prim.level:g} {prim.units}" if prim.level is not None else ""
        return PickInfo(node_id, "isosurface", node_label, p, f"{node_label}: {prim.quantity}{lvl} at {where}", None, prim.level, prim.units)
    if isinstance(prim, (PointCloud, VectorField)):
        pts = prim.points
        v = None
        if len(pts):
            k = int(np.argmin(((pts - np.asarray(p)) ** 2).sum(axis=1)))
            vals = getattr(prim, "values", None)
            v = float(vals[k]) if vals is not None and len(vals) > k else None
        return PickInfo(node_id, "points", node_label, p, f"{node_label} at {where}", None, v, getattr(prim, "units", ""))
    return PickInfo(node_id, "other", node_label, p, f"{node_label} at {where}")
