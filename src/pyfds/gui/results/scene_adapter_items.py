"""SceneAdapter: drawing the primitives (scalars, volumes)."""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pyvista as pv

from pyfds.api.viz import model as vm
from pyfds.api.viz import (
    ErrorBoxes,
    GeometryBoxes,
    GridSurface,
    PointCloud,
    RectilinearVolume,
    TriMesh,
    VectorField,
)
from .quality import volume_mapper

from .scene_adapter_common import _box_mesh, _lut


class SceneAdapterItemsMixin:
    def _draw_one(self, node, prim, bars: Dict[str, Any], viz: vm.ResultsVisualization) -> int:
        pl = self.pl
        mode = viz.rendering_mode
        wire = mode == "wireframe"
        if isinstance(prim, GeometryBoxes):
            mesh = _box_mesh(prim.boxes)
            if mesh is None:
                return 0
            if prim.kind == "mesh":                      # a computational mesh is only an outline, never a solid
                pl.add_mesh(mesh, color="#5c6b7a", style="wireframe", line_width=1, pickable=False, name=f"{node.id}#{prim.kind}")
                return 1
            if prim.kind == "open_vent":                 # the open sides of the domain: a faint outline, so the room stays visible
                pl.add_mesh(mesh, color="#c97b3a", style="wireframe", line_width=1, opacity=0.5, pickable=False,
                            name=f"{node.id}#{prim.kind}")
                return 1
            if prim.kind == "vent":
                pl.add_mesh(mesh, color="#c97b3a", style="wireframe" if wire else "surface", opacity=0.6, name=f"{node.id}#{prim.kind}")
                return 1
            pl.add_mesh(mesh, color="#9aa4b2", style="wireframe" if wire else "surface",
                        show_edges=mode.endswith("outlines") or wire, edge_color="#222222", opacity=1.0, name=f"{node.id}#{prim.kind}")
            return 1
        if isinstance(prim, ErrorBoxes):
            mesh = _box_mesh(prim.boxes)
            if mesh is not None:
                pl.add_mesh(mesh, color="red", style="wireframe", line_width=2, name=node.id)
                return 1
            return 0
        bar = bars.get(getattr(prim, "quantity", ""))
        if isinstance(prim, GridSurface):
            grid = pv.StructuredGrid(prim.x, prim.y, prim.z)
            grid["v"] = prim.values.ravel(order="F")
            self._add_scalar(grid, bar, node.id)
            return 1
        if isinstance(prim, TriMesh):
            if len(prim.faces) == 0:
                return 0
            mesh = pv.PolyData(prim.vertices, np.column_stack([np.full(len(prim.faces), 3), prim.faces]).ravel())
            if prim.values is not None and bar is not None:
                mesh["v"] = prim.values
                self._add_scalar(mesh, bar, node.id)
            else:
                pl.add_mesh(mesh, color="#e0b040", opacity=0.6, smooth_shading=True, name=node.id)
            return 1
        if isinstance(prim, PointCloud):
            cloud = pv.PolyData(prim.points)
            if prim.values is not None and bar is not None:
                cloud["v"] = prim.values
                actor = pl.add_mesh(cloud, scalars="v", point_size=max(prim.diameter, 3.0) if prim.diameter > 1 else 4.0,
                                    render_points_as_spheres=True, show_scalar_bar=False, name=node.id)
                actor.mapper.lookup_table = _lut(bar)
                actor.mapper.scalar_range = (bar.lo, bar.hi)
            else:
                pl.add_mesh(cloud, color="#6cc6ff", point_size=4.0, render_points_as_spheres=True, name=node.id)
            return 1
        if isinstance(prim, VectorField):
            if len(prim.points) == 0:
                return 0
            cloud = pv.PolyData(prim.points)
            cloud["vec"] = prim.vectors
            speed = np.linalg.norm(prim.vectors, axis=1)
            cloud["v"] = prim.values if prim.values is not None else speed
            scale = float(np.nanmax(speed)) or 1.0
            arrows = cloud.glyph(orient="vec", scale=False, factor=0.15 * max(viz.slice_vectors.get(node.quantity + "|" + node.label,
                                 vm.SliceVectorProps()).factor, 1e-6))
            if arrows.n_points:
                self._add_scalar(arrows, bar, node.id, array="v", fallback=cloud["v"])
            return 1
        if isinstance(prim, RectilinearVolume):
            return self._volume(node, prim, bar, viz)
        return 0

    def _add_scalar(self, mesh, bar, name: str, array: str = "v", fallback=None) -> None:
        if bar is None:
            self.pl.add_mesh(mesh, color="#c0c0c0", name=name)
            return
        if array not in mesh.array_names and fallback is not None:
            mesh[array] = np.resize(fallback, mesh.n_points)
        actor = self.pl.add_mesh(mesh, scalars=array, show_scalar_bar=False, nan_opacity=0.0, name=name,
                                 show_edges=False, interpolate_before_map=not self._flat)
        actor.mapper.lookup_table = _lut(bar)
        actor.mapper.scalar_range = (bar.lo, bar.hi)

    def _volume(self, node, vol: RectilinearVolume, bar, viz: vm.ResultsVisualization) -> int:
        grid = pv.RectilinearGrid(vol.x, vol.y, vol.z)
        sp = viz.smoke3d
        mapper = "fixed_point" if self.fast_volumes else volume_mapper(viz.rendering)
        compat = mapper == "fixed_point"
        if vol.kind == "smoke" and vol.extinction is not None:
            dx = vol.cell_size()
            alpha = (1.0 - np.exp(-vol.extinction * sp.smoke_opacity * sp.smoke_brightness * dx * 2.0))
            grid["a"] = np.clip(alpha, 0, 1).ravel(order="F")
            grid = self._uniform(grid, vol) if compat else grid
            self.pl.add_volume(grid, scalars="a", cmap="gray_r", opacity="linear", clim=(0, 1), show_scalar_bar=False,
                               name=node.id, shade=False, mapper=mapper)
            self._jitter(node.id, viz)
            return 1
        if vol.kind == "fire":
            grid["h"] = vol.values.ravel(order="F")
            hi = float(np.nanmax(vol.values)) or 1.0
            grid = self._uniform(grid, vol) if compat else grid
            self.pl.add_volume(grid, scalars="h", cmap="hot", opacity="linear", clim=(0, hi * sp.fire_brightness or hi),
                               show_scalar_bar=False, name=node.id, shade=False, mapper=mapper)
            self._jitter(node.id, viz)
            return 1
        # plain scalar volume: shown as its outline plus a mid-plane so something readable is there
        grid["v"] = vol.values.ravel(order="F")
        self.pl.add_mesh(grid.outline(), color="#777777", name=node.id + "/outline")
        if bar is not None:
            mid = grid.slice(normal="y", origin=[(vol.x[0] + vol.x[-1]) / 2, (vol.y[0] + vol.y[-1]) / 2, (vol.z[0] + vol.z[-1]) / 2])
            if mid.n_points:
                self._add_scalar(mid, bar, node.id, array="v")
        return 1

    @staticmethod
    def _uniform(grid, vol: RectilinearVolume):
        """The software volume mapper needs a uniform grid: resample at the finest cell size."""
        h = min(float(np.diff(a).min()) for a in (vol.x, vol.y, vol.z) if len(a) > 1)
        dims = [max(int(round((a[-1] - a[0]) / h)) + 1, 2) for a in (vol.x, vol.y, vol.z)]
        img = pv.ImageData(dimensions=dims, spacing=(h, h, h), origin=(vol.x[0], vol.y[0], vol.z[0]))
        return img.sample(grid)
