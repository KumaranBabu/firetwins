"""Draws a tool's preview (rubber-band boxes and lines) into the plotter (plan step F2). Thin VTK glue: what to draw
comes from ``Tool.preview()``, which is tested without a display."""
from __future__ import annotations

from typing import Any, List

import pyvista as pv

_PREVIEW_COLOR = "#ffd24a"
_NAME = "pyfds_preview_"


class PreviewLayer:
    def __init__(self, plotter) -> None:
        self.plotter = plotter
        self._names: List[str] = []

    def clear(self) -> None:
        for name in self._names:
            try:
                self.plotter.remove_actor(name, render=False)
            except Exception:
                pass
        self._names = []

    def show(self, preview: Any) -> None:
        """Replace whatever is drawn with *preview* (a ``Preview``). Never pickable, so it cannot block a click."""
        self.clear()
        for i, b in enumerate(preview.boxes):
            lo, hi = list(b[0::2]), list(b[1::2])
            for k in range(3):                           # flat boxes (a vent) get a hair of thickness
                if hi[k] - lo[k] < 1e-3:
                    hi[k] = lo[k] + 1e-3
            box = pv.Box(bounds=(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
            name = f"{_NAME}box{i}"
            self.plotter.add_mesh(box, color=_PREVIEW_COLOR, opacity=0.35, name=name, pickable=False, render=False)
            self._names.append(name)
            edge = f"{_NAME}edge{i}"
            self.plotter.add_mesh(box, color=_PREVIEW_COLOR, style="wireframe", line_width=2, name=edge,
                                  pickable=False, render=False)
            self._names.append(edge)
        for j, line in enumerate(preview.polylines):
            if len(line) >= 2:
                name = f"{_NAME}line{j}"
                self.plotter.add_mesh(pv.lines_from_points([tuple(p) for p in line]), color=_PREVIEW_COLOR,
                                      line_width=3, name=name, pickable=False, render=False)
                self._names.append(name)
        self.plotter.render()
