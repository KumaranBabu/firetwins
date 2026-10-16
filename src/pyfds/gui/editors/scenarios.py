"""Edit Scenarios (plan step F5, FIR-07): named variants of one model, each a list of "this object's field has this value".

All logic is in ``api.scenarios``; the dialog shows the list and the override table. Every change is one undo step.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .model import EntityEditorModel
from .widgets import make_field_widget

_SKIP_FIELDS = {"name", "uid"}


def _entity_choices(api: Any) -> List[Any]:
    return [e for e in api.project.all_entities if getattr(e, "name", None) and hasattr(e, "uid")]


class AddOverrideDialog(QDialog):
    """Pick an object and one of its fields, then type the value the scenario should use."""

    def __init__(self, api: Any, parent: Optional[QWidget] = None, entity: Any = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Add Override")
        self.model = EntityEditorModel(api, "meshes")            # only used to describe fields and convert units
        self._entities = _entity_choices(api)
        self._fw = None
        form = QFormLayout(self)
        self.entity_combo = QComboBox(self)
        for e in self._entities:
            self.entity_combo.addItem(f"{e.name}  ({type(e).__name__})")
        self.field_combo = QComboBox(self)
        self.value_holder = QWidget(self)
        self.value_layout = QVBoxLayout(self.value_holder)
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow("Object", self.entity_combo)
        form.addRow("Field", self.field_combo)
        form.addRow("Value in this scenario", self.value_holder)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)
        self.entity_combo.currentIndexChanged.connect(self._load_fields)
        self.field_combo.currentIndexChanged.connect(self._load_value)
        if entity is not None and entity in self._entities:
            self.entity_combo.setCurrentIndex(self._entities.index(entity))
        self._load_fields()

    def entity(self) -> Optional[Any]:
        i = self.entity_combo.currentIndex()
        return self._entities[i] if 0 <= i < len(self._entities) else None

    def _specs(self) -> List[Any]:
        e = self.entity()
        if e is None:
            return []
        return [s for s in self.model.fields(e) if s.name not in _SKIP_FIELDS and s.kind != "rows"]

    def _load_fields(self) -> None:
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        for s in self._specs():
            self.field_combo.addItem(s.label if s.label == s.name else f"{s.label}  ({s.name})", s.name)
        self.field_combo.blockSignals(False)
        self._load_value()

    def select_field(self, name: str) -> None:
        self.field_combo.setCurrentIndex(max(0, self.field_combo.findData(name)))

    def _spec(self) -> Optional[Any]:
        name = self.field_combo.currentData()
        return next((s for s in self._specs() if s.name == name), None)

    def _load_value(self) -> None:
        while self.value_layout.count():
            w = self.value_layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._fw = None
        spec, e = self._spec(), self.entity()
        if spec is None or e is None:
            return
        names = lambda coll: [getattr(x, "name", "") for x in getattr(self.api, coll).all()] if hasattr(self.api, coll) else []
        self._fw = make_field_widget(spec, names, self.value_holder)
        self._fw.set_value(self.model.to_display(spec, getattr(e, spec.name, None)))
        unit = self.model.unit_label(spec)
        self.value_layout.addWidget(self._fw.widget)
        if unit:
            self.value_layout.addWidget(QLabel(unit, self.value_holder))

    def result_value(self) -> Any:
        """The typed value in model (SI) units; raises ``ValueError`` if it is missing or invalid."""
        spec = self._spec()
        if spec is None or self._fw is None:
            raise ValueError("choose an object and a field")
        value = self.model.from_display(spec, self._fw.value())
        if value is None and not spec.optional and spec.kind in ("float", "int", "vec"):
            raise ValueError(f"{spec.label} needs a value")
        return value

    def set_value(self, shown: Any) -> None:
        self._fw.set_value(shown)


class ScenariosDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None, on_change=None) -> None:
        super().__init__(parent)
        self.api = api
        self.on_change = on_change                       # called after applying/resetting (the window refreshes)
        self.setWindowTitle("Edit Scenarios")
        self.resize(860, 560)
        self._loading = False
        self._current: Optional[str] = None
        outer = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal, self)
        outer.addWidget(split, 1)

        left = QWidget(split)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget(left)
        self.list.currentTextChanged.connect(self._on_list_changed)
        lv.addWidget(self.list, 1)
        self.buttons_left: Dict[str, QPushButton] = {}
        for key, text, slot in (("new", "New...", self.new_scenario), ("clone", "Clone...", self.clone_scenario),
                                ("rename", "Rename...", self.rename_scenario), ("delete", "Delete...", self.delete_scenario),
                                ("apply", "Apply to model", self.apply_scenario), ("reset", "Reset model", self.reset_model)):
            b = QPushButton(text, left)
            b.clicked.connect(lambda _c=False, s=slot: s())
            lv.addWidget(b)
            self.buttons_left[key] = b

        right = QWidget(split)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel(right)
        self.status.setWordWrap(True)
        rv.addWidget(self.status)
        form = QFormLayout()
        self.description = QLineEdit(right)
        self.tags = QLineEdit(right)
        self.tags.setPlaceholderText("comma separated")
        form.addRow("Description", self.description)
        form.addRow("Tags", self.tags)
        rv.addLayout(form)
        rv.addWidget(QLabel("This scenario changes:", right))
        self.table = QTableWidget(0, 4, right)
        self.table.setHorizontalHeaderLabels(["Object", "Type", "Field", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        rv.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot in (("Add override...", self.add_override_dialog), ("Remove selected", self.remove_selected),
                           ("Turn object on/off...", self.toggle_object_dialog)):
            b = QPushButton(text, right)
            b.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(b)
        row.addStretch(1)
        rv.addLayout(row)
        split.setSizes([220, 640])

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.refresh_list()

    # -- list and form ----------------------------------------------------------------------------
    def names(self) -> List[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def refresh_list(self, select: Optional[str] = None) -> None:
        keep = select or self._current
        self._loading = True
        self.list.clear()
        self.list.addItems([s.name for s in self.api.scenarios.all()])
        self._loading = False
        self._current = None
        row = self.names().index(keep) if keep in self.names() else (0 if self.list.count() else -1)
        self.list.setCurrentRow(row)
        if row < 0:
            self._load(None)

    def select(self, name: str) -> None:
        if name in self.names():
            self.list.setCurrentRow(self.names().index(name))

    def _on_list_changed(self, name: str) -> None:
        if self._loading:
            return
        if self._current is not None and not self._save_form():
            self._loading = True
            self.select(self._current)
            self._loading = False
            return
        self._current = name or None
        self._load(name or None)

    def _load(self, name: Optional[str]) -> None:
        self._loading = True
        s = self.api.scenarios.get(name) if name else None
        self.description.setText(s.description if s else "")
        self.tags.setText(", ".join(s.tags) if s else "")
        self.description.setEnabled(s is not None)
        self.tags.setEnabled(s is not None)
        self.table.setRowCount(0)
        if s is not None:
            for o in self.api.scenarios.overrides(name):
                r = self.table.rowCount()
                self.table.insertRow(r)
                ent = o["entity"]
                cells = [ent.name if ent is not None else "(missing object)", o["kind"], o["field"], repr(o["value"])]
                for c, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if c == 0:
                        item.setData(Qt.UserRole, (o["uid"], o["field"]))
                    self.table.setItem(r, c, item)
        active = self.api.scenarios.active
        self.status.setText(f"Applied to the model now: {active}" if active else "No scenario is applied to the model.")
        for key in ("rename", "delete"):
            self.buttons_left[key].setEnabled(s is not None and name != active)
        self.buttons_left["apply"].setEnabled(s is not None and active is None)
        self.buttons_left["reset"].setEnabled(active is not None)
        self.buttons_left["clone"].setEnabled(s is not None)
        self._loading = False

    def overrides_in_table(self) -> List[tuple]:
        return [(self.table.item(r, 0).text(), self.table.item(r, 2).text(), self.table.item(r, 3).text())
                for r in range(self.table.rowCount())]

    def _save_form(self) -> bool:
        """Write the description and tags of the shown scenario if they changed."""
        s = self.api.scenarios.get(self._current) if self._current else None
        if s is None:
            return True
        tags = [t.strip() for t in self.tags.text().split(",") if t.strip()]
        if self.description.text() == s.description and tags == s.tags:
            return True
        try:
            self.api.scenarios.update(s.name, description=self.description.text(), tags=tags)
            return True
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return False

    def apply(self) -> bool:
        return self._save_form()

    def _on_ok(self) -> None:
        if self._save_form():
            self.accept()

    def _guard(self, fn):
        try:
            return fn()
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None

    def _ask_name(self, title: str, label: str, text: str = "") -> Optional[str]:
        name, ok = QInputDialog.getText(self, title, label, text=text)
        return name.strip() if ok and name.strip() else None

    # -- scenario buttons -------------------------------------------------------------------------
    def new_scenario(self, name: Optional[str] = None, description: str = "") -> Any:
        if self._current is not None and not self._save_form():
            return None
        name = name or self._ask_name("New Scenario", "Name:")
        if not name:
            return None
        s = self._guard(lambda: self.api.scenarios.create(name, description))
        if s is not None:
            self._current = None
            self.refresh_list(name)
        return s

    def clone_scenario(self, new_name: Optional[str] = None) -> Any:
        if self._current is None or not self._save_form():
            return None
        new_name = new_name or self._ask_name("Clone Scenario", "Name of the copy:", f"{self._current}_copy")
        if not new_name:
            return None
        s = self._guard(lambda: self.api.scenarios.clone(self._current, new_name))
        if s is not None:
            self._current = None
            self.refresh_list(new_name)
        return s

    def rename_scenario(self, new_name: Optional[str] = None) -> Any:
        if self._current is None or not self._save_form():
            return None
        new_name = new_name or self._ask_name("Rename Scenario", "New name:", self._current)
        if not new_name or new_name == self._current:
            return None
        s = self._guard(lambda: self.api.scenarios.update(self._current, new_name=new_name))
        if s is not None:
            self._current = None
            self.refresh_list(new_name)
        return s

    def delete_scenario(self, confirm: bool = True) -> bool:
        if self._current is None:
            return False
        if confirm and QMessageBox.question(self, "Delete", f"Delete scenario {self._current}?") != QMessageBox.Yes:
            return False
        if self._guard(lambda: self.api.scenarios.delete(self._current) or True) is None:
            return False
        self._current = None
        self.refresh_list()
        return True

    def apply_scenario(self) -> bool:
        if self._current is None or not self._save_form():
            return False
        ok = self._guard(lambda: self.api.scenarios.apply(self._current) or True)
        self._after_apply()
        return bool(ok)

    def reset_model(self) -> bool:
        ok = self._guard(lambda: self.api.scenarios.reset() or True)
        self._after_apply()
        return bool(ok)

    def _after_apply(self) -> None:
        if self.on_change:
            self.on_change()
        self._load(self._current)

    # -- overrides ----------------------------------------------------------------------------------
    def add_override(self, entity: Any, field: str, value: Any) -> None:
        """Record *value* (model units) for *entity*.*field* in the selected scenario."""
        if self._current is None:
            raise ValueError("select or create a scenario first")
        self.api.scenarios.set_override(self._current, entity, field, value)
        self._load(self._current)

    def add_override_dialog(self) -> bool:
        if self._current is None:
            QMessageBox.information(self, self.windowTitle(), "Create a scenario first.")
            return False
        dlg = AddOverrideDialog(self.api, self)
        if dlg.exec() != QDialog.Accepted:
            return False
        try:
            value, entity, field = dlg.result_value(), dlg.entity(), dlg.field_combo.currentData()
            self.add_override(entity, field, value)
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, "Add Override", str(exc))
            return False
        return True

    def toggle_object(self, entity: Any, enabled: bool) -> None:
        """Scenario-specific on/off for one object (an override of its ``enabled`` flag)."""
        self.add_override(entity, "enabled", bool(enabled))

    def toggle_object_dialog(self) -> bool:
        entities = _entity_choices(self.api)
        if self._current is None or not entities:
            return False
        labels = [f"{e.name}  ({type(e).__name__})" for e in entities]
        label, ok = QInputDialog.getItem(self, "Turn Object On/Off", "Object:", labels, 0, False)
        if not ok:
            return False
        state, ok = QInputDialog.getItem(self, "Turn Object On/Off", "In this scenario it is:", ["Off", "On"], 0, False)
        if not ok:
            return False
        self._guard(lambda: self.toggle_object(entities[labels.index(label)], state == "On"))
        return True

    def remove_override(self, uid: str, field: str) -> None:
        entity = next((e for e in self.api.project.all_entities if getattr(e, "uid", None) == uid), None)
        if entity is None:                                    # the object is gone: drop the dangling row directly
            self.api.scenarios.get(self._current).remove_override(uid, field)
        else:
            self.api.scenarios.remove_override(self._current, entity, field)
        self._load(self._current)

    def remove_selected(self) -> int:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        keys = [self.table.item(r, 0).data(Qt.UserRole) for r in rows]
        for uid, field in keys:
            self._guard(lambda u=uid, f=field: self.remove_override(u, f))
        return len(keys)
