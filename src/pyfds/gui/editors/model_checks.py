"""Edit Model Checks (plan step F5, CHK-01): switch individual checks on or off, share check sets, run the checks.

All logic is in ``api.validation``; this dialog shows the list and applies the on/off states as ONE undo step.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


class ModelChecksDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None,
                 on_run: Optional[Callable[[Any], None]] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.on_run = on_run
        self.setWindowTitle("Edit Model Checks")
        self.resize(760, 520)
        v = QVBoxLayout(self)
        self.summary = QLabel(self)
        v.addWidget(self.summary)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter checks...")
        self.filter.textChanged.connect(self._apply_filter)
        v.addWidget(self.filter)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["On", "Check", "What it looks for"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 230)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(lambda _i: self._update_summary())
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot in (("Enable all", lambda: self.set_all(True)), ("Disable all", lambda: self.set_all(False)),
                           ("Import set...", self.import_set), ("Export set...", self.export_set)):
            b = QPushButton(text, self)
            b.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(b)
        row.addStretch(1)
        self.run_button = QPushButton("Run Model Checks", self)
        self.run_button.clicked.connect(lambda _c=False: self.run())
        row.addWidget(self.run_button)
        v.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self.load()

    # -- the list --------------------------------------------------------------------------------
    def load(self) -> None:
        checks = self.api.validation.checks()
        self.table.blockSignals(True)
        self.table.setRowCount(len(checks))
        for r, c in enumerate(checks):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            on.setCheckState(Qt.Checked if c["enabled"] else Qt.Unchecked)
            self.table.setItem(r, 0, on)
            for col, text in ((1, c["name"]), (2, c["description"])):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(r, col, item)
        self.table.blockSignals(False)
        self._apply_filter()
        self._update_summary()

    def names(self) -> List[str]:
        return [self.table.item(r, 1).text() for r in range(self.table.rowCount())]

    def states(self) -> Dict[str, bool]:
        return {self.table.item(r, 1).text(): self.table.item(r, 0).checkState() == Qt.Checked
                for r in range(self.table.rowCount())}

    def set_state(self, name: str, on: bool) -> None:
        self.table.item(self.names().index(name), 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def set_all(self, on: bool) -> None:
        """Switch every check shown (the filter limits which) on or off."""
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_summary()

    def _apply_filter(self) -> None:
        text = self.filter.text().strip().lower()
        for r in range(self.table.rowCount()):
            hay = (self.table.item(r, 1).text() + " " + self.table.item(r, 2).text()).lower()
            self.table.setRowHidden(r, bool(text) and text not in hay)

    def _update_summary(self) -> None:
        s = self.states()
        off = sum(1 for v in s.values() if not v)
        self.summary.setText(f"{len(s) - off} of {len(s)} checks on" + (f"  ({off} switched off)" if off else ""))

    # -- apply, share, run -----------------------------------------------------------------------
    def is_dirty(self) -> bool:
        return self.states() != {c["name"]: c["enabled"] for c in self.api.validation.checks()}

    def apply(self) -> bool:
        """Save the on/off states as one undo step. False (with a message) if refused."""
        try:
            self.api.validation.set_enabled_many(self.states())
            return True
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return False

    def _on_ok(self) -> None:
        if self.apply():
            self.accept()

    def run(self) -> Any:
        """Apply the states, run the enabled checks and hand the report to the caller (the results panel)."""
        if not self.apply():
            return None
        report = self.api.validation.validate()
        if self.on_run:
            self.on_run(report)
        return report

    def import_set(self, path: Optional[str] = None) -> List[str]:
        path = path or QFileDialog.getOpenFileName(self, "Import Check Set", "", "Check sets (*.json)")[0]
        if not path:
            return []
        try:
            unknown = self.api.validation.import_check_set(path)
        except (ValueError, KeyError, OSError) as exc:
            QMessageBox.warning(self, "Import Check Set", str(exc))
            return []
        self.load()
        if unknown:
            QMessageBox.information(self, "Import Check Set", "Ignored (unknown here): " + ", ".join(unknown))
        return unknown

    def export_set(self, path: Optional[str] = None) -> Optional[str]:
        path = path or QFileDialog.getSaveFileName(self, "Export Check Set", "checks.json", "Check sets (*.json)")[0]
        if not path or not self.apply():
            return None
        return self.api.validation.export_check_set(path)
