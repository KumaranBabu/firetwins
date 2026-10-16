"""Simulation Parameters (plan step F5): one tab per global namelist (&TIME, &DUMP, &MISC, &PRES, &RADI), every typed
field in the project's display units, a table for additional FDS keywords, and Reset to defaults.

All logic is in ``api.sim``; Apply checks every tab first and then saves all of them as ONE undo step.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .model import UNIT_KINDS, EntityEditorModel, FieldSpec, _kind_of
from .widgets import FieldWidget, make_field_widget

# name -> (label, units, tip). Anything not listed gets a label made from its name.
_INFO = {
    "t_begin": ("Start time", "s", "T_BEGIN: simulation clock at the start"),
    "t_end": ("End time", "s", "T_END: when the run stops"),
    "dt": ("Initial time step", "s", "DT: first time step (FDS adjusts it); leave empty for the automatic value"),
    "restrict_time_step": ("Restrict time step", "", "RESTRICT_TIME_STEP: never let FDS take a step above DT"),
    "dt_slcf": ("Slice interval", "s", "DT_SLCF"), "dt_pl3d": ("Plot3D interval", "s", "DT_PL3D"),
    "dt_bndf": ("Boundary file interval", "s", "DT_BNDF"), "dt_isof": ("Isosurface interval", "s", "DT_ISOF"),
    "dt_devc": ("Device interval", "s", "DT_DEVC"), "dt_ctrl": ("Control interval", "s", "DT_CTRL"),
    "dt_restart": ("Restart file interval", "s", "DT_RESTART (FDS default 200 s)"),
    "dt_hrr": ("HRR file interval", "s", "DT_HRR"), "dt_mass": ("Mass file interval", "s", "DT_MASS"),
    "plot3d": ("Write Plot3D", "", "PLOT3D"), "smoke3d": ("Write 3D smoke", "", "SMOKE3D"),
    "gvec": ("Gravity vector", "m/s2", "GVEC: x, y, z components"),
    "tmpa": ("Ambient temperature", "°C", "TMPA"), "humidity": ("Relative humidity", "%", "HUMIDITY"),
    "p_inf": ("Ambient pressure", "Pa", "P_INF"), "u0": ("Wind U0", "m/s", "U0"), "v0": ("Wind V0", "m/s", "V0"),
    "w0": ("Wind W0", "m/s", "W0"), "turbulence_model": ("Turbulence model", "", "TURBULENCE_MODEL"),
    "dns": ("Direct numerical simulation", "", "DNS: resolve turbulence instead of modelling it"),
    "openmp_threads": ("OpenMP threads", "", "OPENMP_THREADS"),
    "solver": ("Pressure solver", "", "SOLVER"),
    "velocity_tolerance": ("Velocity tolerance", "", "VELOCITY_TOLERANCE"),
    "number_radiation_angles": ("Radiation angles", "", "NUMBER_RADIATION_ANGLES"),
    "time_step_increment": ("Radiation time step increment", "", "TIME_STEP_INCREMENT"),
}
_ENUMS = {"turbulence_model": ["DEARDORFF", "CONSTANT SMAGORINSKY", "DYNAMIC SMAGORINSKY", "VREMAN"],
          "solver": ["FFT", "GLMAT", "ULMAT", "UGLMAT", "SCARC"]}
_UNITS_KIND = {"°C": "temperature", "Pa": "pressure", "m/s": "velocity"}


def specs_for(api: Any, key: str) -> List[FieldSpec]:
    """FieldSpecs for the typed fields of one parameter block."""
    obj = api.sim.get(key)
    out: List[FieldSpec] = []
    for name, info in type(obj).model_fields.items():
        if name == "fds_extra":
            continue
        k = _kind_of(info.annotation)
        if k is None:
            continue
        kind, length, int_vec, optional = k
        label, units, tip = _INFO.get(name, (name.replace("_", " ").capitalize(), "", name.upper()))
        if name in _ENUMS and kind == "str":
            kind = "enum"
        out.append(FieldSpec(name, label, kind, units, UNIT_KINDS.get(units) or _UNITS_KIND.get(units), tip,
                             key, False, list(_ENUMS.get(name, [])), None, None, length, int_vec, None, optional))
    return out


class SimulationParametersDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.model = EntityEditorModel(api, "meshes")           # only for unit conversion of field values
        self.setWindowTitle("Simulation Parameters")
        self.resize(640, 640)
        self._widgets: Dict[str, Dict[str, FieldWidget]] = {}
        self._tables: Dict[str, QTableWidget] = {}
        self._specs: Dict[str, Dict[str, FieldSpec]] = {}
        v = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        v.addWidget(self.tabs, 1)
        for b in api.sim.blocks():
            self._build_tab(b["key"], b["label"], b["namelist"])
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda: self._apply_quietly())
        v.addWidget(self.buttons)

    # -- building ---------------------------------------------------------------------------------------
    def _build_tab(self, key: str, label: str, namelist: str) -> None:
        page = QWidget(self.tabs)
        v = QVBoxLayout(page)
        fields = QWidget(page)                       # the fields scroll; the keyword table and buttons stay in view
        form = QFormLayout(fields)
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setWidget(fields)
        v.addWidget(scroll, 3)
        self._widgets[key], self._specs[key] = {}, {}
        for spec in specs_for(self.api, key):
            fw = make_field_widget(spec, lambda _c: [], page)
            fw.set_value(self.model.to_display(spec, getattr(self.api.sim.get(key), spec.name)))
            unit = self.model.unit_label(spec)
            form.addRow(f"{spec.label} ({unit})" if unit else spec.label, fw.widget)
            fw.widget.setToolTip(spec.description)
            self._widgets[key][spec.name] = fw
            self._specs[key][spec.name] = spec
        v.addWidget(QLabel(f"Additional {namelist} keywords", page))
        table = QTableWidget(0, 2, page)
        table.setHorizontalHeaderLabels(["FDS keyword", "Value"])
        table.horizontalHeader().setStretchLastSection(True)
        for name, value in self.api.sim.extras(key).items():
            self._add_row(table, name, value)
        self._tables[key] = table
        table.setMaximumHeight(130)
        v.addWidget(table, 1)
        row = QHBoxLayout()
        for text, slot in (("Add keyword", lambda t=table: self._add_row(t, "", "")),
                           ("Remove selected", lambda t=table: self._remove_rows(t)),
                           ("Reset to defaults", lambda k=key: self.reset_block(k))):
            b = QPushButton(text, page)
            b.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.tabs.addTab(page, label)

    @staticmethod
    def _add_row(table: QTableWidget, key: str, value: str) -> None:
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(key))
        table.setItem(r, 1, QTableWidgetItem(value))

    @staticmethod
    def _remove_rows(table: QTableWidget) -> None:
        for r in sorted({i.row() for i in table.selectedIndexes()}, reverse=True):
            table.removeRow(r)

    # -- values -----------------------------------------------------------------------------------------
    def field_widget(self, block: str, name: str) -> FieldWidget:
        return self._widgets[block][name]

    def block_names(self) -> List[str]:
        return list(self._widgets)

    def extras_in_table(self, block: str) -> Dict[str, str]:
        t, out = self._tables[block], {}
        for r in range(t.rowCount()):
            k = (t.item(r, 0).text() if t.item(r, 0) else "").strip().upper()
            if k:
                out[k] = (t.item(r, 1).text() if t.item(r, 1) else "").strip()
        return out

    def changes(self, block: str) -> Dict[str, Any]:
        """Model values (SI) of the fields that differ from the project's."""
        out: Dict[str, Any] = {}
        current = self.api.sim.values(block)
        for name, fw in self._widgets[block].items():
            spec = self._specs[block][name]
            new = self.model.from_display(spec, fw.value())
            if new is None and not spec.optional and spec.kind in ("float", "int", "vec"):
                raise ValueError(f"{spec.label} needs a value")
            old = current[name]
            if isinstance(old, (list, tuple)) and new is not None:
                same = list(old) == list(new)
            else:
                same = old == new
            if not same:
                out[name] = new
        return out

    def is_dirty(self) -> bool:
        try:
            return any(self.changes(b) or self.extras_in_table(b) != self.api.sim.extras(b) for b in self._widgets)
        except ValueError:
            return True

    def problems(self) -> List[str]:
        found: List[str] = []
        for b in self._widgets:
            try:
                found += [f"{self.tabs.tabText(self.block_names().index(b))}: {p}"
                          for p in self.api.sim.check(b, **self.changes(b))]
            except ValueError as exc:
                found.append(str(exc))
        return found

    def apply(self) -> Dict[str, Dict[str, Any]]:
        """Check every tab, then save all changes as one undo step. Raises ``ValueError`` listing the problems."""
        found = self.problems()
        if found:
            raise ValueError("\n".join(found))
        done: Dict[str, Dict[str, Any]] = {}
        with self.api.history.transaction("edit simulation parameters"):
            for b in self._widgets:
                ch = self.changes(b)
                if ch:
                    self.api.sim.update(b, **ch)
                    done[b] = ch
                table = self.extras_in_table(b)
                if table != self.api.sim.extras(b):
                    self.api.sim.set_extras(b, table)
                    done.setdefault(b, {})["extras"] = table
        return done

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

    def reset_block(self, block: str) -> None:
        """Show the defaults in the tab (saved by Apply/OK; the additional keywords are kept)."""
        for name, value in self.api.sim.defaults(block).items():
            self._widgets[block][name].set_value(self.model.to_display(self._specs[block][name], value))
