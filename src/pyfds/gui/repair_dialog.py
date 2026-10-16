"""Geometry Repair: check an imported shape for holes, duplicate or degenerate triangles and flipped faces, and repair it.

All logic is ``api.geom.check_geometry`` / ``api.geom.repair`` (one undo step); this dialog shows the numbers before and
after. Opened from Model > Geometry Repair and Tools > Geometry Repair.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)


def _fmt(report: Dict[str, Any]) -> str:
    return "\n".join(f"{k.replace('_', ' '):<28} {v}" for k, v in report.items() if not isinstance(v, (list, dict)) or v)


class GeometryRepairDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None, select: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Geometry Repair")
        self.resize(560, 480)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.shape_combo = QComboBox(self)
        form.addRow("Shape", self.shape_combo)
        self.orient_check = QCheckBox("Make every face wind the same way (outward)", self)
        self.orient_check.setChecked(True)
        form.addRow(self.orient_check)
        v.addLayout(form)
        self.report = QPlainTextEdit(self)
        self.report.setReadOnly(True)
        v.addWidget(self.report, 1)
        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.repair_button = QPushButton("Repair", self)
        self.repair_button.clicked.connect(lambda _c=False: self.run_repair())
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.addButton(self.repair_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self.shape_combo.currentTextChanged.connect(lambda _t: self.show_check())
        self.reload(select)

    def reload(self, select: Optional[str] = None) -> None:
        names = [g.name for g in self.api.geom.all() if g.verts and g.faces]
        self.shape_combo.blockSignals(True)
        self.shape_combo.clear()
        self.shape_combo.addItems(names)
        if select in names:
            self.shape_combo.setCurrentText(select)
        self.shape_combo.blockSignals(False)
        self.repair_button.setEnabled(bool(names))
        self.show_check()

    def current(self) -> Optional[str]:
        return self.shape_combo.currentText() or None

    def show_check(self) -> Dict[str, Any]:
        name = self.current()
        if name is None:
            self.report.setPlainText("There are no imported or drawn shapes to check.")
            return {}
        result = self.api.geom.check_geometry(name)
        self.report.setPlainText(_fmt(result))
        self.status.setText("")
        return result

    def run_repair(self) -> Optional[Dict[str, Any]]:
        name = self.current()
        if name is None:
            return None
        try:
            report = self.api.geom.repair(name, orient=self.orient_check.isChecked())
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None
        self.report.setPlainText(_fmt(report) + "\n\n--- after repair ---\n" + _fmt(self.api.geom.check_geometry(name)))
        self.status.setText(f"{name} repaired (Undo restores it).")
        return report
