"""Turns a navigation-tree leaf and a playback time into drawable primitives.

``ResultsDataset`` is the data half of the viewer: it opens the streaming readers lazily, picks (and by
default interpolates between) frames, converts units, builds smoke / fire / slice / boundary / particle
shapes in true mesh coordinates, and measures per-quantity statistics for the colorbars. It never draws.
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import colorbar as cb
from . import max_errors as me
from . import units as un
from .fds_run import FdsRun, SliceFile
from .model import ResultsVisualization
from .primitives import (ErrorBoxes, GeometryBoxes, GridSurface, PointCloud, RectilinearVolume, TriMesh, VectorField)
from .streams import (BoundaryStream, IsoStream, ParticleStream, Plot3DStream, SliceStream, Smoke3DStream,
                      open_stream)
from .tree import NavNode

STATS_VERSION = 1


@dataclass
class QuantityStats:
    min: float
    max: float
    p1: float
    p99: float
    n: int = 0


class ResultsDataset:
    def __init__(self, run: FdsRun, viz: ResultsVisualization, use_cache: bool = True, max_open: int = 24) -> None:
        self.run, self.viz, self.use_cache = run, viz, use_cache
        self._streams: "OrderedDict[str, object]" = OrderedDict()
        self._max_open = max_open
        self._stats: Dict[str, QuantityStats] = {}
        self._errors: Optional[Dict[str, List[me.ErrorSample]]] = None
        #: injected by the API: ``() -> GeometryBoxes`` for the sets that come from a model, not from the run
        self.requested_geometry: Optional[Callable[[], GeometryBoxes]] = None
        self.model_geometry: Optional[Callable[[], GeometryBoxes]] = None

    # -- streams -------------------------------------------------------------------------------------
    def stream(self, kind: str, file: str):
        path = str(self.run.resolve(file))
        s = self._streams.get(path)
        if s is None:
            s = open_stream(kind, path, self.use_cache)
            self._streams[path] = s
            while len(self._streams) > self._max_open:
                self._streams.popitem(last=False)
        else:
            self._streams.move_to_end(path)
        return s

    def refresh(self) -> int:
        """Pick up frames FDS has written since; returns the number of new records seen."""
        n = 0
        for s in self._streams.values():
            n += s.refresh()
        self._errors = None
        return n

    # -- time ----------------------------------------------------------------------------------------
    @property
    def offset(self) -> float:
        return self.viz.fds.time_offset + self.viz.timelines.fds_offset

    def leaf_times(self, leaf: NavNode) -> np.ndarray:
        """FDS times of the leaf's frames (before the time offset)."""
        k = leaf.kind
        if k == "slice2d" or k == "slice3d":
            return self.stream("slice", leaf.files[0]).times
        if k == "slice_vectors":
            return self.stream("slice", leaf.files[0]).times
        if k == "boundary":
            return self.stream("boundary", leaf.files[0]).times
        if k == "smoke3d":
            return self.stream("smoke3d", leaf.files[0]).times
        if k == "isosurface":
            return self.stream("isosurface", leaf.files[0]).times
        if k == "particles":
            return self.stream("particles", leaf.files[0]).times
        if k == "plot3d":
            by_name = {p.file: p.time for p in self.run.plot3d}
            return np.array(sorted(by_name[f] for f in leaf.files))
        if k == "max_error":
            s = self.errors()[leaf.data["which"]]
            return np.array([x.time for x in s])
        return np.array([self.run.times[0], self.run.times[1]])           # geometry, views: whole run

    def timeline(self, leaves: Sequence[NavNode]) -> np.ndarray:
        """The union of the leaves' frame times on the global clock (empty when nothing animated is active)."""
        parts = [self.leaf_times(l) for l in leaves if l.kind not in ("geometry", "view")]
        parts = [p for p in parts if len(p)]
        if not parts:
            return np.array([])
        return np.unique(np.round(np.concatenate(parts) + self.offset, 6))

    def _pick(self, times: np.ndarray, t_fds: float) -> Tuple[int, Optional[int], float]:
        n = len(times)
        if n == 0:
            raise ValueError("no frames")
        k = int(np.clip(np.searchsorted(times, t_fds + 1e-9) - 1, 0, n - 1))
        if not self.viz.fds.interpolate or k >= n - 1 or t_fds <= times[0] or times[k + 1] == times[k]:
            return k, None, 0.0
        a = float((t_fds - times[k]) / (times[k + 1] - times[k]))
        return k, k + 1, min(max(a, 0.0), 1.0)

    def _blend(self, get: Callable[[int], np.ndarray], times: np.ndarray, t_fds: float) -> np.ndarray:
        k0, k1, a = self._pick(times, t_fds)
        v0 = get(k0)
        if k1 is None:
            return v0
        return (1.0 - a) * v0 + a * get(k1)

    # -- statistics for colorbars --------------------------------------------------------------------------
    def stats(self, quantity: str, leaves: Sequence[NavNode]) -> QuantityStats:
        """Min, max and the middle 98 % of every value of *quantity* over all time (sampled; cached)."""
        mine = [l for l in leaves if l.quantity == quantity and l.kind in ("slice2d", "slice3d", "boundary", "plot3d",
                                                                          "smoke3d", "slice_vectors")]
        key = quantity + "|" + "|".join(sorted(f"{l.kind}:{f}" for l in mine for f in l.files))
        if key in self._stats:
            return self._stats[key]
        disk = self._load_stats(key, mine)
        if disk is not None:
            self._stats[key] = disk
            return disk
        samples: List[np.ndarray] = []
        for leaf in mine:
            for arr in self._sample_values(leaf):
                samples.append(np.asarray(arr, dtype=np.float32).ravel())
        if not samples:
            stats = QuantityStats(0.0, 1.0, 0.0, 1.0, 0)
        else:
            v = np.concatenate(samples)
            v = v[np.isfinite(v)]
            if v.size > 2_000_000:
                v = v[np.random.default_rng(0).choice(v.size, 2_000_000, replace=False)]
            stats = (QuantityStats(float(v.min()), float(v.max()), float(np.percentile(v, 1)),
                                   float(np.percentile(v, 99)), int(v.size)) if v.size else QuantityStats(0, 1, 0, 1, 0))
        self._stats[key] = stats
        self._save_stats(key, mine, stats)
        return stats

    def _sample_values(self, leaf: NavNode, max_frames: int = 24):
        def picks(n):
            return np.unique(np.linspace(0, n - 1, min(n, max_frames)).astype(int)) if n else []
        if leaf.kind in ("slice2d", "slice3d", "slice_vectors"):
            s = self.stream("slice", leaf.files[0])
            for k in picks(s.n_frames):
                yield s.frame(int(k))
        elif leaf.kind == "boundary":
            s = self.stream("boundary", leaf.files[0])
            for k in picks(s.n_frames):
                yield from s.frame(int(k))
        elif leaf.kind == "plot3d":
            for f in leaf.files[:max_frames]:
                yield self.stream("plot3d", f).data()[leaf.data["index"]]
        elif leaf.kind == "smoke3d":
            s = self.stream("smoke3d", leaf.files[0])
            for k in picks(s.n_frames):
                yield self._smoke_values(leaf, s.frame_bytes(int(k)))[1]

    def _stats_path(self) -> Path:
        return Path(self.run.path + ".pyfstats")

    def _fingerprint(self, leaves: Sequence[NavNode]) -> str:
        parts = []
        for l in leaves:
            for f in l.files:
                p = self.run.resolve(f)
                parts.append(f"{f}:{p.stat().st_size if p.exists() else 0}")
        return ";".join(parts)

    def _load_stats(self, key: str, leaves: Sequence[NavNode]) -> Optional[QuantityStats]:
        if not self.use_cache or not self._stats_path().exists():
            return None
        try:
            c = json.loads(self._stats_path().read_text())
            e = c.get("v") == STATS_VERSION and c["entries"].get(key)
            if e and e["fp"] == self._fingerprint(leaves):
                return QuantityStats(**e["stats"])
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _save_stats(self, key: str, leaves: Sequence[NavNode], stats: QuantityStats) -> None:
        if not self.use_cache:
            return
        try:
            c = json.loads(self._stats_path().read_text()) if self._stats_path().exists() else {}
            if c.get("v") != STATS_VERSION:
                c = {"v": STATS_VERSION, "entries": {}}
            c["entries"][key] = {"fp": self._fingerprint(leaves), "stats": stats.__dict__}
            self._stats_path().write_text(json.dumps(c))
        except OSError:
            pass

    def colorbar(self, quantity: str, units: str, leaves: Sequence[NavNode]) -> cb.ColorbarModel:
        """The colorbar for *quantity* in the user's display units (range from the stats and the range mode)."""
        props = self.viz.fds.colorbar(quantity)
        st = self.stats(quantity, leaves)
        conv = lambda v: float(un.convert(np.array([v]), units, self.viz.units)[0][0])
        scaled = QuantityStats(conv(st.min), conv(st.max), conv(st.p1), conv(st.p99), st.n)
        lo, hi = cb.data_range(props, scaled)
        return cb.ColorbarModel(props, lo, hi)

    # -- errors -----------------------------------------------------------------------------------------
    def errors(self) -> Dict[str, List[me.ErrorSample]]:
        if self._errors is None:
            self._errors = me.read_max_errors(str(self.run.directory / (self.run.chid + ".out")))
        return self._errors

    # -- the primitives ---------------------------------------------------------------------------------------
    def primitives(self, leaf: NavNode, t: float) -> List[object]:
        """Shapes for *leaf* at global time *t* (the run's time offset is removed first)."""
        t_fds = t - self.offset
        fn = {"geometry": self._geometry, "slice2d": self._slice2d, "slice3d": self._slice3d,
              "smoke3d": self._smoke, "plot3d": self._plot3d, "isosurface": self._iso, "boundary": self._boundary,
              "particles": self._particles, "slice_vectors": self._vectors, "max_error": self._max_error}.get(leaf.kind)
        if fn is None:
            return []
        return fn(leaf, t_fds)

    def _convert(self, values: np.ndarray, units: str) -> Tuple[np.ndarray, str]:
        return un.convert(values, units, self.viz.units)

    # geometry
    def _geometry(self, leaf: NavNode, t: float) -> List[object]:
        which = leaf.id.split("/")[-1]
        if which == "fds_actual":
            seen, boxes, labels = set(), [], []
            for o in self.run.obstructions:
                key = (tuple(round(v, 6) for v in o.xb), o.name)
                if key not in seen:
                    seen.add(key)
                    boxes.append(o.xb)
                    labels.append(o.name)
            out: List[object] = [GeometryBoxes("Obstructions", boxes, labels, kind="obstruction")]
            ext = [m.extents for m in self.run.meshes]

            def on_boundary(xb) -> bool:          # a flat face lying on the outside of a mesh: an open boundary
                for e in ext:
                    for ax in range(3):
                        if xb[2 * ax] == xb[2 * ax + 1] and (abs(xb[2 * ax] - e[2 * ax]) < 1e-6 or abs(xb[2 * ax] - e[2 * ax + 1]) < 1e-6):
                            return True
                return False

            vents = [v.xb for v in self.run.vents]
            out.append(GeometryBoxes("Vents", [x for x in vents if not on_boundary(x)], kind="vent"))
            out.append(GeometryBoxes("Open boundaries", [x for x in vents if on_boundary(x)], kind="open_vent"))
            out.append(GeometryBoxes("Meshes", [m.extents for m in self.run.meshes], kind="mesh"))
            return out
        if which == "fds_requested" and self.requested_geometry is not None:
            return [self.requested_geometry()]
        if which == "pyfds_geometry" and self.model_geometry is not None:
            return [self.model_geometry()]
        return []

    # slices
    def _slice_info(self, leaf: NavNode) -> SliceFile:
        for s in self.run.slices:
            if s.file == leaf.files[0]:
                return s
        raise KeyError(leaf.files[0])

    def _slice_frame(self, s: SliceStream, t: float) -> np.ndarray:
        return self._blend(s.frame, s.times, t)

    def _slice2d(self, leaf: NavNode, t: float) -> List[object]:
        info = self._slice_info(leaf)
        s = self.stream("slice", leaf.files[0])
        data, units = self._convert(self._slice_frame(s, t), leaf.units)
        xs, ys, zs = self.run.slice_coords(info)
        axes = [xs, ys, zs]
        shape = data.shape
        d = [n == 1 for n in shape].index(True) if any(n == 1 for n in shape) else info.idir - 1
        keep = [a for a in range(3) if a != d]
        A, B = np.meshgrid(axes[keep[0]], axes[keep[1]], indexing="ij")
        coords: List[Optional[np.ndarray]] = [None, None, None]
        coords[keep[0]], coords[keep[1]], coords[d] = A, B, np.full_like(A, float(axes[d][0]))
        vals = np.squeeze(data, axis=d) if data.shape[d] == 1 else data.take(0, axis=d)
        return [GridSurface(leaf.label, leaf.quantity, units, coords[0], coords[1], coords[2], vals.astype(float),
                            "xyz"[d], float(axes[d][0]))]

    def _slice3d(self, leaf: NavNode, t: float) -> List[object]:
        info = self._slice_info(leaf)
        s = self.stream("slice", leaf.files[0])
        data, units = self._convert(self._slice_frame(s, t), leaf.units)
        xs, ys, zs = self.run.slice_coords(info)
        return [RectilinearVolume(leaf.label, leaf.quantity, units, xs, ys, zs, data.astype(float))]

    def _vectors(self, leaf: NavNode, t: float) -> List[object]:
        infos = [next(s for s in self.run.slices if s.file == f) for f in leaf.files]
        comps = [self._slice_frame(self.stream("slice", f), t) for f in leaf.files]
        xs, ys, zs = self.run.slice_coords(infos[0])
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
        vec = np.column_stack([c.ravel() for c in comps]).astype(float)
        return [VectorField(leaf.label, "VELOCITY", "m/s", pts, vec, np.linalg.norm(vec, axis=1))]

    # boundaries
    def _boundary(self, leaf: NavNode, t: float) -> List[object]:
        s: BoundaryStream = self.stream("boundary", leaf.files[0])
        mesh = self.run.mesh(leaf.mesh)
        k0, k1, a = self._pick(s.times, t)
        f0 = s.frame(k0)
        f1 = s.frame(k1) if k1 is not None else None
        out = []
        for p, patch in enumerate(s.patches):
            vals = f0[p] if f1 is None else (1 - a) * f0[p] + a * f1[p]
            vals, units = self._convert(vals, leaf.units)
            i1, i2, j1, j2, k_1, k_2 = patch[:6]
            idx = [(i1, i2), (j1, j2), (k_1, k_2)]
            shape = tuple(hi - lo + 1 for lo, hi in idx)
            singles = [n == 1 for n in shape]
            if sum(singles) != 1 or vals.size != int(np.prod(shape)):
                continue
            d = singles.index(True)
            axes = []
            for a_ in range(3):
                nodes = mesh.node_coords(a_)
                axes.append(nodes[np.clip(np.arange(idx[a_][0], idx[a_][1] + 1), 0, len(nodes) - 1)])
            keep = [x for x in range(3) if x != d]
            A, B = np.meshgrid(axes[keep[0]], axes[keep[1]], indexing="ij")
            coords: List[Optional[np.ndarray]] = [None, None, None]
            coords[keep[0]], coords[keep[1]], coords[d] = A, B, np.full_like(A, float(axes[d][0]))
            v2 = np.squeeze(vals.reshape(shape, order="F"), axis=d)
            out.append(GridSurface(leaf.label, leaf.quantity, units, coords[0], coords[1], coords[2], v2.astype(float),
                                   "xyz"[d], float(axes[d][0])))
        return out

    # smoke / fire / plot3d
    def _smoke_values(self, leaf: NavNode, raw: np.ndarray) -> Tuple[str, np.ndarray]:
        q = leaf.quantity.upper()
        if q == "HRRPUV":
            return "fire", raw.astype(np.float32) / 255.0 * self.run.hrrpuv_range[1]
        if q == "SOOT DENSITY":
            return "smoke", raw.astype(np.float32)           # 0..255 = 255 * (1 - exp(-kappa rho dx)); see extinction()
        lo, hi = self.run.temp_range
        return "scalar", lo + raw.astype(np.float32) / 255.0 * (hi - lo)     # approximate: 8-bit over the run's range

    def _smoke(self, leaf: NavNode, t: float) -> List[object]:
        s: Smoke3DStream = self.stream("smoke3d", leaf.files[0])
        mesh = self.run.mesh(leaf.mesh)
        k0, k1, a = self._pick(s.times, t)
        raw0 = s.frame_bytes(k0).astype(np.float32)
        raw = raw0 if k1 is None else (1 - a) * raw0 + a * s.frame_bytes(k1).astype(np.float32)
        kind, vals = self._smoke_values(leaf, raw)
        x, y, z = (mesh.node_coords(i) for i in range(3))
        ext = None
        if kind == "smoke":
            dx = (np.mean(np.diff(x)) + np.mean(np.diff(y)) + np.mean(np.diff(z))) / 3.0
            frac = np.clip(raw / 255.0, 0.0, 0.999)
            ext = -np.log1p(-frac) / dx
        return [RectilinearVolume(leaf.label, leaf.quantity, leaf.units, x, y, z, vals.astype(float), kind, ext)]

    def _plot3d(self, leaf: NavNode, t: float) -> List[object]:
        times = self.leaf_times(leaf)
        names = {p.time: p.file for p in self.run.plot3d if p.file in leaf.files}
        ts = sorted(names)
        k = int(np.clip(np.searchsorted(ts, t + 1e-9) - 1, 0, len(ts) - 1))
        data = self.stream("plot3d", names[ts[k]]).data()[leaf.data["index"]]
        data, units = self._convert(data, leaf.units)
        mesh = self.run.mesh(leaf.mesh)
        x, y, z = (mesh.node_coords(i) for i in range(3))
        return [RectilinearVolume(leaf.label, leaf.quantity, units, x, y, z, data.astype(float))]

    # isosurfaces / particles / errors
    def _iso(self, leaf: NavNode, t: float) -> List[object]:
        s: IsoStream = self.stream("isosurface", leaf.files[0])
        k = int(np.clip(np.searchsorted(s.times, t + 1e-9) - 1, 0, s.n_frames - 1))
        out = []
        for level, (v, tri) in zip(s.levels, s.frame(k)):
            if len(v) and len(tri):
                out.append(TriMesh(leaf.label, leaf.quantity, leaf.units, v, tri, None, level))
        return out

    def _particles(self, leaf: NavNode, t: float) -> List[object]:
        s: ParticleStream = self.stream("particles", leaf.files[0])
        ci = int(leaf.data.get("class_index", 0))
        k = int(np.clip(np.searchsorted(s.times, t + 1e-9) - 1, 0, max(s.n_frames - 1, 0)))
        if s.n_frames == 0 or ci >= s.n_classes:
            return []
        frame = s.frame(k)[ci]
        props = self.viz.particles.get(str(leaf.data.get("class")))
        values = None
        units = ""
        if props and props.color != "default":
            names = [q[0] for q in s.quantities[ci]]
            if props.color in names:
                j = names.index(props.color)
                values = frame["values"][:, j]
                units = s.quantities[ci][j][1]
        rgb = next((c.color for c in self.run.particle_classes if c.name == leaf.data.get("class")), (0.0, 0.0, 1.0))
        pc = PointCloud(leaf.label, props.color if props else "", units, frame["positions"], values,
                        props.size if props else 3.0)
        pc.__dict__["class_color"] = rgb
        return [pc]

    def _max_error(self, leaf: NavNode, t: float) -> List[object]:
        smp = me.at_time(self.errors()[leaf.data["which"]], t)
        if smp is None:
            return []
        box = me.cell_box(self.run.mesh(smp.mesh), smp.cell)
        return [ErrorBoxes(leaf.label, [box], [smp.value])]
