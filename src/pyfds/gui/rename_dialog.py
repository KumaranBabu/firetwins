"""Rename dialog (PyroSim "Bulk Renaming"): one new name for the selection, or a name template with ``${keyword}`` parts
worked out for each object. The keywords are buttons that type themselves at the cursor; the list below shows every old and new
name before anything is changed. All logic is in ``api.rename``."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from pyfds.api.renaming import KEYWORDS, describe


class RenameDialog(QDialog):
    def __init__(self, api: Any, entities: Sequence[Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.entities: List[Any] = list(entities)
        self.setWindowTitle("Rename")
        self.resize(520, 480)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"{len(self.entities)} object(s) selected. New name:", self))
        self.edit = QLineEdit(self.entities[0].name if len(self.entities) == 1 else "", self)
        self.edit.textChanged.connect(lambda _t: self._refresh())
        v.addWidget(self.edit)
        self.template_check = QCheckBox("Rename with Template", self)
        self.template_check.toggled.connect(self._on_template_toggled)
        v.addWidget(self.template_check)
        self.keyword_row = QWidget(self)
        row = QHBoxLayout(self.keyword_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.keyword_buttons = {}
        for kw in KEYWORDS:
            if kw == "parent_name-1":
                continue
            b = QPushButton(kw, self.keyword_row)
            b.setToolTip(describe(kw))
            b.clicked.connect(lambda _c=False, k=kw: self.insert_keyword(k))
            row.addWidget(b)
            self.keyword_buttons[kw] = b
        self.keyword_row.setVisible(False)
        v.addWidget(self.keyword_row)
        self.hint = QLabel("Example: ${base_name}${type}_${post_num}", self)
        self.hint.setVisible(False)
        v.addWidget(self.hint)
        self.preview = QListWidget(self)
        v.addWidget(self.preview, 1)
        self.error = QLabel("", self)
        self.error.setStyleSheet("color: #b3261e;")
        v.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self._refresh()

    # -- state ------------------------------------------------------------------------------------------------------
    def _on_template_toggled(self, on: bool) -> None:
        self.keyword_row.setVisible(on)
        self.hint.setVisible(on)
        self._refresh()

    def insert_keyword(self, keyword: str) -> None:
        self.edit.insert("${" + keyword + "}")
        self.edit.setFocus()

    def plan(self):
        """``[(entity, new name)]`` for what is typed (raises ValueError when it cannot be used)."""
        text = self.edit.text()
        if self.template_check.isChecked():
            return self.api.rename.preview(self.entities, template=text)
        return self.api.rename.preview(self.entities, name=text)

    def _refresh(self) -> None:
        self.preview.clear()
        try:
            plan = self.plan()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        self.error.setText("")
        for e, new in plan:
            self.preview.addItem(f"{e.name}  ->  {new}")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def _on_ok(self) -> None:
        try:
            self.changed = self.api.rename.rename(
                self.entities, **({"template": self.edit.text()} if self.template_check.isChecked() else {"name": self.edit.text()}))
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
