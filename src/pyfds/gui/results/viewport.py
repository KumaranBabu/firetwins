"""The results 3D view: a ``QtInteractor`` on a desktop, a plain label under Qt's offscreen platform.

Either way ``self.plotter`` is a usable ``pyvista.Plotter`` (off-screen when there is no interactor), so the
scene can always be drawn and saved to an image; only live mouse navigation needs the interactor.
"""
from __future__ import annotations

from typing import Callable, Optional

import pyvista as pv
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .scene_adapter import SceneAdapter, make_offscreen_renderer


class ResultsViewport(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        app = QApplication.instance()
        self.interactive = bool(app) and app.platformName() not in ("offscreen", "minimal")
        if self.interactive:
            from pyvistaqt import QtInteractor
            self.plotter = QtInteractor(self)
            lay.addWidget(self.plotter.interactor)
        else:
            self.plotter = pv.Plotter(off_screen=True, window_size=(800, 500))
            lay.addWidget(QLabel("3D view needs a desktop display"))
        self.adapter = SceneAdapter(self.plotter)
        self.on_click: Optional[Callable[[int, int], None]] = None      # called with the display point of a click that did not drag
        self._press: Optional[tuple] = None
        if self.interactive:
            iren = self.plotter.iren
            iren.add_observer("LeftButtonPressEvent", self._pressed)
            iren.add_observer("LeftButtonReleaseEvent", self._released)

    def _pressed(self, *_a) -> None:
        self._press = tuple(self.plotter.iren.interactor.GetEventPosition())

    def _released(self, *_a) -> None:
        start, self._press = self._press, None
        end = tuple(self.plotter.iren.interactor.GetEventPosition())
        if start is not None and self.on_click and abs(end[0] - start[0]) <= 3 and abs(end[1] - start[1]) <= 3:
            self.on_click(*end)               # a click, not an orbit/pan drag

    def shutdown(self) -> None:
        try:
            self.plotter.close()
        except Exception:
            pass

    def make_renderer(self, viewer):
        return make_offscreen_renderer(viewer)
