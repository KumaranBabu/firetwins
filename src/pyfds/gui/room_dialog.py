"""Draw > Room: four walls, optional floor/ceiling, doors and windows from one dialog."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


def _spin(value: float, lo: float = -1000.0, hi: float = 1000.0, step: float = 0.05, decimals: int = 3) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(" m")
    return s


class RoomDialog(QDialog):
    """Collects the arguments of the ``add_room`` tool."""

    _COLS = ["Wall", "Centre (m)", "Width (m)", "Height (m)", "Sill (m)"]

    def __init__(self, surfaces: List[str], parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Draw Room")
        self.setMinimumWidth(600)
        root = QVBoxLayout(self)
        intro = QLabel("Four walls round a rectangle, with an optional floor and ceiling, plus doors and "
                       "windows cut through the walls. One undo step removes the whole room.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        shape = QGroupBox("Footprint (plan view, metres)")
        form = QFormLayout(shape)
        self.x0, self.x1 = _spin(0.6), _spin(5.4)
        self.y0, self.y1 = _spin(0.6), _spin(3.9)
        self.z0 = _spin(0.0)
        row = QHBoxLayout(); row.addWidget(self.x0); row.addWidget(QLabel("to")); row.addWidget(self.x1)
        form.addRow("X from / to", row)
        row = QHBoxLayout(); row.addWidget(self.y0); row.addWidget(QLabel("to")); row.addWidget(self.y1)
        form.addRow("Y from / to", row)
        form.addRow("Floor level (Z)", self.z0)
        root.addWidget(shape)

        build = QGroupBox("Construction")
        bf = QFormLayout(build)
        self.height = _spin(2.4, 0.1)
        self.wall = _spin(0.15, 0.01, 5.0, 0.01)
        self.position = QComboBox(); self.position.addItems(["inside", "centre", "outside"])
        self.floor = _spin(0.0, 0.0, 5.0, 0.05)
        self.ceiling = _spin(0.15, 0.0, 5.0, 0.05)
        self.surface = QComboBox(); self.surface.setEditable(True)
        self.surface.addItems(surfaces or ["INERT"])
        bf.addRow("Room height", self.height)
        bf.addRow("Wall thickness", self.wall)
        bf.addRow("Walls sit", self.position)
        bf.addRow("Floor thickness (0 = none)", self.floor)
        bf.addRow("Ceiling thickness (0 = none)", self.ceiling)
        bf.addRow("Wall surface", self.surface)
        root.addWidget(build)

        op = QGroupBox("Doors and windows")
        ol = QVBoxLayout(op)
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(self._COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(120)
        self.table.setToolTip("Wall: S, E, N or W. Centre: distance along the wall. Sill: height of the bottom edge.")
        ol.addWidget(self.table)
        b = QHBoxLayout()
        add_door = QPushButton("Add door"); add_door.clicked.connect(lambda: self._add_row("S", 3.0, 0.9, 2.1, 0.0))
        add_win = QPushButton("Add window"); add_win.clicked.connect(lambda: self._add_row("E", 2.25, 1.2, 1.05, 0.9))
        rem = QPushButton("Remove selected"); rem.clicked.connect(self._remove_row)
        for w in (add_door, add_win, rem):
            b.addWidget(w)
        b.addStretch(1)
        ol.addLayout(b)
        root.addWidget(op)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_row(self, side: str, centre: float, width: float, height: float, sill: float) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate((side, centre, width, height, sill)):
            self.table.setItem(r, c, QTableWidgetItem(str(v)))

    def _remove_row(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def openings(self) -> List[Dict[str, Any]]:
        out = []
        for r in range(self.table.rowCount()):
            cell = lambda c: self.table.item(r, c).text().strip()
            side = cell(0).upper()
            if side not in ("S", "E", "N", "W"):
                raise ValueError(f"row {r + 1}: wall must be S, E, N or W")
            try:
                out.append({"side": side, "centre": float(cell(1)), "width": float(cell(2)),
                            "height": float(cell(3)), "sill": float(cell(4))})
            except ValueError:
                raise ValueError(f"row {r + 1}: centre, width, height and sill must be numbers") from None
        return out

    def values(self) -> Dict[str, Any]:
        v: Dict[str, Any] = {
            "xb": [self.x0.value(), self.x1.value(), self.y0.value(), self.y1.value()],
            "height": self.height.value(), "wall_thickness": self.wall.value(), "z": self.z0.value(),
            "position": self.position.currentText(), "floor_thickness": self.floor.value(),
            "ceiling_thickness": self.ceiling.value(), "surf_id": self.surface.currentText().strip() or "INERT",
            "name": "ROOM",
        }
        ops = self.openings()
        if ops:
            v["openings"] = ops
        return v

    def _accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self.accept()
