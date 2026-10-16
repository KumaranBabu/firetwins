"""Examples browser: pick one of the built-in example models and open it (Help > Examples)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


class ExamplesDialog(QDialog):
    """Lists ``api.examples``. Opening one replaces the current project, so it asks first when there is anything in it."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None, on_loaded=None) -> None:
        super().__init__(parent)
        self.api = api
        self.on_loaded = on_loaded
        self.setWindowTitle("Examples")
        self.resize(640, 360)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.list = QListWidget(self)
        self.list.currentRowChanged.connect(self._show)
        row.addWidget(self.list, 1)
        self.about = QLabel("", self)
        self.about.setWordWrap(True)
        self.about.setMinimumWidth(280)
        row.addWidget(self.about, 1)
        v.addLayout(row)
        self.open_button = QPushButton("Open example", self)
        self.open_button.clicked.connect(lambda _c=False: self.open_selected())
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.addButton(self.open_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._items = self.api.examples.list()
        self.list.addItems([e["title"] for e in self._items])
        if self._items:
            self.list.setCurrentRow(0)
        self.open_button.setEnabled(bool(self._items))

    def _show(self, row: int) -> None:
        self.about.setText(self._items[row]["about"] if 0 <= row < len(self._items) else "")

    def selected(self) -> Optional[str]:
        row = self.list.currentRow()
        return self._items[row]["name"] if 0 <= row < len(self._items) else None

    def _project_has_content(self) -> bool:
        return any(getattr(self.api, a).all() for a in ("meshes", "obstructions", "vents", "devices", "geom"))

    def open_selected(self, confirm: bool = True) -> Optional[Dict[str, str]]:
        name = self.selected()
        if name is None:
            return None
        if confirm and self._project_has_content() and QMessageBox.question(
                self, "Open example", "Opening an example replaces the current project. Continue?") != QMessageBox.Yes:
            return None
        info = self.api.examples.load(name)
        if self.on_loaded:
            self.on_loaded(info)
        self.accept()
        return info
