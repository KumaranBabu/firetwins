"""EntityCollectionEditor (plan step F5): PyroSim's "Edit <Things>" dialog, built once for every collection.

    [ list of objects ]   [ tabs by category + Advanced (rest of the fields, raw FDS keywords) ]
    [ New  Clone  ... ]   [ live FDS record preview, changed parameters highlighted           ]

All logic is in ``EntityEditorModel``; this class only shows it. Edits are applied as one undo step.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from .model import EntityEditorModel, FieldSpec
from .widgets import FieldWidget, make_field_widget

ADVANCED_TAB = "Advanced"


def changed_tokens(original: str, edited: str) -> List[str]:
    """The ``KEY=value`` pieces of *edited* that are not in *original* (what the preview highlights)."""
    def tokens(text: str) -> List[str]:
        return [t.strip() for t in text.replace("\n", " ").replace("/", " ").split(", ") if t.strip()]
    old = set(tokens(original))
    return [t for t in tokens(edited) if t not in old]


class EntityCollectionEditor(QDialog):
    def __init__(self, api: Any, attr: str, title: str, parent: Optional[QWidget] = None,
                 select: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.attr = attr
        self.model = EntityEditorModel(api, attr)
        self.setWindowTitle(title)
        self.resize(900, 620)
        self._current: Optional[Any] = None
        self._widgets: Dict[str, FieldWidget] = {}
        self._loading = False
        self._build()
        self.refresh_list(select)

    # -- layout ---------------------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal, self)
        outer.addWidget(split, 1)

        left = QWidget(split)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget(left)
        self.list.currentTextChanged.connect(self._on_list_changed)
        lv.addWidget(self.list, 1)
        self.new_button = self._button(lv, "New", self.new_object)
        self.clone_button = self._button(lv, "Clone", self.clone_object)
        self.rename_button = self._button(lv, "Rename...", self.rename_object)
        self.delete_button = self._button(lv, "Delete...", self.delete_object)
        self.library_button = self._button(lv, "Add From Library...", self.add_from_library)
        self.library_button.setVisible(bool(self.model.library_names()))

        right = QWidget(split)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.info = QLabel(right)
        self.info.setWordWrap(True)
        rv.addWidget(self.info)
        self.tabs = QTabWidget(right)
        rv.addWidget(self.tabs, 1)
        self.preview = QPlainTextEdit(right)
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(110)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.preview.setFont(mono)
        rv.addWidget(QLabel("FDS record", right))
        rv.addWidget(self.preview)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 680])

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda: self.apply())
        outer.addWidget(self.buttons)

    @staticmethod
    def _button(layout, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda _c=False: slot())
        layout.addWidget(b)
        return b

    # -- the list ---------------------------------------------------------------------------------
    def names(self) -> List[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def refresh_list(self, select: Optional[str] = None) -> None:
        keep = select or (self._current.name if self._current is not None else None)
        self._loading = True
        self.list.clear()
        for name in self.model.names():
            self.list.addItem(name)
        self._loading = False
        row = self.names().index(keep) if keep in self.names() else (0 if self.list.count() else -1)
        self._current = None
        self.list.setCurrentRow(row)
        if row < 0:
            self._clear_form()

    def select(self, name: str) -> None:
        if name in self.names():
            self.list.setCurrentRow(self.names().index(name))

    def _on_list_changed(self, name: str) -> None:
        if self._loading:
            return
        if self._current is not None and not self._apply_quietly():
            self._loading = True                      # the pending edits are invalid: stay on the same object
            self.select(self._current.name)
            self._loading = False
            return
        entity = self.model.get(name) if name else None
        self._current = entity
        self._load(entity) if entity is not None else self._clear_form()

    # -- the form ---------------------------------------------------------------------------------
    def _clear_form(self) -> None:
        self.tabs.clear()
        self._widgets = {}
        self.info.setText("")
        self.preview.setPlainText("")

    def _ref_names(self, collection: str) -> List[str]:
        try:
            return [getattr(e, "name", "") for e in getattr(self.api, collection).all()]
        except AttributeError:
            return []

    def _load(self, entity: Any) -> None:
        self._loading = True
        self._clear_form()
        specs = self.model.fields(entity)
        shown = self.model.current(entity, specs)
        pages: Dict[str, QFormLayout] = {}
        for spec in specs:
            tab = ADVANCED_TAB if spec.advanced else spec.category
            if tab not in pages:
                page = QWidget(self.tabs)
                pages[tab] = QFormLayout(page)
                self.tabs.addTab(page, tab)
            fw = make_field_widget(spec, self._ref_names, self)
            fw.set_value(shown.get(spec.name))
            fw.changed.connect(self._update_preview)
            unit = self.model.unit_label(spec)
            label = f"{spec.label} ({unit})" if unit else spec.label
            if spec.kind == "rows":                      # a table fills its own tab
                pages[tab].addRow(fw.widget)
            else:
                pages[tab].addRow(label, fw.widget)
            if spec.description:
                fw.widget.setToolTip(spec.description)
            self._widgets[spec.name] = fw
        self._add_extras_table(entity, pages.get(ADVANCED_TAB))
        # the Advanced tab goes last, whatever order the fields came in
        idx = next((i for i in range(self.tabs.count()) if self.tabs.tabText(i) == ADVANCED_TAB), -1)
        if 0 <= idx < self.tabs.count() - 1:
            self.tabs.tabBar().moveTab(idx, self.tabs.count() - 1)
        lines = self.model.info(entity)
        missing = self.model.unsupported_fields(entity)
        if missing:
            lines.append("not editable here yet: " + ", ".join(missing))
        self.info.setText("\n".join(lines))
        self._loading = False
        self._update_preview()

    def _add_extras_table(self, entity: Any, advanced_form: Optional[QFormLayout]) -> None:
        if advanced_form is None:
            page = QWidget(self.tabs)
            advanced_form = QFormLayout(page)
            self.tabs.addTab(page, ADVANCED_TAB)
        holder = QWidget(self)
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, 0, 0, 0)
        self.extras_table = QTableWidget(0, 2, holder)
        self.extras_table.setHorizontalHeaderLabels(["FDS keyword", "Value"])
        self.extras_table.horizontalHeader().setStretchLastSection(True)
        for key, value in self.model.extras(entity).items():
            self._add_extra_row(key, value)
        v.addWidget(self.extras_table)
        row = QHBoxLayout()
        add = QPushButton("Add keyword", holder)
        add.clicked.connect(lambda _c=False: self._add_extra_row("", ""))
        rem = QPushButton("Remove selected", holder)
        rem.clicked.connect(lambda _c=False: self._remove_extra_rows())
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.addLayout(row)
        advanced_form.addRow("Additional FDS parameters", holder)

    def _add_extra_row(self, key: str, value: str) -> None:
        r = self.extras_table.rowCount()
        self.extras_table.insertRow(r)
        self.extras_table.setItem(r, 0, QTableWidgetItem(key))
        self.extras_table.setItem(r, 1, QTableWidgetItem(value))

    def _remove_extra_rows(self) -> None:
        for r in sorted({i.row() for i in self.extras_table.selectedIndexes()}, reverse=True):
            self.extras_table.removeRow(r)

    def extras_in_table(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for r in range(self.extras_table.rowCount()):
            k = (self.extras_table.item(r, 0).text() if self.extras_table.item(r, 0) else "").strip().upper()
            v = (self.extras_table.item(r, 1).text() if self.extras_table.item(r, 1) else "").strip()
            if k:
                out[k] = v
        return out

    # -- values, preview, apply -----------------------------------------------------------------------
    def field_widget(self, name: str) -> FieldWidget:
        return self._widgets[name]

    def pending(self) -> Dict[str, Any]:
        return {name: fw.value() for name, fw in self._widgets.items()}

    def is_dirty(self) -> bool:
        if self._current is None:
            return False
        try:
            return bool(self.model.changes(self._current, self.pending())) or \
                self.extras_in_table() != self.model.extras(self._current)
        except (KeyError, ValueError):
            return True

    def preview_text(self) -> str:
        return self.preview.toPlainText()

    def _update_preview(self) -> None:
        if self._loading or self._current is None:
            return
        try:
            original = self.model.record(self._current)
            edited = self.model.record(self._current, self.pending())
        except Exception as exc:
            self.preview.setPlainText(f"(cannot preview: {exc})")
            return
        self.preview.setPlainText(edited)
        marks = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff2a8"))
        fmt.setForeground(QColor("#000000"))
        doc_text = edited
        for token in changed_tokens(original, edited):
            start = doc_text.find(token)
            if start >= 0:
                sel = QTextEdit.ExtraSelection()
                cur = QTextCursor(self.preview.document())
                cur.setPosition(start)
                cur.setPosition(start + len(token), QTextCursor.KeepAnchor)
                sel.cursor, sel.format = cur, fmt
                marks.append(sel)
        self.preview.setExtraSelections(marks)

    def apply(self) -> Dict[str, Any]:
        """Apply the form to the current object (one undo step). Raises ``ValueError`` if a value is invalid."""
        if self._current is None:
            return {}
        entity = self._current
        pending = self.pending()
        for name, fw in self._widgets.items():
            spec = fw.spec
            if pending[name] is None and not spec.optional and spec.kind in ("float", "int", "vec", "list_float"):
                raise ValueError(f"{spec.label} needs a value")
        with self.api.history.transaction(f"edit {entity.name}"):
            changed = self.model.apply(entity, pending)
            table = self.extras_in_table()
            old = self.model.extras(entity)
            for key in set(old) - set(table):
                self.model.remove_extra(entity, key)
            for key, value in table.items():
                if old.get(key) != value:
                    self.model.set_extra(entity, key, value)
                    changed[key] = value
        if "name" in changed:
            self.refresh_list(entity.name)
        else:
            self._load(entity)
        return changed

    def _apply_quietly(self) -> bool:
        try:
            self.apply()
            return True
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return False

    def _on_ok(self) -> None:
        if self._apply_quietly():
            self.accept()

    # -- list buttons -----------------------------------------------------------------------------------
    def new_object(self) -> Any:
        if self._current is not None and not self._apply_quietly():
            return None
        entity = self.model.create()
        self._current = None
        self.refresh_list(entity.name)
        return entity

    def clone_object(self) -> Any:
        if self._current is None:
            return None
        try:
            fresh = self.model.clone(self._current)
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None
        self.refresh_list(fresh.name)
        return fresh

    def rename_object(self) -> None:
        if self._current is None:
            return
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=self._current.name)
        if not ok or not name or name == self._current.name:
            return
        try:
            self.model.rename(self._current, name)
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Rename", str(exc))
            return
        self.refresh_list(name)

    def delete_object(self) -> None:
        if self._current is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete {self._current.name}?") != QMessageBox.Yes:
            return
        self.model.delete(self._current)
        self._current = None
        self.refresh_list()

    def add_from_library(self) -> Any:
        names = self.model.library_names()
        if not names:
            return None
        name, ok = QInputDialog.getItem(self, "Add From Library", "Choose one:", names, 0, False)
        if not ok:
            return None
        try:
            entity = self.model.add_from_library(name)
        except Exception as exc:
            QMessageBox.warning(self, "Add From Library", str(exc))
            return None
        self.refresh_list(getattr(entity, "name", None))
        return entity
