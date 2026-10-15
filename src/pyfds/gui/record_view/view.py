"""RecordView (plan step F4): the model's FDS input as live, colour-coded text beside the 3D view.

Read-only. It follows the model (refreshing a moment after any change), scrolls to and marks the record of the
selected object, and a click on a record selects that object. All mapping logic is in ``record_view.model``.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import model
from .highlighter import FdsHighlighter

_MARK = "#fff2a8"


class RecordView(QWidget):
    def __init__(self, api: Any, on_select: Optional[Callable[[str, Any], None]] = None,
                 parent: Optional[QWidget] = None, debounce_ms: int = 150) -> None:
        super().__init__(parent)
        self.api = api
        self.on_select = on_select
        self._records: List[model.RecordLine] = []
        self._syncing = False
        self._text = ""
        self._build()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        bar = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Find in the FDS input")
        self.search.returnPressed.connect(lambda: self.find(self.search.text()))
        nxt = QPushButton("Next", self)
        nxt.clicked.connect(lambda _c=False: self.find(self.search.text()))
        prev = QPushButton("Previous", self)
        prev.clicked.connect(lambda _c=False: self.find(self.search.text(), backwards=True))
        self.follow = QCheckBox("Follow selection", self)
        self.follow.setChecked(True)
        copy = QPushButton("Copy", self)
        copy.clicked.connect(lambda _c=False: self.copy_all())
        save = QPushButton("Save As...", self)
        save.clicked.connect(lambda _c=False: self.save_as())
        for w in (self.search, nxt, prev, self.follow, copy, save):
            bar.addWidget(w, 1 if w is self.search else 0)
        root.addLayout(bar)
        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.editor.setFont(mono)
        self.highlighter = FdsHighlighter(self.editor.document())
        self.editor.cursorPositionChanged.connect(self._on_cursor)
        root.addWidget(self.editor, 1)
        self.status = QLabel("", self)
        root.addWidget(self.status)

    # -- following the model ------------------------------------------------------------------------
    def schedule_refresh(self) -> None:
        """Refresh shortly (a burst of edits is shown once)."""
        self._timer.start()

    def refresh(self) -> None:
        text = self.api.fds_text()
        if text == self._text:
            return
        bar = self.editor.verticalScrollBar()
        keep = bar.value()
        self._text = text
        self._syncing = True
        self.editor.setPlainText(text)
        self._syncing = False
        bar.setValue(keep)
        self._records = model.index_records(text)
        counts = model.summary(self._records)
        self.status.setText(f"{len(self._records)} records  |  " +
                            ", ".join(f"{t} {n}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])[:6]))

    def text(self) -> str:
        return self._text

    def records(self) -> List[model.RecordLine]:
        return list(self._records)

    # -- selection <-> text -----------------------------------------------------------------------------
    def show_entity(self, attr: str, entity: Any) -> bool:
        """Scroll to the object's record(s) and mark them. Returns False if it has no record."""
        lines = model.lines_of(self._records, attr, getattr(entity, "name", ""))
        marks = []
        for n in lines:
            block = self.editor.document().findBlockByNumber(n)
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(block)
            cur.select(QTextCursor.LineUnderCursor)
            sel.cursor = cur
            sel.format.setBackground(QColor(_MARK))
            sel.format.setForeground(QColor("#000000"))
            marks.append(sel)
        self.editor.setExtraSelections(marks)
        if not lines:
            return False
        self._syncing = True
        cur = QTextCursor(self.editor.document().findBlockByNumber(lines[0]))
        self.editor.setTextCursor(cur)
        self.editor.centerCursor()
        self._syncing = False
        return True

    def entity_at_line(self, line: int) -> Optional[Any]:
        rec = model.record_at(self._records, line)
        return model.entity_for(self.api, rec) if rec else None

    def _on_cursor(self) -> None:
        if self._syncing or not self.follow.isChecked() or self.on_select is None:
            return
        line = self.editor.textCursor().blockNumber()
        rec = model.record_at(self._records, line)
        entity = model.entity_for(self.api, rec) if rec else None
        if entity is not None:
            self._syncing = True
            try:
                self.on_select(rec.attr, entity)
            finally:
                self._syncing = False

    # -- tools ---------------------------------------------------------------------------------------------
    def find(self, needle: str, backwards: bool = False) -> bool:
        """Select the next (or previous) match of *needle*, wrapping round; case-insensitive."""
        if not needle:
            return False
        from PySide6.QtGui import QTextDocument
        opts = QTextDocument.FindBackward if backwards else QTextDocument.FindFlag(0)
        found = self.editor.document().find(needle, self.editor.textCursor(), opts)
        if found.isNull():                                          # wrap
            start = QTextCursor(self.editor.document())
            if backwards:
                start.movePosition(QTextCursor.End)
            found = self.editor.document().find(needle, start, opts)
        if found.isNull():
            self.status.setText(f"'{needle}' not found")
            return False
        self._syncing = True
        self.editor.setTextCursor(found)
        self._syncing = False
        self.editor.centerCursor()
        return True

    def copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text)

    def save_as(self) -> Optional[str]:
        path, _ = QFileDialog.getSaveFileName(self, "Save FDS Input", f"{self.api.project.chid}.fds", "FDS Files (*.fds)")
        if not path:
            return None
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._text)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return None
        return path
