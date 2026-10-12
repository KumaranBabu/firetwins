"""Time-history plot dialog: CSV columns and Data3D points on one chart (Tools ▸ Time History)."""
from __future__ import annotations

from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout,
                               QWidget)


class TimePlotDialog(QDialog):
    def __init__(self, viewer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setWindowTitle("Time History")
        self.resize(900, 520)
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setMaximumWidth(280)
        left = QVBoxLayout()
        self.kind = QComboBox()                      # View > Plot Type
        self.kind.addItems(["Line", "Stem", "Step"])
        self.kind.currentIndexChanged.connect(lambda _i: self.replot())
        left.addWidget(self.kind)
        left.addWidget(self.list)
        lay.addLayout(left)
        QShortcut(QKeySequence("F11"), self, activated=self.save_image)   # File > Save Screenshot
        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasQTAgg(self.fig)
        lay.addWidget(self.canvas, 1)
        for sid in viewer.csv_series():
            it = QListWidgetItem(sid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.list.addItem(it)
        self.list.itemChanged.connect(lambda _i: self.replot())

    def checked(self):
        return [self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked]

    def replot(self) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        for s in self.viewer.time_history(self.checked()):
            label = f"{s.label} ({s.unit})" if s.unit else s.label
            kind = self.kind.currentText()
            if kind == "Stem":
                ax.stem(s.times, s.values, label=label)
            elif kind == "Step":
                ax.step(s.times, s.values, where="post", label=label)
            else:
                ax.plot(s.times, s.values, label=label)
        ax.axvline(self.viewer.time, color="grey", lw=0.8, ls="--")
        ax.set_xlabel("Time (s)")
        ax.grid(True, alpha=0.3)
        if self.checked():
            ax.legend(fontsize=8)
        self.canvas.draw_idle()

    def save_image(self, path: str = "") -> str:
        """Save the plot as an image (F11). Without *path* a file dialog asks for one."""
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save Plot", "plot.png", "PNG (*.png);;PDF (*.pdf)")
        if path:
            self.fig.savefig(path, dpi=150)
        return path
