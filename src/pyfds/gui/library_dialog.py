"""Library browser: pick a material, surface, reaction, detector ... and add it to the model."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class LibraryDialog(QDialog):
    """Browse ``api.library``; "Add to Model" keeps the dialog open so several items can be added."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None, category: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Library")
        self.resize(760, 480)
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Category"))
        self.category = QComboBox()
        for c in api.library.categories():
            self.category.addItem(f"{c['label']}  ({c['builtin'] + c['user']})", c["key"])
        top.addWidget(self.category, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name")
        top.addWidget(self.search, 1)
        root.addLayout(top)

        mid = QHBoxLayout()
        self.names = QListWidget()
        mid.addWidget(self.names, 1)
        right = QVBoxLayout()
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600;")
        self.source = QLabel("")
        self.source.setStyleSheet("color: #666;")
        self.fields = QPlainTextEdit()
        self.fields.setReadOnly(True)
        right.addWidget(self.title)
        right.addWidget(self.source)
        right.addWidget(self.fields, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("ID in model"))
        self.new_name = QLineEdit()
        row.addWidget(self.new_name, 1)
        right.addLayout(row)
        mid.addLayout(right, 2)
        root.addLayout(mid, 1)

        self.status = QLabel("")
        root.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.add_button = QPushButton("Add to Model")
        buttons.addButton(self.add_button, QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(lambda b: self.reject() if buttons.buttonRole(b) == QDialogButtonBox.RejectRole else None)
        root.addWidget(buttons)

        self.category.currentIndexChanged.connect(self._fill)
        self.search.textChanged.connect(self._fill)
        self.names.currentItemChanged.connect(self._show)
        self.add_button.clicked.connect(self._add)
        if category is not None:
            i = self.category.findData(category)
            if i >= 0:
                self.category.setCurrentIndex(i)
        self._fill()

    def _key(self) -> str:
        return self.category.currentData()

    def _fill(self, *_a) -> None:
        self.names.blockSignals(True)            # no half-filled list may reach _show()
        self.names.clear()
        text = self.search.text().strip().lower()
        for n in self.api.library.names(self._key()):
            if text in n.lower():
                self.names.addItem(QListWidgetItem(n))
        self.names.blockSignals(False)
        if self.names.count():
            self.names.setCurrentRow(0)
            self._show(self.names.item(0), None)
        else:
            self._show(None, None)

    def _show(self, cur, _prev) -> None:
        if cur is None:
            self.title.setText("")
            self.source.setText("")
            self.fields.setPlainText("")
            self.new_name.setText("")
            self.add_button.setEnabled(False)
            return
        entry = self.api.library.get(self._key(), cur.text())
        self.title.setText(entry.get("description") or cur.text())
        self.source.setText("Built-in" if entry["source"] == "builtin" else "Your library")
        lines = []
        for k, v in entry["fields"].items():
            if k == "layers":
                v = ", ".join(f"{l['material_id']} {l['thickness'] * 1000:g} mm" for l in v)
            lines.append(f"{k.replace('_', ' '):<26} {v}")
        self.fields.setPlainText("\n".join(lines))
        self.new_name.setText(cur.text().upper().replace(" ", "_").replace("-", "_"))
        self.add_button.setEnabled(True)

    def _add(self) -> None:
        item = self.names.currentItem()
        if item is None:
            return
        try:
            ent = self.api.library.add_to_model(self._key(), item.text(), self.new_name.text().strip() or None)
        except Exception as exc:
            QMessageBox.warning(self, "Could not add", str(exc))
            return
        self.status.setText(f"Added {ent.name} to the model.")
