"""ResultsDataset: drawable primitives for each result kind."""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from . import max_errors as me
from . import units as un
from .fds_run import SliceFile
from .primitives import (
    ErrorBoxes,
    GeometryBoxes,
    GridSurface,
    PointCloud,
    RectilinearVolume,
    TriMesh,
    VectorField,
)
from .streams import BoundaryStream, IsoStream, ParticleStream, SliceStream, Smoke3DStream
from .tree import NavNode


class ResultsDatasetPrimitivesMixin:
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
