"""Edit Libraries: browse the built-in and your own definitions, add them to the model, save model items into your
library, remove your entries, and import/export library files."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class LibraryDialog(QDialog):
    """Browse ``api.library``; "Add to Model" keeps the dialog open so several items can be added."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None, category: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Edit Libraries")
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

        files = QHBoxLayout()
        self.save_button = QPushButton("Save Model Item to Library...")
        self.remove_button = QPushButton("Remove from My Library")
        self.import_button = QPushButton("Import...")
        self.export_button = QPushButton("Export My Library...")
        for b, slot in ((self.save_button, self.save_to_library_dialog), (self.remove_button, self.remove_selected),
                        (self.import_button, self.import_file), (self.export_button, self.export_file)):
            b.clicked.connect(lambda _c=False, f=slot: f())
            files.addWidget(b)
        files.addStretch(1)
        root.addLayout(files)
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
            self.remove_button.setEnabled(False)
            return
        entry = self.api.library.get(self._key(), cur.text())
        self.title.setText(entry.get("description") or cur.text())
        self.source.setText("Built-in" if entry["source"] == "builtin" else "Your library")
        self.remove_button.setEnabled(entry["source"] == "user")
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

    # -- your library: save, remove, import, export -----------------------------------------------------
    def _refresh_counts(self) -> None:
        self.category.blockSignals(True)
        for i, c in enumerate(self.api.library.categories()):
            self.category.setItemText(i, f"{c['label']}  ({c['builtin'] + c['user']})")
        self.category.blockSignals(False)
        self._fill()

    def model_candidates(self) -> List[str]:
        """Names of project objects that fit the shown category (what 'Save Model Item' offers)."""
        return self.api.library.candidates(self._key())

    def save_to_library(self, entity_name: str, name: Optional[str] = None, description: str = "",
                        overwrite: bool = False) -> Optional[str]:
        try:
            key = self.api.library.add_to_library(self._key(), entity_name, name or None, overwrite, description)
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return None
        self.status.setText(f"Saved {key} to your library.")
        self._refresh_counts()
        self._select(key)
        return key

    def save_to_library_dialog(self) -> Optional[str]:
        names = self.model_candidates()
        if not names:
            QMessageBox.information(self, "Save to Library", "The model has nothing of this kind to save.")
            return None
        pick, ok = QInputDialog.getItem(self, "Save to Library", "Model item:", names, 0, False)
        if not ok:
            return None
        key, ok = QInputDialog.getText(self, "Save to Library", "Name in the library:", text=pick)
        if not ok or not key.strip():
            return None
        exists = key.strip() in self.api.library.names(self._key(), "user")
        if exists and QMessageBox.question(self, "Save to Library", f"Replace your entry {key.strip()!r}?") != QMessageBox.Yes:
            return None
        return self.save_to_library(pick, key.strip(), "", overwrite=exists)

    def remove_selected(self) -> bool:
        item = self.names.currentItem()
        if item is None:
            return False
        try:
            self.api.library.remove_from_library(self._key(), item.text())
        except KeyError as exc:
            QMessageBox.warning(self, "Could not remove", str(exc))
            return False
        self.status.setText(f"Removed {item.text()} from your library.")
        self._refresh_counts()
        return True

    def import_file(self, path: Optional[str] = None, overwrite: Optional[bool] = None) -> Optional[Dict[str, List[Any]]]:
        path = path or QFileDialog.getOpenFileName(self, "Import Library", "", "Library files (*.json)")[0]
        if not path:
            return None
        if overwrite is None:
            overwrite = QMessageBox.question(self, "Import Library", "Replace entries that already exist in your library?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        try:
            report = (self.api.library.import_library(path, overwrite=overwrite) if path.lower().endswith(".json")
                      else self.api.library.import_fds(path, overwrite=overwrite))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not import", str(exc))
            return None
        self.status.setText("Imported: " + (", ".join(f"{len(v)} {k}" for k, v in report.items() if v) or "nothing new"))
        self._refresh_counts()
        return report

    def export_file(self, path: Optional[str] = None) -> Optional[int]:
        path = path or QFileDialog.getSaveFileName(self, "Export My Library", "my_library.json", "Library files (*.json)")[0]
        if not path:
            return None
        count = self.api.library.export_library(path)
        self.status.setText(f"Exported {count} entries.")
        return count

    def _select(self, name: str) -> None:
        for i in range(self.names.count()):
            if self.names.item(i).text() == name:
                self.names.setCurrentRow(i)
                return
