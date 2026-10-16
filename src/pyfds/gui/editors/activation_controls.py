"""Edit Activation Controls (plan step F5, CTL-01): the logic that switches objects on and off.

Left, the controls. Right, the control's function (grouped by kind), its inputs (devices and other controls, never a
loop), the parameters that function needs, a live list of problems, and the objects it drives. All logic is in
``api.controls``; Apply saves everything as ONE undo step.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)


from .activation_controls_ops import ControlOperationsMixin  # noqa: E402

#: parameters each function uses besides inputs (everything else is hidden for it)
_PARAMS = {"TIME_DELAY": ("delay",), "DEADBAND": ("deadband", "initial_state"), "ONLY": ("n",), "CUSTOM": ("ramp_id",),
           "PID": ("setpoint", "constant")}
_COMMON = ("latch", "initial_state")
_KINDS = ["Detector-based", "Time-based", "Deadband-based", "Mathematical", "Custom"]


class ActivationControlsDialog(ControlOperationsMixin, QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None, select: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Edit Activation Controls")
        self.resize(900, 640)
        self._current: Optional[Any] = None
        self._loading = False
        outer = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal, self)
        outer.addWidget(split, 1)

        left = QWidget(split)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget(left)
        self.list.currentTextChanged.connect(self._on_list_changed)
        lv.addWidget(self.list, 1)
        for text, slot in (("New", self.new_control), ("Clone", self.clone_control), ("Rename...", self.rename_control),
                           ("Delete...", self.delete_control)):
            b = QPushButton(text, left)
            b.clicked.connect(lambda _c=False, s=slot: s())
            lv.addWidget(b)

        right = QWidget(split)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        top = QFormLayout()
        self.kind_combo = QComboBox(right)
        self.kind_combo.addItems(_KINDS)
        self.kind_combo.activated.connect(lambda _i: self._on_kind())
        self.function_combo = QComboBox(right)
        self.function_combo.activated.connect(lambda _i: self._on_function())
        top.addRow("Kind", self.kind_combo)
        top.addRow("Function", self.function_combo)
        rv.addLayout(top)
        self.description = QLabel(right)
        self.description.setWordWrap(True)
        rv.addWidget(self.description)

        rv.addWidget(QLabel("Inputs (devices and other controls)", right))
        self.inputs = QListWidget(right)
        self.inputs.setMaximumHeight(150)
        self.inputs.itemChanged.connect(lambda _i: self._changed())
        rv.addWidget(self.inputs)

        self.params_form = QFormLayout()
        self.delay_box = self._dspin("delay", 0.0, 1e6)
        self.setpoint_box = self._dspin("setpoint", -1e9, 1e9)
        self.constant_box = self._dspin("constant", -1e9, 1e9)
        self.n_box = QSpinBox(right)
        self.n_box.setRange(0, 10000)
        self.n_box.valueChanged.connect(lambda _v: self._changed())
        self.deadband_low = self._dspin("deadband low", -1e9, 1e9)
        self.deadband_high = self._dspin("deadband high", -1e9, 1e9)
        self.ramp_combo = QComboBox(right)
        self.ramp_combo.currentTextChanged.connect(lambda _t: self._changed())
        self.latch_check = QCheckBox("Stay on once switched on (latch)", right)
        self.initial_check = QCheckBox("Starts on", right)
        for c in (self.latch_check, self.initial_check):
            c.toggled.connect(lambda _b: self._changed())
        self._rows = {"delay": ("Delay (s)", self.delay_box), "setpoint": ("Set point", self.setpoint_box),
                      "constant": ("Constant", self.constant_box), "n": ("Number of inputs on", self.n_box),
                      "deadband": ("Deadband low / high", self._pair(self.deadband_low, self.deadband_high)),
                      "ramp_id": ("Ramp", self.ramp_combo), "latch": ("", self.latch_check),
                      "initial_state": ("", self.initial_check)}
        for key, (label, widget) in self._rows.items():
            self.params_form.addRow(label, widget)
        rv.addLayout(self.params_form)

        self.problems_label = QLabel(right)
        self.problems_label.setWordWrap(True)
        rv.addWidget(self.problems_label)

        box = QGroupBox("Objects this control switches", right)
        bv = QVBoxLayout(box)
        self.driven = QListWidget(box)
        self.driven.setSelectionMode(QListWidget.ExtendedSelection)
        self.driven.setMaximumHeight(110)
        bv.addWidget(self.driven)
        row = QHBoxLayout()
        self.add_object_button = QPushButton("Add object...", box)
        self.add_object_button.clicked.connect(lambda _c=False: self.add_object_dialog())
        self.remove_object_button = QPushButton("Remove selected", box)
        self.remove_object_button.clicked.connect(lambda _c=False: self.remove_selected_objects())
        row.addWidget(self.add_object_button)
        row.addWidget(self.remove_object_button)
        row.addStretch(1)
        bv.addLayout(row)
        self.used_label = QLabel(box)
        self.used_label.setWordWrap(True)
        bv.addWidget(self.used_label)
        rv.addWidget(box)
        split.setSizes([220, 680])

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda: self._apply_quietly())
        outer.addWidget(self.buttons)
        self.refresh_list(select)

    # -- small builders -------------------------------------------------------------------------------------
    def _dspin(self, tip: str, lo: float, hi: float) -> QDoubleSpinBox:
        b = QDoubleSpinBox(self)
        b.setRange(lo, hi)
        b.setDecimals(4)
        b.setToolTip(tip)
        b.valueChanged.connect(lambda _v: self._changed())
        return b

    def _pair(self, a: QWidget, b: QWidget) -> QWidget:
        w = QWidget(self)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(b)
        return w

    # -- the list ---------------------------------------------------------------------------------------------
    def names(self) -> List[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def refresh_list(self, select: Optional[str] = None) -> None:
        keep = select or (self._current.name if self._current is not None else None)
        self._loading = True
        self.list.clear()
        self.list.addItems([c.name for c in self.api.controls.all()])
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
        if self._current is not None and not self._apply_quietly():
            self._loading = True
            self.select(self._current.name)
            self._loading = False
            return
        self._current = self.api.controls.get(name) if name else None
        self._load(self._current)

    # -- showing a control --------------------------------------------------------------------------------------
    def _functions_of(self, kind: str) -> List[str]:
        return [f["name"] for f in self.api.controls.functions() if f["kind"] == kind]

    def _function(self, name: str) -> Optional[Dict[str, Any]]:
        return next((f for f in self.api.controls.functions() if f["name"] == (name or "").strip().upper()), None)

    def _load(self, c: Optional[Any]) -> None:
        self._loading = True
        enabled = c is not None
        for w in (self.kind_combo, self.function_combo, self.inputs, self.add_object_button, self.remove_object_button):
            w.setEnabled(enabled)
        self.inputs.clear()
        self.driven.clear()
        if c is None:
            self.description.setText("")
            self.problems_label.setText("")
            self.used_label.setText("")
            self._loading = False
            return
        fn = self._function(c.function_type)
        kind = fn["kind"] if fn else "Custom"
        self.kind_combo.setCurrentText(kind)
        self._fill_functions(kind, c.function_type)
        chosen = set(self.api.controls.inputs_of(c))
        for name in self.api.controls.input_candidates(c):
            it = QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if name in chosen else Qt.Unchecked)
            self.inputs.addItem(it)
        for name in chosen - set(self.api.controls.input_candidates(c)):         # an input that no longer exists
            it = QListWidgetItem(f"{name} (missing)")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, name)
            self.inputs.addItem(it)
        self.delay_box.setValue(c.delay or 0.0)
        self.setpoint_box.setValue(c.setpoint or 0.0)
        self.constant_box.setValue(c.constant or 0.0)
        self.n_box.setValue(c.n or 0)
        lo, hi = c.deadband or (0.0, 0.0)
        self.deadband_low.setValue(lo)
        self.deadband_high.setValue(hi)
        self.ramp_combo.clear()
        self.ramp_combo.addItems([""] + sorted({r.name for r in self.api.ramps.all()}))
        self.ramp_combo.setCurrentText(c.ramp_id or "")
        self.latch_check.setChecked(bool(c.latch))
        self.initial_check.setChecked(bool(c.initial_state))
        self._load_objects(c)
        self._loading = False
        self._show_params()
        self._refresh_problems()

    def _fill_functions(self, kind: str, current: str) -> None:
        self.function_combo.clear()
        names = self._functions_of(kind)
        if current.upper() not in names:
            names.append(current.upper())                      # an imported function outside the usual table
        self.function_combo.addItems(names)
        self.function_combo.setCurrentText(current.upper())

    def _load_objects(self, c: Any) -> None:
        self.driven.clear()
        for kind, e in self.api.controls.controlled(c):
            it = QListWidgetItem(f"{e.name}  ({kind})")
            it.setData(Qt.UserRole, e)
            self.driven.addItem(it)
        users = [o.name for o in self.api.controls.used_as_input(c)]
        self.used_label.setText("Used as an input by: " + ", ".join(users) if users else "Not used as an input by another control.")

    def _show_params(self) -> None:
        fn = self.function_combo.currentText().upper()
        wanted = set(_PARAMS.get(fn, ())) | set(_COMMON)
        for key, (label, widget) in self._rows.items():
            show = key in wanted
            widget.setVisible(show)
            lab = self.params_form.labelForField(widget)
            if lab is not None:
                lab.setVisible(show)
        f = self._function(fn)
        self.description.setText(f["description"] if f else "Unknown function (kept as it is)")

    # -- pending values -----------------------------------------------------------------------------------------
    def checked_inputs(self) -> List[str]:
        out = []
        for i in range(self.inputs.count()):
            it = self.inputs.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole) or it.text())
        return out

    def pending(self) -> Dict[str, Any]:
        fn = self.function_combo.currentText().upper()
        wanted = set(_PARAMS.get(fn, ())) | set(_COMMON)
        out: Dict[str, Any] = {"function_type": fn, "latch": self.latch_check.isChecked(),
                               "initial_state": self.initial_check.isChecked()}
        out["delay"] = self.delay_box.value() if "delay" in wanted else (self._current.delay if self._current else 0.0)
        out["setpoint"] = self.setpoint_box.value() if "setpoint" in wanted else (self._current.setpoint if self._current else None)
        out["constant"] = self.constant_box.value() if "constant" in wanted else (self._current.constant if self._current else None)
        out["n"] = (self.n_box.value() or None) if "n" in wanted else (self._current.n if self._current else None)
        out["deadband"] = ((self.deadband_low.value(), self.deadband_high.value()) if "deadband" in wanted
                           else (self._current.deadband if self._current else None))
        out["ramp_id"] = (self.ramp_combo.currentText() or None) if "ramp_id" in wanted else (self._current.ramp_id if self._current else None)
        return out

    def _probe(self) -> Any:
        probe = self._current.model_copy(deep=True)
        for k, v in self.pending().items():
            setattr(probe, k, v)
        probe.input_ids, probe.input_id = self.checked_inputs() or None, None
        return probe

    def _refresh_problems(self) -> None:
        if self._current is None:
            return
        found = self.api.controls.problems(self._probe())
        self.problems_label.setStyleSheet("color: #b3261e;" if found else "color: #15803d;")
        self.problems_label.setText("\n".join("! " + p for p in found) if found else "This control is complete.")

    def _changed(self) -> None:
        if not self._loading:
            self._refresh_problems()

    def _on_kind(self) -> None:
        self._fill_functions(self.kind_combo.currentText(), self._functions_of(self.kind_combo.currentText())[0])
        self._on_function()

    def _on_function(self) -> None:
        self._show_params()
        self._changed()

    def set_function(self, name: str) -> None:
        """Choose a function (switching to its kind) without saving."""
        f = self._function(name)
        self._loading = True
        self.kind_combo.setCurrentText(f["kind"] if f else "Custom")
        self._fill_functions(f["kind"] if f else "Custom", name)
        self._loading = False
        self._on_function()

    def set_inputs(self, names: List[str]) -> None:
        for i in range(self.inputs.count()):
            it = self.inputs.item(i)
            it.setCheckState(Qt.Checked if (it.data(Qt.UserRole) or it.text()) in names else Qt.Unchecked)

    def is_dirty(self) -> bool:
        c = self._current
        if c is None:
            return False
        p = self.pending()
        return any((getattr(c, k) or None) != (v or None) if not isinstance(v, bool) else bool(getattr(c, k)) != v
                   for k, v in p.items()) or self.checked_inputs() != self.api.controls.inputs_of(c)

    # -- apply --------------------------------------------------------------------------------------------------
    def apply(self) -> bool:
        """Save the shown control as one undo step. Raises ``ValueError`` if it is not valid."""
        c = self._current
        if c is None or not self.is_dirty():
            return True
        found = self.api.controls.problems(self._probe())
        if found:
            raise ValueError("; ".join(found))
        p = self.pending()
        with self.api.history.transaction(f"edit control {c.name}"):
            self.api.controls.update(c, **{k: v for k, v in p.items() if (getattr(c, k) or None) != (v or None)
                                           or isinstance(v, bool) and bool(getattr(c, k)) != v})
            if self.checked_inputs() != self.api.controls.inputs_of(c):
                self.api.controls.set_inputs(c, self.checked_inputs())
        self._load(c)
        return True

    def _apply_quietly(self) -> bool:
        try:
            return self.apply()
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return False

    def _on_ok(self) -> None:
        if self._apply_quietly():
            self.accept()
