"""Validation panel: the findings of the last validation pass as a list; double-click jumps to the object."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

_COLOURS = {"ERROR": "#b91c1c", "WARNING": "#b45309", "INFO": "#475569"}      # keyed by Severity.name


class ValidationPanel(QWidget):
    entity_activated = Signal(str)        # entity name of the double-clicked finding
    validate_requested = Signal()
    auto_fix_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(2)
        row = QHBoxLayout()
        self.summary = QLabel("Not validated yet.")
        self.summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)      # a long summary must not widen the dock
        row.addWidget(self.summary, 1)
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self.validate_requested)
        self.fix_button = QPushButton("Auto-Fix")
        self.fix_button.clicked.connect(self.auto_fix_requested)
        row.addWidget(self.validate_button)
        row.addWidget(self.fix_button)
        root.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels(["Severity", "Message", "Object", "Hint"])
        self.tree.setColumnWidth(1, 420)
        self.tree.itemDoubleClicked.connect(self._on_activated)
        root.addWidget(self.tree, 1)

    def show_report(self, report: Any) -> None:
        self.tree.clear()
        for r in sorted(report.results, key=lambda r: r.severity.value):
            item = QTreeWidgetItem([r.severity.name.capitalize(), r.message, r.entity_name or "", r.hint or ""])
            item.setForeground(0, QColor(_COLOURS[r.severity.name]))
            item.setData(0, Qt.UserRole, r.entity_name)
            self.tree.addTopLevelItem(item)
        e, w, i = len(report.errors), len(report.warnings), len(report.infos)
        self.summary.setText(("Passed - " if report.passed else "FAILED - ") + f"{e} errors, {w} warnings, {i} notes")
        self.summary.setStyleSheet(f"font-weight: 600; color: {'#15803d' if report.passed else '#b91c1c'};")

    def count(self) -> int:
        return self.tree.topLevelItemCount()

    def _on_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        name = item.data(0, Qt.UserRole)
        if name:
            self.entity_activated.emit(name)
