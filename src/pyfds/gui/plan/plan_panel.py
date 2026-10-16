"""The plan view with its controls (plan step F3): floor, level and slab thickness, fit, grid, and the cursor position."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from pyfds.core.events import EventType
from pyfds.gui.viewport_tools import ToolManager

from .plan_view import PlanView


class PlanPanel(QWidget):
    """The plan view with its controls: floor, level and slab thickness, fit, grid, and the cursor position."""

    def __init__(self, api: Any, tools: Optional[ToolManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self._loading = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        unit = api.units.label("length")
        # Two compact rows (the unit sits inside the number boxes), so the panel can stand in a split pane beside the 3D
        # view without forcing the window wide. Row 1: floor, fit, grid. Row 2: level, slab, cursor position.
        row = QHBoxLayout()
        row.addWidget(QLabel("Floor"))
        self.floor_combo = QComboBox(self)
        self.floor_combo.setMinimumContentsLength(8)
        self.floor_combo.activated.connect(self._on_floor)
        row.addWidget(self.floor_combo, 1)
        self.fit_button = QPushButton("Fit", self)
        row.addWidget(self.fit_button)
        self.grid_check = QCheckBox("Grid", self)
        self.grid_check.setChecked(True)
        row.addWidget(self.grid_check)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Level"))
        self.level_box = QDoubleSpinBox(self)
        self.level_box.setRange(-1e3, 1e3)
        self.level_box.setDecimals(2)
        self.level_box.setSuffix(f" {unit}")
        self.level_box.setToolTip("Height of the cut: objects at and above it are shown")
        row2.addWidget(self.level_box)
        row2.addWidget(QLabel("Slab"))
        self.band_box = QDoubleSpinBox(self)
        self.band_box.setRange(0.01, 1e3)
        self.band_box.setDecimals(2)
        self.band_box.setSuffix(f" {unit}")
        self.band_box.setToolTip("How far above the level objects are still shown")
        row2.addWidget(self.band_box)
        row2.addStretch(1)
        self.coords = QLabel("", self)
        row2.addWidget(self.coords)
        v.addLayout(row2)
        self.view = PlanView(api, tools, self)
        v.addWidget(self.view, 1)
        self.level_box.setValue(api.units.to_display(self.view.level, "length"))
        self.band_box.setValue(api.units.to_display(self.view.band, "length"))
        self.level_box.valueChanged.connect(self._on_level)
        self.band_box.valueChanged.connect(self._on_level)
        self.fit_button.clicked.connect(lambda _c=False: self.view.fit())
        self.grid_check.toggled.connect(self._on_grid)
        self.view.cursor_moved.connect(self._on_cursor)
        self.sync_floors()
        self._subs = [api.subscribe(EventType.COMMAND_EXECUTED, lambda _e: self.sync_floors()),
                      api.subscribe(EventType.UNDO_PERFORMED, lambda _e: self.sync_floors()),
                      api.subscribe(EventType.REDO_PERFORMED, lambda _e: self.sync_floors())]

    # forwarded so the window connects to the panel exactly as to the 3D widget
    @property
    def entity_picked(self):
        return self.view.entity_picked

    @property
    def selection_changed(self):
        return self.view.selection_changed

    @property
    def status_message(self):
        return self.view.status_message

    @property
    def cursor_moved(self):
        return self.view.cursor_moved

    def sync_floors(self) -> None:
        self._loading = True
        current = self.floor_combo.currentData()
        self.floor_combo.clear()
        self.floor_combo.addItem("(custom level)", None)
        for f in self.api.floors.all_floors():
            self.floor_combo.addItem(f.name, f.name)
        self.floor_combo.setCurrentIndex(max(0, self.floor_combo.findData(current)))
        self._loading = False

    def set_floor(self, name: str) -> None:
        """Show one floor: its bottom becomes the level and its height the slab."""
        f = self.api.floors.get_floor(name)
        if f is None:
            raise KeyError(f"floor {name!r} not found")
        self._loading = True
        self.floor_combo.setCurrentIndex(max(0, self.floor_combo.findData(name)))
        self.level_box.setValue(self.api.units.to_display(f.z_min, "length"))
        self.band_box.setValue(self.api.units.to_display(max(f.z_max - f.z_min, 0.01), "length"))
        self._loading = False
        self._on_level()

    def _on_floor(self, index: int) -> None:
        name = self.floor_combo.itemData(index)
        if name is not None:
            self.set_floor(name)

    def _on_level(self, *_a) -> None:
        if self._loading:
            return
        u = self.api.units
        self.view.set_level(u.from_display(self.level_box.value(), "length"),
                            u.from_display(self.band_box.value(), "length"))

    def _on_grid(self, on: bool) -> None:
        self.view.show_grid = on
        self.view.viewport().update()

    def _on_cursor(self, p) -> None:
        if p is None:
            self.coords.setText("")
        else:
            u = self.api.units
            self.coords.setText("x %.2f  y %.2f %s " % (u.to_display(p[0], "length"), u.to_display(p[1], "length"),
                                                       u.label("length")))

    def shutdown(self) -> None:
        for sid in self._subs:
            self.api.unsubscribe(sid)
        self.view.shutdown()
