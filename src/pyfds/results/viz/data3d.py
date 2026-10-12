"""Data3D tools (phase V6): points, arbitrary slices and isosurfaces cut from a 3-D dataset.

A Data3D object is a 3-D scalar field on a (possibly stretched) rectilinear grid: a 3-D slice file or a
Plot3D quantity. From it the viewer makes, without re-running FDS: a *point* (a value over time), a *slice*
on any plane, and an *isosurface* at any value. Isosurfaces use marching tetrahedra (six tetrahedra per
cell), which needs no extra libraries and gives closed, consistent surfaces.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .primitives import GridSurface, RectilinearVolume, TriMesh


def _interp(vol: RectilinearVolume) -> RegularGridInterpolator:
    return RegularGridInterpolator((vol.x, vol.y, vol.z), vol.values, bounds_error=False, fill_value=np.nan)


def inside(vol: RectilinearVolume, xyz: Sequence[float]) -> bool:
    return all(a[0] <= c <= a[-1] for a, c in zip((vol.x, vol.y, vol.z), xyz))


def sample_point(vol: RectilinearVolume, xyz: Sequence[float]) -> float:
    """Trilinear value at a point (NaN outside the grid)."""
    if len(xyz) != 3:
        raise ValueError("a point needs x, y, z")
    return float(_interp(vol)(np.array([xyz], dtype=float))[0])


def point_series(volumes: Sequence[RectilinearVolume], xyz: Sequence[float]) -> np.ndarray:
    """The value at a point from a list of frames (one volume per time)."""
    return np.array([sample_point(v, xyz) for v in volumes])


def _plane_basis(normal: Sequence[float]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = np.asarray(normal, dtype=float)
    length = np.linalg.norm(n)
    if length == 0:
        raise ValueError("the plane normal must not be zero")
    n = n / length
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return n, u, v


def slice_plane(vol: RectilinearVolume, origin: Sequence[float], normal: Sequence[float],
                resolution: Optional[float] = None) -> Optional[GridSurface]:
    """Values of the volume on the plane through *origin* with *normal* (any orientation, not just axis-aligned).
    Returns ``None`` when the plane misses the volume."""
    n, u, v = _plane_basis(normal)
    b = vol.bounds()
    corners = np.array([[x, y, z] for x in b[0:2] for y in b[2:4] for z in b[4:6]])
    o = np.asarray(origin, dtype=float)
    rel = corners - o
    su, sv = rel @ u, rel @ v
    if not (rel @ n).min() <= 0 <= (rel @ n).max():
        return None
    h = resolution or vol.cell_size()
    us = np.arange(su.min(), su.max() + h, h)
    vs = np.arange(sv.min(), sv.max() + h, h)
    U, V = np.meshgrid(us, vs, indexing="ij")
    pts = o + U[..., None] * u + V[..., None] * v
    vals = _interp(vol)(pts.reshape(-1, 3)).reshape(U.shape)
    if np.isnan(vals).all():
        return None
    axis = int(np.argmax(np.abs(n)))
    aligned = abs(abs(n[axis]) - 1.0) < 1e-9
    return GridSurface("slice", vol.quantity, vol.units, pts[..., 0], pts[..., 1], pts[..., 2], vals,
                       "xyz"[axis] if aligned else None, float(o[axis]) if aligned else None)


# 6 tetrahedra around the cube diagonal 0-6 (vertex numbering: bit 0 = x, bit 1 = y, bit 2 = z)
_TETS = np.array([[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]])


def isosurface(vol: RectilinearVolume, value: float) -> TriMesh:
    """Triangles of the surface where the field equals *value* (empty mesh when it never crosses)."""
    vals = vol.values
    if not (np.nanmin(vals) < value < np.nanmax(vals)) and not np.any(vals == value):
        return TriMesh("iso", vol.quantity, vol.units, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), None, value)
    nx, ny, nz = vals.shape
    if min(nx, ny, nz) < 2:
        raise ValueError("an isosurface needs at least two nodes in every direction")
    gx, gy, gz = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1), np.arange(nz - 1), indexing="ij")
    base = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])              # cell origins
    offs = np.array([[i & 1, (i >> 1) & 1, (i >> 2) & 1] for i in range(8)])
    # cube corner index order used in _TETS: 0:(0,0,0) 1:(1,0,0) 2:(1,1,0) 3:(0,1,0) 4:(0,0,1) 5:(1,0,1) 6:(1,1,1) 7:(0,1,1)
    corner = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
    cv = np.stack([vals[base[:, 0] + c[0], base[:, 1] + c[1], base[:, 2] + c[2]] for c in corner], axis=1)   # (cells, 8)
    cx = np.stack([vol.x[base[:, 0] + c[0]] for c in corner], axis=1)
    cy = np.stack([vol.y[base[:, 1] + c[1]] for c in corner], axis=1)
    cz = np.stack([vol.z[base[:, 2] + c[2]] for c in corner], axis=1)
    keep = (np.nanmin(cv, axis=1) <= value) & (np.nanmax(cv, axis=1) >= value)
    cv, cx, cy, cz = cv[keep], cx[keep], cy[keep], cz[keep]
    tris: list = []
    for tet in _TETS:
        v = cv[:, tet]                                   # (cells, 4)
        p = np.stack([cx[:, tet], cy[:, tet], cz[:, tet]], axis=2)       # (cells, 4, 3)
        above = v >= value
        n_above = above.sum(axis=1)
        for case in (1, 2, 3):
            sel = n_above == case
            if not sel.any():
                continue
            vs, ps, ab = v[sel], p[sel], above[sel]
            if case == 2:
                order = np.argsort(~ab, axis=1, kind="stable")           # the two above first
                pa = np.take_along_axis(ps, order[..., None], 1)
                va = np.take_along_axis(vs, order, 1)
                e = [(0, 2), (0, 3), (1, 3), (1, 2)]                      # quad between {0,1} above and {2,3} below
                pts = [_cut(pa[:, i], pa[:, j], va[:, i], va[:, j], value) for i, j in e]
                tris += [np.stack([pts[0], pts[1], pts[2]], 1), np.stack([pts[0], pts[2], pts[3]], 1)]
            else:
                lone_above = case == 1
                order = np.argsort(~ab if lone_above else ab, axis=1, kind="stable")      # the lone vertex first
                pl = np.take_along_axis(ps, order[..., None], 1)
                vl = np.take_along_axis(vs, order, 1)
                pts = [_cut(pl[:, 0], pl[:, j], vl[:, 0], vl[:, j], value) for j in (1, 2, 3)]
                tris.append(np.stack(pts, 1))
    if not tris:
        return TriMesh("iso", vol.quantity, vol.units, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), None, value)
    allt = np.concatenate(tris, axis=0)                  # (n, 3, 3)
    verts = allt.reshape(-1, 3)
    uniq, inv = np.unique(np.round(verts, 9), axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3)
    good = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return TriMesh("iso", vol.quantity, vol.units, uniq, faces[good].astype(np.int64), None, value)


def _cut(p0, p1, v0, v1, value):
    d = v1 - v0
    t = np.where(np.abs(d) < 1e-30, 0.5, (value - v0) / np.where(d == 0, 1, d))
    return p0 + (p1 - p0) * t[:, None]
