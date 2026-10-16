"""Help > Keyboard Shortcuts: see and change the key of every menu command (UI-21)."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from pyfds.gui.actions.keymap import Keymap


class KeymapDialog(QDialog):
    """A searchable table of commands and keys. Changes apply at once (and are saved after each one), so the new
    keys can be tried straight away; Reset All puts every key back."""

    def __init__(self, keymap: Keymap, on_save: Any = None, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.keymap = keymap
        self._on_save = on_save
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(640, 520)
        v = QVBoxLayout(self)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search commands or keys")
        self.search.textChanged.connect(self._filter)
        v.addWidget(self.search)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut", "Default"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row)
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("New shortcut:"))
        self.edit = QKeySequenceEdit(self)
        self.edit.setMaximumSequenceLength(1)
        row.addWidget(self.edit, 1)
        self.assign_button = QPushButton("Assign", self)
        self.assign_button.clicked.connect(lambda _c=False: self.assign(self.edit.keySequence().toString()))
        row.addWidget(self.assign_button)
        self.clear_button = QPushButton("Remove", self)
        self.clear_button.clicked.connect(lambda _c=False: self.assign(""))
        row.addWidget(self.clear_button)
        self.reset_button = QPushButton("Reset", self)
        self.reset_button.clicked.connect(lambda _c=False: self.reset_selected())
        row.addWidget(self.reset_button)
        v.addLayout(row)
        self.message = QLabel("", self)
        self.message.setWordWrap(True)
        v.addWidget(self.message)
        buttons = QDialogButtonBox(self)
        self.reset_all_button = buttons.addButton("Reset All", QDialogButtonBox.ResetRole)
        self.reset_all_button.clicked.connect(lambda _c=False: self.reset_all())
        buttons.addButton(QDialogButtonBox.Close).clicked.connect(self.accept)
        v.addWidget(buttons)
        self._fill()
        self._on_row()

    # -- the table --------------------------------------------------------------------
    def _fill(self, keep: Optional[str] = None) -> None:
        rows = self.keymap.rows()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate((row["label"], row["key"], row["default"])):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, row["id"])
                if row["key"] != row["default"] and c == 1:
                    f = item.font()
                    f.setBold(True)                       # a changed key stands out
                    item.setFont(f)
                self.table.setItem(r, c, item)
        self._filter(self.search.text())
        if keep:
            self.select(keep)

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            hide = bool(t) and not any(t in self.table.item(r, c).text().lower() for c in range(3))
            self.table.setRowHidden(r, hide)

    def selected_id(self) -> Optional[str]:
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None

    def select(self, action_id: str) -> None:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == action_id:
                self.table.selectRow(r)
                return

    def _on_row(self) -> None:
        on = self.selected_id() is not None
        for b in (self.assign_button, self.clear_button, self.reset_button, self.edit):
            b.setEnabled(on)
        self.edit.clear()

    # -- changing keys ----------------------------------------------------------------
    def assign(self, text: str, steal: Optional[bool] = None) -> bool:
        """Give the selected command *text* as its key. A key another command has is taken only if *steal* is True,
        or (when None) the user says yes. Returns whether it was assigned."""
        aid = self.selected_id()
        if aid is None:
            return False
        try:
            self.keymap.set(aid, text)
            self.message.setText("")
        except ValueError as exc:
            if steal is None:
                steal = QMessageBox.question(self, "Shortcut in use",
                                             f"{exc}.\n\nTake it for this command?") == QMessageBox.Yes
            if not steal:
                self.message.setText(str(exc))
                return False
            lost = self.keymap.set(aid, text, steal=True)
            self.message.setText("Taken from: " + ", ".join(c.replace("/", " > ") for c in lost))
        self._changed(aid)
        return True

    def reset_selected(self) -> None:
        aid = self.selected_id()
        if aid is not None:
            self.keymap.reset(aid)
            self._changed(aid)

    def reset_all(self) -> None:
        self.keymap.reset_all()
        self._changed(self.selected_id())

    def _changed(self, keep: Optional[str]) -> None:
        self._fill(keep)
        if self._on_save is not None:
            self._on_save(self.keymap)
