"""Field widgets for the collection editor: one small class per kind of value, all with the same face
(``set_value`` / ``value`` / ``changed``), so the form code never looks at the widget type."""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .model import FieldSpec


def _fmt(v: float) -> str:
    return f"{v:.10g}"


class FieldWidget(QObject):
    """Wraps one input widget. ``value()`` returns what the model layer expects as a *displayed* value."""

    changed = Signal()

    def __init__(self, spec: FieldSpec, widget: QWidget, get: Callable[[], Any], set_: Callable[[Any], None],
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.widget = widget
        self._get = get
        self._set = set_

    def value(self) -> Any:
        return self._get()

    def set_value(self, value: Any) -> None:
        self._set(value)


def _line(parent) -> QLineEdit:
    return QLineEdit(parent)


def make_field_widget(spec: FieldSpec, ref_names: Callable[[str], List[str]], parent: Optional[QWidget] = None) -> FieldWidget:
    """Build the right input for *spec*; ``ref_names(collection)`` lists the names a reference field may take."""
    k = spec.kind
    if k in ("float", "int"):
        edit = _line(parent)
        edit.setValidator(QDoubleValidator(edit) if k == "float" else QIntValidator(edit))
        edit.setPlaceholderText("(unset)" if spec.optional else "")

        def get_num():
            t = edit.text().strip().replace(",", ".")
            if not t:
                return None
            try:
                return float(t) if k == "float" else int(float(t))
            except ValueError:
                return None
        fw = FieldWidget(spec, edit, get_num,
                         lambda v: edit.setText("" if v is None else (_fmt(v) if k == "float" else str(int(v)))), parent)
        edit.textChanged.connect(lambda _t: fw.changed.emit())
        return fw
    if k == "bool":
        box = QCheckBox(parent)
        fw = FieldWidget(spec, box, box.isChecked, lambda v: box.setChecked(bool(v)), parent)
        box.toggled.connect(lambda _b: fw.changed.emit())
        return fw
    if k in ("enum", "ref"):
        combo = QComboBox(parent)
        choices = list(spec.enum_values) if k == "enum" else [""] + ref_names(spec.ref_collection or "")
        combo.setEditable(k == "ref")
        combo.addItems(choices)

        def set_choice(v):
            text = "" if v is None else str(v)
            if combo.findText(text) < 0:
                combo.addItem(text)
            combo.setCurrentText(text)
        fw = FieldWidget(spec, combo, combo.currentText, set_choice, parent)
        combo.currentTextChanged.connect(lambda _t: fw.changed.emit())
        return fw
    if k == "vec":
        holder = QWidget(parent)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        edits = []
        for _ in range(spec.length):
            e = _line(holder)
            e.setValidator(QIntValidator(e) if spec.int_vec else QDoubleValidator(e))
            row.addWidget(e)
            edits.append(e)

        def get_vec():
            texts = [e.text().strip().replace(",", ".") for e in edits]
            if not any(texts):
                return None
            try:
                return tuple((int(float(t)) if spec.int_vec else float(t)) for t in texts)
            except ValueError:
                return None

        def set_vec(v):
            for e, x in zip(edits, v if v is not None else [None] * len(edits)):
                e.setText("" if x is None else (str(int(x)) if spec.int_vec else _fmt(x)))
        fw = FieldWidget(spec, holder, get_vec, set_vec, parent)
        for e in edits:
            e.textChanged.connect(lambda _t: fw.changed.emit())
        return fw
    if k == "list_float":
        edit = _line(parent)
        edit.setPlaceholderText("numbers separated by commas")

        def get_floats():
            out = []
            for t in edit.text().replace(";", ",").split(","):
                t = t.strip()
                if t:
                    try:
                        out.append(float(t))
                    except ValueError:
                        return None
            return out
        fw = FieldWidget(spec, edit, get_floats, lambda v: edit.setText(", ".join(_fmt(x) for x in (v or []))), parent)
        edit.textChanged.connect(lambda _t: fw.changed.emit())
        return fw
    if k == "rows":
        return _rows_widget(spec, ref_names, parent)
    if k == "list_str":
        edit = _line(parent)
        edit.setPlaceholderText("comma separated")
        fw = FieldWidget(spec, edit, lambda: [t.strip() for t in edit.text().split(",") if t.strip()],
                         lambda v: edit.setText(", ".join(v or [])), parent)
        edit.textChanged.connect(lambda _t: fw.changed.emit())
        return fw
    edit = _line(parent)                                   # str
    fw = FieldWidget(spec, edit, edit.text, lambda v: edit.setText("" if v is None else str(v)), parent)
    edit.textChanged.connect(lambda _t: fw.changed.emit())
    return fw


def _cell_text(col: FieldSpec, value) -> str:
    if value is None:
        return ""
    if col.kind == "list_str":
        return ", ".join(value)
    if col.kind == "list_float":
        return ", ".join(_fmt(x) for x in value)
    if col.kind == "float":
        return _fmt(value)
    return str(value)


def _parse_cell(col: FieldSpec, text: str):
    t = text.strip()
    if col.kind == "list_str":
        return [x.strip() for x in t.split(",") if x.strip()] or None
    if col.kind == "list_float":
        try:
            return [float(x) for x in t.split(",") if x.strip()] or None
        except ValueError:
            return None
    if not t:
        return None
    try:
        if col.kind == "float":
            return float(t.replace(",", "."))
        if col.kind == "int":
            return int(float(t))
    except ValueError:
        return None
    return t


def _rows_widget(spec: FieldSpec, ref_names: Callable[[str], List[str]], parent: Optional[QWidget]) -> FieldWidget:
    """A table of sub-objects (surface layers, pyrolysis reactions), one column per field."""
    holder = QWidget(parent)
    v = QVBoxLayout(holder)
    v.setContentsMargins(0, 0, 0, 0)
    cols = spec.columns
    table = QTableWidget(0, len(cols), holder)
    table.setHorizontalHeaderLabels([c.label for c in cols])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    v.addWidget(table)
    buttons = QHBoxLayout()
    add = QPushButton("Add row", holder)
    rem = QPushButton("Remove selected", holder)
    up = QPushButton("Move up", holder)
    buttons.addWidget(add)
    buttons.addWidget(rem)
    buttons.addWidget(up)
    buttons.addStretch(1)
    v.addLayout(buttons)

    def add_row(values=None):
        values = values or {}
        r = table.rowCount()
        table.insertRow(r)
        for c, col in enumerate(cols):
            if col.kind == "ref":
                combo = QComboBox(table)
                combo.setEditable(True)
                combo.addItems([""] + ref_names(col.ref_collection or ""))
                combo.setCurrentText(_cell_text(col, values.get(col.name)))
                combo.currentTextChanged.connect(lambda _t: fw.changed.emit())
                table.setCellWidget(r, c, combo)
            elif col.kind == "bool":
                item = QTableWidgetItem()
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if values.get(col.name) else Qt.Unchecked)
                table.setItem(r, c, item)
            else:
                table.setItem(r, c, QTableWidgetItem(_cell_text(col, values.get(col.name))))

    def get_rows():
        rows = []
        for r in range(table.rowCount()):
            row = {}
            for c, col in enumerate(cols):
                if col.kind == "ref":
                    row[col.name] = table.cellWidget(r, c).currentText().strip() or None
                elif col.kind == "bool":
                    row[col.name] = table.item(r, c).checkState() == Qt.Checked
                else:
                    row[col.name] = _parse_cell(col, table.item(r, c).text() if table.item(r, c) else "")
            rows.append(row)
        return rows

    def set_rows(rows):
        table.setRowCount(0)
        for row in rows or []:
            add_row(dict(row))

    def remove_selected():
        for r in sorted({i.row() for i in table.selectedIndexes()}, reverse=True):
            table.removeRow(r)
        fw.changed.emit()

    def move_up():
        rows = get_rows()
        sel = sorted({i.row() for i in table.selectedIndexes()})
        if sel and sel[0] > 0:
            r = sel[0]
            rows[r - 1], rows[r] = rows[r], rows[r - 1]
            set_rows(rows)
            table.selectRow(r - 1)
            fw.changed.emit()

    fw = FieldWidget(spec, holder, get_rows, set_rows, parent)
    fw.add_row = lambda values=None: (add_row(values), fw.changed.emit())
    fw.table = table
    add.clicked.connect(lambda _c=False: fw.add_row())
    rem.clicked.connect(lambda _c=False: remove_selected())
    up.clicked.connect(lambda _c=False: move_up())
    table.itemChanged.connect(lambda _i: fw.changed.emit())
    return fw
