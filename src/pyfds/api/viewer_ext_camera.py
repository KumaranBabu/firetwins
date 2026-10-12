"""ViewerExtras: camera, views and view files."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from pyfds.results.viz import model as vm
from pyfds.results.viz import views as vw


class ViewerExtrasCameraMixin:
    # -- camera and standard views ---------------------------------------------------------------------------
    @property
    def camera(self) -> vm.Viewpoint:
        return self.viz.camera

    def set_camera(self, vp: vm.Viewpoint) -> None:
        self.viz.camera = copy.deepcopy(vp)
        self.dirty = True

    def set_projection(self, projection: str) -> None:
        """Perspective ⇄ Orthogonal (the viewpoint is kept)."""
        if projection not in ("perspective", "orthogonal"):
            raise ValueError("projection must be perspective or orthogonal")
        self.viz.camera.projection = projection
        self.dirty = True

    def set_navigation(self, tool: str) -> None:
        if tool not in ("orbit", "pan", "zoom", "roam", "smokeview"):
            raise ValueError("navigation tool must be orbit, pan, zoom, roam or smokeview")
        if tool == "roam" and self.viz.camera.projection == "orthogonal":
            raise ValueError("the roam tool cannot be used with the orthogonal view")
        self.viz.camera.navigation = tool
        self.dirty = True

    def standard_view(self, name: str) -> vm.Viewpoint:
        """Top, Front or Side (left) of the model (``Reset Camera`` = isometric), looking at its centre."""
        b = self.run.bounds() if self.run else (0, 1, 0, 1, 0, 1)
        c = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
        d = float(np.linalg.norm([b[1] - b[0], b[3] - b[2], b[5] - b[4]])) * 1.3 + 1e-6
        views = {"top": ((0, 0, d), (0, 1, 0)), "front": ((0, -d, 0), (0, 0, 1)), "side": ((-d, 0, 0), (0, 0, 1)),
                 "isometric": ((d * 0.7, -d * 0.7, d * 0.5), (0, 0, 1))}
        if name not in views:
            raise ValueError(f"view must be one of {', '.join(views)}")
        off, up = views[name]
        vp = copy.deepcopy(self.viz.camera)
        vp.position, vp.target, vp.up = tuple(c + o for c, o in zip(c, off)), tuple(c), up      # type: ignore
        self.viz.camera = vp
        self.dirty = True
        return vp

    def reset_camera(self) -> vm.Viewpoint:
        return self.standard_view("isometric")

    # -- geometry set and rendering mode --------------------------------------------------------------------------
    def set_geometry_set(self, name: str) -> None:
        if name not in vm.GEOMETRY_SETS:
            raise ValueError(f"geometry set must be one of {', '.join(vm.GEOMETRY_SETS)}")
        node = self.tree.find(f"geometry/{name}")
        if node is None:
            raise KeyError(f"this run has no {name} geometry")
        self.activation.activate(node.id)
        self.viz.geometry_set = name
        self.dirty = True

    def set_rendering_mode(self, mode: str) -> None:
        if mode not in vm.RENDER_MODES:
            raise ValueError(f"rendering mode must be one of {', '.join(vm.RENDER_MODES)}")
        self.viz.rendering_mode = mode
        self.dirty = True

    # -- views, tours, section boxes -------------------------------------------------------------------------------
    def new_view(self, name: Optional[str] = None) -> vm.View:
        v = vw.new_view(self.viz, name, self.viz.camera, vw.active_section(self.viz))
        self._views_changed()
        return v

    def new_tour(self, name: Optional[str] = None) -> vm.View:
        v = vw.new_tour(self.viz, name, vw.active_section(self.viz))
        self._views_changed()
        return v

    def activate_view(self, name: Optional[str]) -> Optional[vm.View]:
        v = vw.activate(self.viz, name)
        self._views_changed(rebuild=False)
        return v

    def save_viewpoint(self, name: Optional[str] = None) -> None:
        vw.save_viewpoint(self.viz, name or self.viz.active_view or "")
        self.dirty = True

    def delete_view(self, name: str) -> None:
        vw.delete_view(self.viz, name)
        self._views_changed()

    def duplicate_views(self, names: Sequence[str]) -> List[vm.View]:
        out = vw.duplicate_views(self.viz, names)
        self._views_changed()
        return out

    def _views_changed(self, rebuild: bool = True) -> None:
        self.dirty = True
        if rebuild:
            self._rebuild()
        self._playback = None

    def import_views(self, path: str) -> List[vm.View]:
        """File ▸ Import ▸ Import Views (from a views file or another visualization)."""
        out = vw.import_views(self.viz, Path(path).read_text(encoding="utf-8"))
        self._views_changed()
        return out

    def export_views(self, path: str) -> str:
        Path(path).write_text(vw.export_views(self.viz), encoding="utf-8")
        return path

    def camera_for_time(self, t: Optional[float] = None) -> vm.Viewpoint:
        tour = vw.active_tour(self.viz)
        return vw.camera_at(tour, self.time if t is None else t) if tour and tour.keyframes else copy.deepcopy(self.viz.camera)
