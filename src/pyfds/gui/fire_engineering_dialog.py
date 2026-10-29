"""Tools > Fire Engineering Calculators: the hand calculations of ``api.engineering`` in one dialog.

Pick a calculation, fill in its inputs (SI units), press Calculate; every number the calculation returns is listed. Until
now these were reachable only from scripts and the AI assistant. Nothing here changes the model.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

#: one input: (keyword, label, units, default, minimum, maximum)
Field = Tuple[str, str, str, float, float, float]
#: one calculation: (title, reference, inputs, function of (engineering manager, values))
Calc = Tuple[str, str, Sequence[Field], Callable[[Any, Dict[str, float]], Any]]

_HRR: Field = ("hrr_kw", "Heat release rate", "kW", 1000.0, 1.0, 1e7)

CALCULATIONS: List[Calc] = [
    ("Fire size and cell size", "D* and D*/dx (FDS User Guide; NUREG-1824)", [_HRR],
     lambda e, v: e.recommend_cell_size(v["hrr_kw"])),
    ("Plume (Heskestad)", "Heskestad plume centreline (SFPE Handbook)",
     [_HRR, ("z", "Height above the fire", "m", 3.0, 0.1, 100.0)],
     lambda e, v: e.heskestad_plume(v["hrr_kw"], v["z"])),
    ("Ceiling jet (Alpert)", "Alpert 1972 ceiling jet",
     [_HRR, ("r", "Radial distance", "m", 2.0, 0.0, 100.0), ("H", "Ceiling height above the fire", "m", 3.0, 0.1, 50.0)],
     lambda e, v: e.ceiling_jet(v["hrr_kw"], v["r"], v["H"])),
    ("Smoke filling time (NFPA 92)", "NFPA 92 steady fire filling time",
     [_HRR, ("floor_area_m2", "Floor area", "m²", 100.0, 1.0, 1e6), ("room_height_m", "Room height", "m", 5.0, 0.5, 200.0),
      ("z_interface_m", "Smoke layer height", "m", 2.0, 0.0, 200.0)],
     lambda e, v: e.smoke_filling_time(v["hrr_kw"], v["floor_area_m2"], v["room_height_m"], v["z_interface_m"])),
    ("Two-layer zone model", "Two-zone room filling",
     [_HRR, ("room_height_m", "Room height", "m", 3.0, 0.5, 200.0), ("floor_area_m2", "Floor area", "m²", 25.0, 1.0, 1e6)],
     lambda e, v: e.two_layer_zone_model(v["hrr_kw"], v["room_height_m"], v["floor_area_m2"])),
    ("Heat detector response", "Alpert ceiling jet + RTI detector model",
     [_HRR, ("ceiling_height_m", "Ceiling height", "m", 3.0, 0.5, 50.0),
      ("detector_radial_distance_m", "Detector distance from the fire axis", "m", 2.0, 0.0, 50.0)],
     lambda e, v: e.detector_response_time(v["hrr_kw"], v["ceiling_height_m"], v["detector_radial_distance_m"])),
    ("Tunnel critical velocity (Kennedy)", "Kennedy 1996 critical ventilation velocity",
     [_HRR, ("tunnel_height_m", "Tunnel height", "m", 6.0, 1.0, 50.0), ("tunnel_width_m", "Tunnel width", "m", 10.0, 1.0, 100.0)],
     lambda e, v: e.critical_velocity(v["hrr_kw"], v["tunnel_height_m"], v["tunnel_width_m"])),
]


def result_rows(result: Any) -> List[Tuple[str, str]]:
    """``(name, value)`` for every number or short text a calculation returned (dataclass, object or plain number)."""
    if isinstance(result, (int, float)):
        return [("result", _fmt(result))]
    if dataclasses.is_dataclass(result):
        items = dataclasses.asdict(result).items()
    else:
        items = vars(result).items() if hasattr(result, "__dict__") else []
    rows = []
    for name, value in items:
        if name.startswith("_"):
            continue
        if isinstance(value, (int, float, str, bool)) or value is None:
            rows.append((name.replace("_", " "), _fmt(value)))
        elif isinstance(value, (list, tuple)) and value and all(isinstance(x, (int, float)) for x in value) and len(value) <= 6:
            rows.append((name.replace("_", " "), ", ".join(_fmt(x) for x in value)))
        elif isinstance(value, (list, tuple)) and value and all(isinstance(x, str) for x in value):
            rows.append((name.replace("_", " "), "; ".join(value)))
    return rows


def _fmt(value: Any) -> str:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return str(value)
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            return str(value)
        return f"{value:.4g}"
    return str(value)


class FireEngineeringDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Fire Engineering Calculators")
        self.resize(560, 520)
        v = QVBoxLayout(self)
        self.choice = QComboBox(self)
        for title, *_ in CALCULATIONS:
            self.choice.addItem(title)
        self.choice.currentIndexChanged.connect(self._show_inputs)
        v.addWidget(self.choice)
        self.reference = QLabel(self)
        self.reference.setWordWrap(True)
        v.addWidget(self.reference)
        self.form_box = QWidget(self)
        self.form = QFormLayout(self.form_box)
        v.addWidget(self.form_box)
        self.calc_button = QPushButton("Calculate", self)
        self.calc_button.clicked.connect(self.calculate)
        v.addWidget(self.calc_button)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Quantity", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        v.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._inputs: Dict[str, QDoubleSpinBox] = {}
        self._show_inputs(0)

    def _show_inputs(self, index: int) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        _title, ref, fields, _fn = CALCULATIONS[index]
        self.reference.setText(f"Method: {ref}. Inputs in SI units.")
        self._inputs = {}
        for key, label, units, default, lo, hi in fields:
            box = QDoubleSpinBox(self.form_box)
            box.setRange(lo, hi)
            box.setDecimals(3)
            box.setValue(default)
            box.setSuffix(f" {units}")
            self.form.addRow(label, box)
            self._inputs[key] = box
        self.table.setRowCount(0)
        self.message.clear()

    def values(self) -> Dict[str, float]:
        return {k: box.value() for k, box in self._inputs.items()}

    def calculate(self) -> List[Tuple[str, str]]:
        """Run the chosen calculation and list its results; an input the method rejects is shown, not raised."""
        _title, _ref, _fields, fn = CALCULATIONS[self.choice.currentIndex()]
        try:
            rows = result_rows(fn(self.api.engineering, self.values()))
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            self.table.setRowCount(0)
            self.message.setText(f"Cannot calculate: {exc}")
            return []
        self.table.setRowCount(len(rows))
        for r, (name, value) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(value))
        self.table.resizeColumnToContents(0)
        self.message.setText("Hand calculation for checking a model; it does not replace the FDS run.")
        return rows
