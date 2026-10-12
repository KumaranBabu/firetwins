"""Renderer-agnostic results scene (C2): layers fed by the existing readers, drawn by anyone.

A :class:`ResultsScene` holds *layers* (slices, boundary files, isosurfaces, particles, smoke / fire
volumes). Every layer knows its own frame times; the scene merges them into one timeline and, for a
time, hands back plain numpy primitives (:mod:`pyfds.results.scene_data`) with the scene's clip planes
applied. It also answers probe questions ("what is the temperature at this point now?"). Nothing here
draws anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import transfer
from .scene_data import (AXES, ClipPlane, GridSurface, PointCloud, TriMesh, VolumeGrid, clip,
                         index_range_coords, node_coords)


def _nearest_before(times: np.ndarray, t: float) -> int:
    """Index of the last frame at or before *t* (the first frame before the start)."""
    if len(times) == 0:
        raise ValueError("layer has no frames")
    return int(np.clip(np.searchsorted(times, t + 1e-9) - 1, 0, len(times) - 1))


class Layer:
    """Base: a named, switchable source of primitives over time."""
    kind = "layer"

    def __init__(self, name: str, times: Sequence[float], opacity: float = 1.0) -> None:
        self.name = name
        self.times = np.asarray(times, dtype=float)
        self.visible = True
        self.opacity = opacity

    @property
    def n_frames(self) -> int:
        return len(self.times)

    def index_at(self, t: float) -> int:
        return _nearest_before(self.times, t)

    def primitives(self, i: int) -> List[Any]:           # pragma: no cover - overridden
        raise NotImplementedError

    def value_range(self) -> Tuple[float, float]:
        raise NotImplementedError

    def sample(self, point: Sequence[float], i: int, tol: Optional[float] = None) -> Optional[Dict[str, Any]]:
        return None

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "visible": self.visible, "opacity": self.opacity,
                "frames": self.n_frames,
                "t_start": float(self.times[0]) if self.n_frames else None,
                "t_end": float(self.times[-1]) if self.n_frames else None}


# -- slices ---------------------------------------------------------------------------------------
class SliceLayer(Layer):
    """A slice file (``ReaderResult`` from ``SliceReader``): a plane, or a volume for 3-D slices."""
    kind = "slice"

    def __init__(self, name: str, result: Any, mesh: Any = None, opacity: float = 1.0) -> None:
        super().__init__(name, result.times, opacity)
        data = result.data
        if data is None or getattr(data, "size", 0) == 0:
            raise ValueError("the slice has no data")
        self.result, self.mesh = result, mesh
        self.header = (result.metadata or {}).get("header")
        self.quantity, self.units = result.quantity, result.units
        shape = data.shape[1:]
        self.planar = any(n == 1 for n in shape)
        self.kind = "slice" if self.planar else "volume"
        self._axes = self._axis_coords(shape)

    def _axis_coords(self, shape):
        h = self.header
        rng = [(h.i1, h.i2), (h.j1, h.j2), (h.k1, h.k2)] if h is not None else [(0, n - 1) for n in shape]
        out = []
        for a in range(3):
            if self.mesh is not None:
                out.append(index_range_coords(self.mesh, a, *rng[a]))
            else:
                out.append(np.arange(rng[a][0], rng[a][1] + 1, dtype=float))
        return out

    def primitives(self, i: int) -> List[Any]:
        frame = self.result.data[i]
        if not self.planar:
            ax = self._axes
            sp = tuple(float(np.diff(c).mean()) if len(c) > 1 else 1.0 for c in ax)
            origin = tuple(float(c[0]) - s / 2 for c, s in zip(ax, sp))
            return [VolumeGrid(self.name, self.quantity, self.units, origin, sp, frame.copy())]
        d = [n == 1 for n in frame.shape].index(True)
        keep = [a for a in range(3) if a != d]
        a, b = self._axes[keep[0]], self._axes[keep[1]]
        A, B = np.meshgrid(a, b, indexing="ij")
        pos = float(self._axes[d][0])
        coords = [None, None, None]
        coords[keep[0]], coords[keep[1]], coords[d] = A, B, np.full_like(A, pos)
        return [GridSurface(self.name, self.quantity, self.units, coords[0], coords[1], coords[2],
                            np.squeeze(frame, axis=d).astype(float), AXES[d], pos)]

    def value_range(self):
        return float(np.nanmin(self.result.data)), float(np.nanmax(self.result.data))

    def sample(self, point, i, tol=None):
        frame = self.result.data[i]
        if self.planar:
            d = [n == 1 for n in frame.shape].index(True)
            c = self._axes[d]
            tol = tol if tol is not None else (self._cell(d) / 2 if self.mesh is not None else 0.5)
            if abs(point[d] - float(c[0])) > tol:
                return None
        idx = []
        for a in range(3):
            c = self._axes[a]
            if len(c) == 1:
                idx.append(0)
                continue
            half = abs(c[1] - c[0]) / 2
            if point[a] < c.min() - half or point[a] > c.max() + half:
                return None
            idx.append(int(np.abs(c - point[a]).argmin()))
        return {"layer": self.name, "quantity": self.quantity, "units": self.units,
                "value": float(frame[tuple(idx)]), "time": float(self.times[i])}

    def _cell(self, a: int) -> float:
        return float((getattr(self.mesh, AXES[a] + "_max") - getattr(self.mesh, AXES[a] + "_min")) / self.mesh.cell_count[a])


# -- boundary files ---------------------------------------------------------------------------------
class BoundaryLayer(Layer):
    """A boundary file: one surface patch per mesh face, drawn as coloured grids."""
    kind = "boundary"

    def __init__(self, name: str, header: Any, patches: Sequence[Any], frames: Sequence[Any],
                 meshes: Optional[Sequence[Any]] = None, opacity: float = 1.0) -> None:
        super().__init__(name, [f.time for f in frames], opacity)
        self.header, self.patches, self.frames = header, list(patches), list(frames)
        self.meshes = list(meshes or [])
        self.quantity, self.units = header.quantity, header.units

    def _mesh(self, patch):
        if not self.meshes:
            return None
        return self.meshes[patch.iblk - 1] if 1 <= patch.iblk <= len(self.meshes) else self.meshes[0]

    def primitives(self, i: int) -> List[Any]:
        out = []
        for p, vals in zip(self.patches, self.frames[i].patch_data):
            rng = [(p.i1, p.i2), (p.j1, p.j2), (p.k1, p.k2)]
            shape = tuple(r[1] - r[0] + 1 for r in rng)
            singles = [n == 1 for n in shape]
            if sum(singles) != 1 or vals.size != int(np.prod(shape)):
                continue                                    # not a flat face
            d = singles.index(True)
            keep = [a for a in range(3) if a != d]
            m = self._mesh(p)
            axes = [index_range_coords(m, a, *rng[a]) if m is not None else np.arange(rng[a][0], rng[a][1] + 1, dtype=float)
                    for a in range(3)]
            A, B = np.meshgrid(axes[keep[0]], axes[keep[1]], indexing="ij")
            coords = [None, None, None]
            coords[keep[0]], coords[keep[1]], coords[d] = A, B, np.full_like(A, float(axes[d][0]))
            out.append(GridSurface(self.name, self.quantity, self.units, coords[0], coords[1], coords[2],
                                   np.squeeze(vals.reshape(shape, order="F"), axis=d), AXES[d], float(axes[d][0])))
        return out

    def value_range(self):
        lo = min(float(np.nanmin(v)) for f in self.frames for v in f.patch_data)
        hi = max(float(np.nanmax(v)) for f in self.frames for v in f.patch_data)
        return lo, hi


# -- isosurfaces ------------------------------------------------------------------------------------
class IsoLayer(Layer):
    kind = "isosurface"

    def __init__(self, name: str, iso: Any, level: Optional[float] = None, opacity: float = 1.0) -> None:
        super().__init__(name, [f.time for f in iso.frames], opacity)
        self.iso, self.level = iso, level
        self.quantity, self.units = iso.quantity, iso.units

    def primitives(self, i: int) -> List[Any]:
        f = self.iso.frames[i]
        return [TriMesh(self.name, self.quantity, self.units, np.asarray(f.vertices, dtype=float),
                        np.asarray(f.triangles, dtype=int), None if f.values is None else np.asarray(f.values, float),
                        self.level)]

    def value_range(self):
        vals = [f.values for f in self.iso.frames if f.values is not None and len(f.values)]
        if not vals:
            return (self.level or 0.0, self.level or 0.0)
        return min(float(v.min()) for v in vals), max(float(v.max()) for v in vals)


# -- particles --------------------------------------------------------------------------------------
class ParticleLayer(Layer):
    kind = "particles"

    def __init__(self, name: str, pclass: Any, quantity: Optional[str] = None, diameter: float = 0.01,
                 opacity: float = 1.0) -> None:
        super().__init__(name, pclass.times, opacity)
        self.pclass, self.diameter = pclass, diameter
        names = list(pclass.quantity_names)
        if quantity is not None and quantity not in names:
            raise KeyError(f"particle class {pclass.name!r} has no quantity {quantity!r}; has {names}")
        self.quantity = quantity or ""
        self.units = pclass.units[names.index(quantity)] if quantity else ""

    def primitives(self, i: int) -> List[Any]:
        f = self.pclass.frames[i]
        vals = f.quantities.get(self.quantity) if self.quantity else None
        return [PointCloud(self.name, self.quantity, self.units, np.asarray(f.positions, float).reshape(-1, 3),
                           None if vals is None else np.asarray(vals, float), self.diameter)]

    def value_range(self):
        if not self.quantity:
            return (0.0, 0.0)
        arrs = [f.quantities[self.quantity] for f in self.pclass.frames if len(f.quantities.get(self.quantity, []))]
        return (min(float(a.min()) for a in arrs), max(float(a.max()) for a in arrs)) if arrs else (0.0, 0.0)


# -- smoke / fire / 3-D scalar volumes ---------------------------------------------------------------
class VolumeLayer(Layer):
    """A 4-D array ``(frames, ni, nj, nk)`` on a mesh, shown as smoke, fire or a plain scalar volume."""

    def __init__(self, name: str, values: np.ndarray, times: Sequence[float], mesh: Any, quantity: str = "",
                 units: str = "", volume_kind: str = "scalar", opacity: float = 1.0, **transfer_options) -> None:
        super().__init__(name, times, opacity)
        values = np.asarray(values, dtype=float)
        if values.ndim != 4 or values.shape[0] != len(self.times):
            raise ValueError("values must have shape (frames, ni, nj, nk) matching the times")
        if volume_kind not in ("scalar", "smoke", "fire"):
            raise ValueError("volume_kind must be scalar, smoke or fire")
        self.values, self.mesh = values, mesh
        self.quantity, self.units, self.volume_kind = quantity, units, volume_kind
        self.kind = "smoke" if volume_kind == "smoke" else "fire" if volume_kind == "fire" else "volume"
        self.options = transfer_options
        self.spacing = tuple(float((getattr(mesh, AXES[a] + "_max") - getattr(mesh, AXES[a] + "_min")) / values.shape[1 + a])
                             for a in range(3))
        self.origin = tuple(float(node_coords(mesh, a)[0]) for a in range(3))

    def primitives(self, i: int) -> List[Any]:
        v = self.values[i]
        rgba = None
        if self.volume_kind != "scalar":
            opts = dict(self.options)
            opts.setdefault("opacity", self.opacity)
            rgba = transfer.apply(self.volume_kind, v, float(np.mean(self.spacing)), **opts)
        return [VolumeGrid(self.name, self.quantity, self.units, self.origin, self.spacing, v.copy(), rgba)]

    def value_range(self):
        return float(np.nanmin(self.values)), float(np.nanmax(self.values))

    def sample(self, point, i, tol=None):
        idx = []
        for a in range(3):
            f = (point[a] - self.origin[a]) / self.spacing[a]
            if not 0 <= f < self.values.shape[1 + a]:
                return None
            idx.append(int(f))
        return {"layer": self.name, "quantity": self.quantity, "units": self.units,
                "value": float(self.values[i][tuple(idx)]), "time": float(self.times[i])}


# -- the scene --------------------------------------------------------------------------------------
@dataclass
class SceneFrame:
    time: float
    items: List[Tuple[str, Any]] = field(default_factory=list)       # (layer name, primitive)

    def of(self, layer: str) -> List[Any]:
        return [p for n, p in self.items if n == layer]


class ResultsScene:
    def __init__(self) -> None:
        self._layers: Dict[str, Layer] = {}
        self.clips: List[ClipPlane] = []

    # layers
    def add(self, layer: Layer) -> Layer:
        if layer.name in self._layers:
            raise ValueError(f"the scene already has a layer called {layer.name!r}")
        if layer.n_frames == 0:
            raise ValueError(f"layer {layer.name!r} has no frames")
        self._layers[layer.name] = layer
        return layer

    def remove(self, name: str) -> None:
        self.layer(name)
        del self._layers[name]

    def layer(self, name: str) -> Layer:
        try:
            return self._layers[name]
        except KeyError:
            raise KeyError(f"no layer {name!r}; have {sorted(self._layers)}") from None

    @property
    def layers(self) -> List[Layer]:
        return list(self._layers.values())

    def unique_name(self, base: str) -> str:
        if base not in self._layers:
            return base
        i = 2
        while f"{base}_{i}" in self._layers:
            i += 1
        return f"{base}_{i}"

    def set_visible(self, name: str, visible: bool) -> None:
        self.layer(name).visible = bool(visible)

    def set_opacity(self, name: str, opacity: float) -> None:
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("opacity must be between 0 and 1")
        self.layer(name).opacity = opacity

    # timeline
    @property
    def times(self) -> np.ndarray:
        if not self._layers:
            return np.array([])
        return np.unique(np.round(np.concatenate([l.times for l in self._layers.values()]), 6))

    @property
    def n_frames(self) -> int:
        return len(self.times)

    # clip planes
    def add_clip(self, axis: str, position: float, keep: str = "above") -> ClipPlane:
        c = ClipPlane(axis.lower(), float(position), keep)
        self.clips.append(c)
        return c

    def clear_clips(self) -> None:
        self.clips.clear()

    # frames
    def frame(self, t: float) -> SceneFrame:
        out = SceneFrame(float(t))
        for layer in self._layers.values():
            if not layer.visible:
                continue
            for prim in layer.primitives(layer.index_at(t)):
                for c in self.clips:
                    prim = clip(prim, c) if prim is not None else None
                if prim is not None:
                    out.items.append((layer.name, prim))
        return out

    def frame_index(self, k: int) -> SceneFrame:
        ts = self.times
        if not -len(ts) <= k < len(ts):
            raise IndexError(f"frame {k} out of range (the scene has {len(ts)} frames)")
        return self.frame(float(ts[k]))

    # probe
    def probe(self, point: Sequence[float], t: float, tol: Optional[float] = None) -> List[Dict[str, Any]]:
        """Values at *point* from every visible layer that has data there at time *t*."""
        if len(point) != 3:
            raise ValueError("point needs three coordinates")
        for c in self.clips:
            if not c.mask(np.asarray(point[AXES.index(c.axis)])):
                return []
        out = []
        for layer in self._layers.values():
            if layer.visible:
                hit = layer.sample(point, layer.index_at(t), tol)
                if hit is not None:
                    out.append(hit)
        return out

    def summary(self) -> Dict[str, Any]:
        ts = self.times
        return {"layers": [l.describe() for l in self._layers.values()], "frames": len(ts),
                "t_start": float(ts[0]) if len(ts) else None, "t_end": float(ts[-1]) if len(ts) else None,
                "clips": [(c.axis, c.position, c.keep) for c in self.clips]}
