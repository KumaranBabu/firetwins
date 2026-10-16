"""Tool Properties (plan step F2): the numbers and surfaces the viewport drawing tools use — height, base, surface, cell
size, wall thickness, and the Paint tool's surface with a list of recent ones. Edits go straight into ``ToolProps``;
lengths are typed in the project's display units."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QListWidget, QVBoxLayout, QWidget,
)


class ToolPropertiesPanel(QWidget):
    def __init__(self, api: Any, tool_manager: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.manager = tool_manager
        self._loading = False
        v = QVBoxLayout(self)
        self.tool_label = QLabel("", self)
        self.tool_label.setStyleSheet("font-weight: 600;")
        v.addWidget(self.tool_label)
        form = QFormLayout()
        v.addLayout(form)
        self.height_box = self._spin(form, "Height", 0.01, 1e5)
        self.auto_base = QCheckBox("Start on the clicked surface", self)
        form.addRow(self.auto_base)
        self.base_box = self._spin(form, "Base Z", -1e5, 1e5)
        self.surface_combo = QComboBox(self)
        self.surface_combo.setEditable(True)
        form.addRow("Surface", self.surface_combo)
        self.cell_box = self._spin(form, "Mesh cell size", 0.001, 1e3)
        self.thickness_box = self._spin(form, "Wall thickness", 0.001, 1e3)
        self.paint_combo = QComboBox(self)
        self.paint_combo.setEditable(True)
        form.addRow("Paint surface", self.paint_combo)
        v.addWidget(QLabel("Recent surfaces", self))
        self.recent = QListWidget(self)
        self.recent.setMaximumHeight(90)
        self.recent.itemClicked.connect(lambda it: self.set_paint_surface(it.text()))
        v.addWidget(self.recent)
        v.addStretch(1)
        self.height_box.valueChanged.connect(self._save)
        self.base_box.valueChanged.connect(self._save)
        self.auto_base.toggled.connect(self._save)
        self.cell_box.valueChanged.connect(self._save)
        self.thickness_box.valueChanged.connect(self._save)
        self.surface_combo.currentTextChanged.connect(self._save)
        self.paint_combo.currentTextChanged.connect(self._save)
        tool_manager.subscribe(self.sync)
        self.sync()

    def _spin(self, form: QFormLayout, label: str, lo: float, hi: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox(self)
        box.setDecimals(3)
        box.setRange(lo, hi)
        form.addRow(f"{label} ({self.api.units.label('length')})", box)
        return box

    # -- values <-> ToolProps ---------------------------------------------------------------------------------
    def _disp(self, si: float) -> float:
        return self.api.units.to_display(si, "length")

    def _si(self, shown: float) -> float:
        return self.api.units.from_display(shown, "length")

    def sync(self) -> None:
        """Show the current ToolProps (also called when the tool or the recent list changes)."""
        p = self.manager.props
        self._loading = True
        self.tool_label.setText(f"Tool: {self.manager.current.label}")
        self.height_box.setValue(self._disp(p.height))
        self.auto_base.setChecked(p.z_base is None)
        self.base_box.setEnabled(p.z_base is not None)
        self.base_box.setValue(self._disp(p.z_base or 0.0))
        self.cell_box.setValue(self._disp(p.cell_size))
        self.thickness_box.setValue(self._disp(p.wall_thickness))
        names = [s.name for s in self.api.surfaces.all()]
        for combo, current in ((self.surface_combo, p.surface_id or ""), (self.paint_combo, p.paint_surface or "")):
            combo.clear()
            combo.addItems([""] + names)
            combo.setCurrentText(current)
        self.recent.clear()
        self.recent.addItems(p.recent_surfaces)
        self._loading = False

    def _save(self, *_a) -> None:
        if self._loading:
            return
        p = self.manager.props
        p.height = self._si(self.height_box.value())
        p.z_base = None if self.auto_base.isChecked() else self._si(self.base_box.value())
        self.base_box.setEnabled(not self.auto_base.isChecked())
        p.cell_size = self._si(self.cell_box.value())
        p.wall_thickness = self._si(self.thickness_box.value())
        p.surface_id = self.surface_combo.currentText().strip() or None
        p.paint_surface = self.paint_combo.currentText().strip() or None

    def set_paint_surface(self, name: str) -> None:
        self.paint_combo.setCurrentText(name)
