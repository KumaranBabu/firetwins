"""Section-box clipping and multi-floor layout applied to every kind of viewer primitive."""
from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..scene_data import ClipPlane, GridSurface, PointCloud, TriMesh, VolumeGrid, clip
from .floors import FloorLayout
from .primitives import ErrorBoxes, GeometryBoxes, RectilinearVolume, VectorField, XB

Plane = Tuple[str, float, str]


def _clip_box(b: XB, planes: Sequence[Plane]) -> Optional[XB]:
    lo = [b[0], b[2], b[4]]
    hi = [b[1], b[3], b[5]]
    for axis, pos, keep in planes:
        a = "xyz".index(axis)
        if keep == "above":
            lo[a] = max(lo[a], pos)
        else:
            hi[a] = min(hi[a], pos)
        if hi[a] < lo[a]:
            return None
    return (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])


def clip_primitive(p, planes: Sequence[Plane]):
    """The primitive with everything outside the section box removed, or ``None`` when nothing is left."""
    if not planes:
        return p
    if isinstance(p, (GeometryBoxes, ErrorBoxes)):
        keep = [(i, _clip_box(b, planes)) for i, b in enumerate(p.boxes)]
        keep = [(i, b) for i, b in keep if b is not None]
        if not keep:
            return None
        kw = {"boxes": [b for _, b in keep]}
        if isinstance(p, GeometryBoxes):
            kw["labels"] = [p.labels[i] for i, _ in keep] if p.labels else []
            kw["colors"] = [p.colors[i] for i, _ in keep] if p.colors else []
        else:
            kw["values"] = [p.values[i] for i, _ in keep] if p.values else []
        return replace(p, **kw)
    if isinstance(p, RectilinearVolume):
        axes = [p.x, p.y, p.z]
        mask = np.ones(p.values.shape, dtype=bool)
        for axis, pos, keep in planes:
            a = "xyz".index(axis)
            m1 = axes[a] >= pos if keep == "above" else axes[a] <= pos
            shape = [1, 1, 1]
            shape[a] = -1
            mask &= m1.reshape(shape)
        if not mask.any():
            return None
        out = replace(p, values=np.where(mask, p.values, np.nan))
        if p.extinction is not None:
            out.extinction = np.where(mask, p.extinction, 0.0)
        return out
    if isinstance(p, VectorField):
        keep = np.ones(len(p.points), dtype=bool)
        for axis, pos, k in planes:
            c = p.points[:, "xyz".index(axis)]
            keep &= (c >= pos) if k == "above" else (c <= pos)
        if not keep.any():
            return None
        return replace(p, points=p.points[keep], vectors=p.vectors[keep], values=None if p.values is None else p.values[keep])
    out = p
    for axis, pos, k in planes:
        out = clip(out, ClipPlane(axis, pos, k))
        if out is None:
            return None
    return out


def layout_primitive(p, layout: FloorLayout):
    """Move a primitive to where its floor is drawn; hidden floors and clipped wall heights drop points/boxes.
    Volumes are left where they are (they span floors)."""
    if layout is None or not layout.active:
        return p
    if isinstance(p, (GeometryBoxes, ErrorBoxes)):
        boxes, labels, colors, values = [], [], [], []
        for i, b in enumerate(p.boxes):
            corners = np.array([[b[0], b[2], b[4]], [b[1], b[3], b[5]]])
            moved, keep = layout.apply(corners[:1])
            if not keep[0]:
                continue
            off = moved[0] - corners[0]
            h = layout.s.wall_height if layout.s.clip_walls else None
            zmax = b[5]
            if h is not None:
                level = layout.s.floors[min(max(int(np.searchsorted(layout.s.floors, b[4] + 1e-9, side="right")) - 1, 0), len(layout.s.floors) - 1)]
                zmax = min(zmax, level + h)
            boxes.append((b[0] + off[0], b[1] + off[0], b[2] + off[1], b[3] + off[1], b[4] + off[2], zmax + off[2]))
            if getattr(p, "labels", None):
                labels.append(p.labels[i])
            if getattr(p, "colors", None):
                colors.append(p.colors[i])
            if getattr(p, "values", None):
                values.append(p.values[i])
        if not boxes:
            return None
        kw = {"boxes": boxes}
        if isinstance(p, GeometryBoxes):
            kw.update(labels=labels, colors=colors)
        else:
            kw["values"] = values
        return replace(p, **kw)
    if isinstance(p, GridSurface):
        pts = np.stack([p.x.ravel(), p.y.ravel(), p.z.ravel()], axis=1)
        moved, keep = layout.apply(pts)
        if not keep.any():
            return None
        v = np.where(keep.reshape(p.values.shape), p.values, np.nan)
        return replace(p, x=moved[:, 0].reshape(p.x.shape), y=moved[:, 1].reshape(p.x.shape),
                       z=moved[:, 2].reshape(p.x.shape), values=v)
    if isinstance(p, TriMesh):
        moved, keep = layout.apply(p.vertices)
        faces = p.faces[keep[p.faces].all(axis=1)]
        return replace(p, vertices=moved, faces=faces) if len(faces) else None
    if isinstance(p, PointCloud):
        moved, keep = layout.apply(p.points)
        if not keep.any():
            return None
        return replace(p, points=moved[keep], values=None if p.values is None else p.values[keep])
    if isinstance(p, VectorField):
        moved, keep = layout.apply(p.points)
        if not keep.any():
            return None
        return replace(p, points=moved[keep], vectors=p.vectors[keep], values=None if p.values is None else p.values[keep])
    return p


def thin_volume(vol: RectilinearVolume, max_nodes: int = 1_500_000) -> RectilinearVolume:
    """Level of detail: keep every n-th node in each direction until the volume has at most *max_nodes* nodes."""
    n = vol.values.size
    if n <= max_nodes:
        return vol
    step = int(np.ceil((n / max_nodes) ** (1.0 / 3.0)))
    sl = slice(None, None, step)
    out = replace(vol, x=vol.x[sl], y=vol.y[sl], z=vol.z[sl], values=vol.values[sl, sl, sl])
    if vol.extinction is not None:
        out.extinction = vol.extinction[sl, sl, sl]
    return out
