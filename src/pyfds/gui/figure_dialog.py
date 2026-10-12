"""
Read-only matplotlib figure viewer dialog — used for the Results >
View Time History plot (and any future plot dialog).

``FigureCanvasQTAgg`` renders to an Agg raster buffer and blits via
QPainter — no real OpenGL context involved, unlike ``pyvistaqt.QtInteractor``
(see viewport_3d.py) — so unlike that widget, this one is safe to construct
under Qt's offscreen platform and is covered by the automated test suite.
"""
from __future__ import annotations

from typing import Any, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget


class FigureDialog(QDialog):
    def __init__(self, title: str, figure: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 520)

        canvas = FigureCanvasQTAgg(figure)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(canvas)
        layout.addWidget(buttons)
