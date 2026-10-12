"""Layers panel: tick boxes that show or hide each kind of object in the 3D view (same flags as View > Show)."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from pyfds.core.viewport import VisibilityFlags

# (label, flag, swatch colour) - colours match the viewport's object colours
LAYERS: List[Tuple[str, VisibilityFlags, str]] = [
    ("Meshes", VisibilityFlags.MESHES, "#2563eb"),
    ("Obstructions", VisibilityFlags.OBSTRUCTIONS, "#a16207"),
    ("Vents", VisibilityFlags.VENTS, "#dc2626"),
    ("Devices", VisibilityFlags.DEVICES, "#16a34a"),
    ("Init regions", VisibilityFlags.INIT_REGIONS, "#ea580c"),
    ("Profiles", VisibilityFlags.PROFILES, "#7c3aed"),
    ("Geometry", VisibilityFlags.GEOMETRY, "#0891b2"),
    ("HVAC", VisibilityFlags.HVAC, "#475569"),
    ("Grid", VisibilityFlags.GRID, "#94a3b8"),
    ("Axes", VisibilityFlags.AXES, "#64748b"),
    ("Labels", VisibilityFlags.LABELS, "#334155"),
]


def _swatch(colour: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor(colour))
    return QIcon(pm)


class LayersPanel(QWidget):
    """One checkable row per layer; ticking calls ``api.viewport.set_visibility``."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api = api
        self._busy = False
        root = QVBoxLayout(self)
        self.list = QListWidget()
        self._items = {}
        for label, flag, colour in LAYERS:
            item = QListWidgetItem(_swatch(colour), label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setData(Qt.UserRole, flag)
            self.list.addItem(item)
            self._items[flag] = item
        self.list.itemChanged.connect(self._on_changed)
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, state in (("Show all", True), ("Hide all", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, s=state: self.set_all(s))
            row.addWidget(b)
        root.addLayout(row)
        self.sync()

    def sync(self) -> None:
        """Tick the boxes to match the viewport state."""
        self._busy = True
        try:
            for flag, item in self._items.items():
                item.setCheckState(Qt.Checked if self._api.viewport.state.is_visible(flag) else Qt.Unchecked)
        finally:
            self._busy = False

    def set_all(self, visible: bool) -> None:
        for flag in self._items:
            self._api.viewport.set_visibility(flag, visible)
        self.sync()

    def _on_changed(self, item: QListWidgetItem) -> None:
        if self._busy:
            return
        self._api.viewport.set_visibility(item.data(Qt.UserRole), item.checkState() == Qt.Checked)
