"""Primitives of the results scene (C2): plain numpy data a renderer can draw, no rendering code.

Whatever draws the results (PyVista, Qt3D, a web view, a test) takes these four shapes:

* :class:`GridSurface`  - a coloured plane or boundary patch: x/y/z 2-D coordinate arrays + values
* :class:`TriMesh`      - triangles (isosurfaces): vertices, faces, optional per-vertex values
* :class:`PointCloud`   - particles: points, optional values, a drawing diameter
* :class:`VolumeGrid`   - a 3-D block of cells (smoke, fire, 3-D slices): origin, spacing, values, optional RGBA

``ClipPlane`` cuts any of them at an axis-aligned plane.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional, Tuple

import numpy as np

AXES = "xyz"


@dataclass
class GridSurface:
    name: str
    quantity: str
    units: str
    x: np.ndarray            # (n, m) coordinates of the grid points
    y: np.ndarray
    z: np.ndarray
    values: np.ndarray       # (n, m)
    axis: Optional[str] = None       # normal axis of a planar slice/patch: "x", "y" or "z"
    position: Optional[float] = None  # coordinate of that plane


@dataclass
class TriMesh:
    name: str
    quantity: str
    units: str
    vertices: np.ndarray     # (n, 3)
    faces: np.ndarray        # (m, 3) indices
    values: Optional[np.ndarray] = None   # (n,) per vertex
    level: Optional[float] = None         # isosurface value


@dataclass
class PointCloud:
    name: str
    quantity: str
    units: str
    points: np.ndarray       # (n, 3)
    values: Optional[np.ndarray] = None
    diameter: float = 0.01   # drawing size in metres


@dataclass
class VolumeGrid:
    name: str
    quantity: str
    units: str
    origin: Tuple[float, float, float]     # lower corner of cell (0, 0, 0)
    spacing: Tuple[float, float, float]    # cell size
    values: np.ndarray                     # (ni, nj, nk) cell values
    rgba: Optional[np.ndarray] = None      # (ni, nj, nk, 4) from a transfer function (smoke / fire)

    def centers(self):
        """1-D arrays of cell-centre coordinates per axis."""
        return tuple(self.origin[a] + (np.arange(self.values.shape[a]) + 0.5) * self.spacing[a] for a in range(3))


Primitive = Any   # GridSurface | TriMesh | PointCloud | VolumeGrid


@dataclass(frozen=True)
class ClipPlane:
    """Keep the part of the scene on one side of the plane ``axis = position``."""
    axis: str
    position: float
    keep: str = "above"      # "above" keeps coordinate >= position, "below" keeps <=

    def __post_init__(self):
        if self.axis not in tuple(AXES):
            raise ValueError("axis must be 'x', 'y' or 'z'")
        if self.keep not in ("above", "below"):
            raise ValueError("keep must be 'above' or 'below'")

    def mask(self, coords: np.ndarray) -> np.ndarray:
        """True where the coordinate array is kept."""
        return coords >= self.position if self.keep == "above" else coords <= self.position


def clip(prim: Primitive, plane: ClipPlane) -> Optional[Primitive]:
    """The primitive with the clipped part removed, or ``None`` when nothing is left."""
    a = AXES.index(plane.axis)
    if isinstance(prim, GridSurface):
        keep = plane.mask((prim.x, prim.y, prim.z)[a])
        if not keep.any():
            return None
        if keep.all():
            return prim
        v = np.where(keep, prim.values, np.nan)            # clipped points become holes (NaN)
        return replace(prim, values=v, x=np.where(keep, prim.x, np.nan), y=np.where(keep, prim.y, np.nan),
                       z=np.where(keep, prim.z, np.nan))
    if isinstance(prim, TriMesh):
        centroid = prim.vertices[prim.faces][:, :, a].mean(axis=1)
        keep = plane.mask(centroid)
        if not keep.any():
            return None
        return replace(prim, faces=prim.faces[keep])
    if isinstance(prim, PointCloud):
        keep = plane.mask(prim.points[:, a])
        if not keep.any():
            return None
        return replace(prim, points=prim.points[keep], values=None if prim.values is None else prim.values[keep])
    if isinstance(prim, VolumeGrid):
        c = prim.centers()[a]
        keep1d = plane.mask(c)
        if not keep1d.any():
            return None
        shape = [1, 1, 1]
        shape[a] = -1
        keep = keep1d.reshape(shape)
        vals = np.where(keep, prim.values, np.nan)
        rgba = None
        if prim.rgba is not None:
            rgba = prim.rgba.copy()
            rgba[..., 3] = np.where(keep, rgba[..., 3], 0.0)
        return replace(prim, values=vals, rgba=rgba)
    raise TypeError(f"cannot clip {type(prim).__name__}")


# -- mesh node coordinates ---------------------------------------------------------------------
def node_coords(mesh: Any, axis: int) -> np.ndarray:
    """Cell-boundary coordinates along *axis* (0, 1, 2) of a mesh-like object (uniform cells)."""
    lo = getattr(mesh, AXES[axis] + "_min")
    hi = getattr(mesh, AXES[axis] + "_max")
    return np.linspace(lo, hi, int(mesh.cell_count[axis]) + 1)


def index_range_coords(mesh: Any, axis: int, i1: int, i2: int) -> np.ndarray:
    """Coordinates of grid indices i1..i2 (inclusive) along *axis*; clamps indices into the mesh."""
    nodes = node_coords(mesh, axis)
    idx = np.clip(np.arange(i1, i2 + 1), 0, len(nodes) - 1)
    return nodes[idx]
