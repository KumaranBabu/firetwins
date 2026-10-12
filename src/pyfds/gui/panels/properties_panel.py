"""Properties panel: edits the selected object in place (same schema and undoable commands as Edit > Properties)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.property_schema import apply_edits, build_edit_schema

logger = logging.getLogger(__name__)


class PropertiesPanel(QWidget):
    """Shows one form per selected entity; *Apply* writes the changed fields through ``api.set_property``."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None,
                 on_error: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(parent)
        self._api = api
        self._on_error = on_error or (lambda msg: logger.warning("properties: %s", msg))
        self._entity: Any = None
        self._schema: Dict[str, Any] = {}
        self._fields: Dict[str, QWidget] = {}
        self._initial: Dict[str, Any] = {}

        root = QVBoxLayout(self)
        self.title = QLabel("Nothing selected")
        self.title.setStyleSheet("font-weight: 600;")
        root.addWidget(self.title)
        self._holder = QWidget()
        self._form = QFormLayout(self._holder)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._holder)
        root.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.reload)
        row.addStretch(1)
        row.addWidget(self.revert_button)
        row.addWidget(self.apply_button)
        root.addLayout(row)
        self._set_buttons(False)

    # -- selection ---------------------------------------------------------------------------------
    def show_entity(self, attr: Optional[str], entity: Any) -> None:
        """Show *entity*'s fields (``None`` clears the panel)."""
        self._entity = entity
        self.reload()

    def reload(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._fields.clear()
        self._initial.clear()
        entity = self._entity
        if entity is None:
            self.title.setText("Nothing selected")
            self._schema = {}
            self._set_buttons(False)
            return
        self._schema = build_edit_schema(entity)
        self.title.setText(f"{type(entity).__name__}: {getattr(entity, 'name', '')}")
        for name, prop in self._schema["properties"].items():
            widget = self._make_widget(prop)
            self._fields[name] = widget
            self._initial[name] = self._raw(widget)
            self._form.addRow(name.replace("_", " ").capitalize(), widget)
        self._set_buttons(bool(self._fields))

    def _make_widget(self, prop: Dict[str, Any]) -> QWidget:
        if prop.get("type") == "boolean":
            box = QCheckBox()
            box.setChecked(bool(prop.get("default", False)))
            return box
        if "enum" in prop:
            combo = QComboBox()
            combo.addItems([str(v) for v in prop["enum"]])
            idx = combo.findText(str(prop.get("default")))
            if idx >= 0:
                combo.setCurrentIndex(idx)
            return combo
        edit = QLineEdit()
        default = prop.get("default")
        if isinstance(default, (list, tuple)):
            edit.setText(", ".join(str(v) for v in default))
        elif default is not None:
            edit.setText(str(default))
        edit.setToolTip(prop.get("description", ""))
        edit.returnPressed.connect(self.apply)
        return edit

    def _set_buttons(self, on: bool) -> None:
        self.apply_button.setEnabled(on)
        self.revert_button.setEnabled(on)

    # -- editing -----------------------------------------------------------------------------------
    @staticmethod
    def _raw(widget: QWidget) -> Any:
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return widget.currentText() if isinstance(widget, QComboBox) else widget.text().strip()

    def values(self) -> Dict[str, Any]:
        """Only the fields the user changed (unset optional fields are shown with a placeholder default)."""
        out: Dict[str, Any] = {}
        props = self._schema.get("properties", {})
        for name, widget in self._fields.items():
            raw = self._raw(widget)
            if raw == self._initial[name]:
                continue
            out[name] = raw if isinstance(widget, QCheckBox) else SchemaFormDialog._parse_value(name, raw, props[name]) if raw != "" else None
        return {k: v for k, v in out.items() if v is not None}

    def apply(self) -> int:
        """Write the edited fields; returns how many changed (0 on error, which is reported)."""
        if self._entity is None:
            return 0
        try:
            changed = apply_edits(self._api, self._entity, self.values())
        except Exception as exc:                      # invalid text, rejected by the model, ...
            self._on_error(str(exc))
            return 0
        self.reload()
        return changed
