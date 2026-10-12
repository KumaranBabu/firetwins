"""
Generic "Add Entity" dialog.

Renders a Qt form directly from a ``ToolSpec.input_schema`` — the same
JSON Schema the AI agent tools use (see ``pyfds.agent.registry``). GUI
entity creation and agent entity creation therefore share one field
definition per entity type; there is no separate, hand-written dialog
class per mesh/obstruction/surface/etc. to keep in sync.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QVBoxLayout, QWidget,
)


class SchemaFormDialog(QDialog):
    """One text/combo field per property in a JSON-Schema ``input_schema``."""

    def __init__(
        self,
        title: str,
        description: str,
        input_schema: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._schema = input_schema
        self._required = set(input_schema.get("required", []))
        self._fields: Dict[str, QWidget] = {}

        layout = QFormLayout(self)
        if description:
            note = QLabel(description, self)
            note.setWordWrap(True)
            layout.addRow(note)

        for name, prop in input_schema.get("properties", {}).items():
            widget = self._make_widget(prop)
            self._fields[name] = widget
            label = prop.get("title") or name.replace("_", " ").capitalize()
            label += " *" if name in self._required else ""
            hint = prop.get("description", "")
            if hint and not isinstance(widget, QCheckBox):
                # the description sits under the field instead of vanishing into a placeholder
                box = QWidget(self)
                col = QVBoxLayout(box)
                col.setContentsMargins(0, 0, 0, 0)
                col.setSpacing(1)
                col.addWidget(widget)
                note = QLabel(hint, box)
                note.setWordWrap(True)
                note.setStyleSheet("color: #666; font-size: 11px;")
                col.addWidget(note)
                layout.addRow(label, box)
            else:
                layout.addRow(label, widget)
            widget.setToolTip(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _make_widget(self, prop: Dict[str, Any]) -> QWidget:
        if prop.get("type") == "boolean":
            box = QCheckBox(self)
            box.setChecked(bool(prop.get("default", False)))
            return box

        if "enum" in prop:
            combo = QComboBox(self)
            combo.addItems([str(v) for v in prop["enum"]])
            if "default" in prop:
                idx = combo.findText(str(prop["default"]))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            return combo

        edit = QLineEdit(self)
        if "default" in prop:
            edit.setText(str(prop["default"]))
        hint = prop.get("description", "")
        if prop.get("type") == "array":
            n = prop.get("minItems")
            count_hint = f"{n} comma-separated numbers" if n else "comma-separated numbers"
            hint = f"{hint} ({count_hint})".strip()
        if prop.get("type") == "object" or prop.get("items", {}).get("type") in ("array", "object"):
            hint = f"{hint} (as JSON, e.g. [[0,0],[3,0]] or {{\"PROPANE\": 1}})".strip()
        edit.setPlaceholderText(hint)
        return edit

    def _on_accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self.accept()

    def values(self) -> Dict[str, Any]:
        """Parsed {field_name: value} for every filled-in field, JSON-Schema-typed."""
        result: Dict[str, Any] = {}
        props = self._schema.get("properties", {})
        for name, widget in self._fields.items():
            prop = props.get(name, {})
            if isinstance(widget, QCheckBox):
                # A checkbox always has a definite True/False value — there's
                # no "left blank" state the required/optional check applies to.
                result[name] = widget.isChecked()
                continue
            raw = widget.currentText() if isinstance(widget, QComboBox) else widget.text().strip()
            if not raw:
                if name in self._required:
                    raise ValueError(f"{name!r} is required")
                continue
            result[name] = self._parse_value(name, raw, prop)
        return result

    @staticmethod
    def _parse_value(name: str, raw: str, prop: Dict[str, Any]) -> Any:
        ptype = prop.get("type")
        try:
            if ptype == "number":
                return float(raw)
            if ptype == "integer":
                return int(raw)
            if ptype in ("array", "object") and (ptype == "object" or prop.get("items", {}).get("type") in ("array", "object")):
                import json
                return json.loads(raw)       # nested values (a wall path, openings, stoichiometry) are typed as JSON
            if ptype == "array":
                item_type = prop.get("items", {}).get("type")
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                if item_type == "number":
                    values: list = [float(p) for p in parts]
                elif item_type == "integer":
                    values = [int(p) for p in parts]
                else:
                    values = parts
                n = prop.get("minItems")
                if n is not None and prop.get("maxItems") == n and len(values) != n:
                    raise ValueError(f"{name!r} needs exactly {n} comma-separated values")
                return values
            return raw
        except ValueError:
            raise
        except Exception as exc:  # malformed number/int text etc.
            raise ValueError(f"{name!r}: {exc}") from exc
