"""ViewerManager: Data3D points, slices and isosurfaces."""
from __future__ import annotations

from typing import Any, List, Sequence

import numpy as np

from pyfds.results.viz import data3d as d3
from pyfds.results.viz import model as vm
from pyfds.results.viz.primitives import PointCloud
from pyfds.results.viz.tree import NavNode


class ViewerManagerData3DMixin:
    # -- Data3D objects ---------------------------------------------------------------------------------------
    def _group_leaves(self, group_id: str) -> List[NavNode]:
        g = self.node(group_id)
        leaves = [l for l in g.leaves() if l.kind in ("slice3d", "plot3d")]
        if not leaves:
            raise ValueError("Data3D objects are made from a 3D Slices or Plot3D quantity")
        return leaves

    def _next_id(self, prefix: str, items: Sequence[Any]) -> str:
        n = 1
        names = {o.id for o in items}
        while f"{prefix} {n}" in names:
            n += 1
        return f"{prefix} {n}"

    def add_data3d_point(self, group_id: str, xyz: Sequence[float]) -> vm.Data3DPoint:
        leaves = self._group_leaves(group_id)
        t = float(self.timeline()[0]) if len(self.timeline()) else self.run.times[0]
        vols = [v for l in leaves for v in self.dataset.primitives(l, t)]
        if not any(d3.inside(v, xyz) for v in vols):
            raise ValueError("the point must be inside one of the regions of this quantity")
        o = vm.Data3DPoint(self._next_id("Point", self.viz.data3d_points), group_id, leaves[0].quantity,
                           tuple(float(c) for c in xyz))                        # type: ignore[arg-type]
        self.viz.data3d_points.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def add_data3d_slice(self, group_id: str, origin: Sequence[float], normal: Sequence[float]) -> vm.Data3DSlice:
        leaves = self._group_leaves(group_id)
        if np.linalg.norm(normal) == 0:
            raise ValueError("the plane normal must not be zero")
        o = vm.Data3DSlice(self._next_id("Slice", self.viz.data3d_slices), group_id, leaves[0].quantity,
                           tuple(float(c) for c in origin), tuple(float(c) for c in normal))   # type: ignore[arg-type]
        self.viz.data3d_slices.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def add_data3d_isosurface(self, group_id: str, value: float) -> vm.Data3DIso:
        leaves = self._group_leaves(group_id)
        o = vm.Data3DIso(self._next_id("Isosurface", self.viz.data3d_isos), group_id, leaves[0].quantity, float(value))
        self.viz.data3d_isos.append(o)
        self._rebuild()
        self.dirty = True
        return o

    def remove_data3d(self, obj_id: str) -> None:
        for lst in (self.viz.data3d_points, self.viz.data3d_slices, self.viz.data3d_isos):
            for o in lst:
                if o.id == obj_id:
                    lst.remove(o)
                    self.viz.active = [a for a in self.viz.active if not a.endswith("/" + obj_id)]
                    self._rebuild()
                    self.dirty = True
                    return
        raise KeyError(f"no Data3D object {obj_id!r}")

    def _find_data3d(self, leaf: NavNode):
        oid = leaf.data["obj_id"]
        for o in self.viz.data3d_points + self.viz.data3d_slices + self.viz.data3d_isos:
            if o.id == oid:
                return o
        raise KeyError(oid)

    def _data3d_primitives(self, leaf: NavNode, t: float) -> List[Any]:
        o = self._find_data3d(leaf)
        vols = [v for l in self._group_leaves(o.group) for v in self.dataset.primitives(l, t)]
        out: List[Any] = []
        if leaf.kind == "data3d_point":
            vals = [d3.sample_point(v, o.xyz) for v in vols if d3.inside(v, o.xyz)]
            if vals:
                out.append(PointCloud(o.id, o.quantity, vols[0].units, np.array([o.xyz]), np.array([vals[0]]), 8.0))
        elif leaf.kind == "data3d_slice":
            for v in vols:
                s = d3.slice_plane(v, o.origin, o.normal)
                if s is not None:
                    out.append(s)
        else:
            for v in vols:
                m = d3.isosurface(v, o.value)
                if len(m.faces):
                    out.append(m)
        return out
