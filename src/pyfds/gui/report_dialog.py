"""
Read-only monospace text report dialog.

Used for anything that already renders a good plain-text ``str()`` —
validation reports today, simulation summaries potentially later — so
there is one dialog class instead of one per report type.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout, QWidget


class TextReportDialog(QDialog):
    def __init__(self, title: str, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 400)

        edit = QTextEdit(self)
        edit.setReadOnly(True)
        edit.setFont(QFont("Consolas", 9))
        edit.setPlainText(text)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(edit)
        layout.addWidget(buttons)
