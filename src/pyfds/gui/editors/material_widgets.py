"""Widgets for Edit Materials: the Byproducts tab and the pyrolysis calculator (plan step F5)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import material_calc


class ByproductsWidget(QWidget):
    """What a reacting material turns into: gases (species and mass yield) and a residue (a material and its yield)."""

    changed = Signal()

    def __init__(self, species_choices: List[str], residue_choices: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._species = species_choices
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Gases given off, as a fraction of the reacted mass", self))
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Species", "Yield"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda _i: self._edited())
        v.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add gas", self)
        add.clicked.connect(lambda _c=False: self.add_gas("", None))
        rem = QPushButton("Remove selected", self)
        rem.clicked.connect(lambda _c=False: self._remove())
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.addLayout(row)
        form = QFormLayout()
        self.residue_yield = QLineEdit(self)
        self.residue_yield.setPlaceholderText("0")
        self.residue_yield.textChanged.connect(lambda _t: self._edited())
        form.addRow("Residue yield", self.residue_yield)
        self.residue_material = QComboBox(self)
        self.residue_material.setEditable(True)
        self.residue_material.addItems([""] + residue_choices)
        self.residue_material.currentTextChanged.connect(lambda _t: self._edited())
        form.addRow("Residue material", self.residue_material)
        v.addLayout(form)
        self.total = QLabel("", self)
        v.addWidget(self.total)

    # -- reading and writing -----------------------------------------------------------------------
    def add_gas(self, species: str, value: Optional[float]) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        combo = QComboBox(self.table)
        combo.setEditable(True)
        combo.addItems([""] + self._species)
        combo.setCurrentText(species)
        combo.currentTextChanged.connect(lambda _t: self._edited())
        self.table.setCellWidget(r, 0, combo)
        self.table.setItem(r, 1, QTableWidgetItem("" if value is None else f"{value:.10g}"))
        self._edited()

    def load(self, species: Optional[List[str]], yields: Optional[List[float]], residue: Optional[float],
             residue_material: Optional[str]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for s, y in zip(species or [], yields or []):
            self.add_gas(s, y)
        self.table.blockSignals(False)
        self.residue_yield.setText("" if not residue else f"{residue:.10g}")
        self.residue_material.setCurrentText(residue_material or "")
        self._edited(silent=True)

    def gases(self) -> Dict[str, Any]:
        """``{"species": [...], "yields": [...]}`` of the complete rows (a row needs a species and a number)."""
        sp, ys = [], []
        for r in range(self.table.rowCount()):
            name = self.table.cellWidget(r, 0).currentText().strip()
            text = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if not name and not text:
                continue
            try:
                y = float(text.replace(",", "."))
            except ValueError:
                continue
            if name:
                sp.append(name)
                ys.append(y)
        return {"species": sp, "yields": ys}

    def residue(self) -> Optional[float]:
        t = self.residue_yield.text().strip().replace(",", ".")
        try:
            return float(t) if t else None
        except ValueError:
            return None

    def residue_id(self) -> Optional[str]:
        return self.residue_material.currentText().strip() or None

    def problems(self) -> List[str]:
        """Rows or values that cannot be read (the model check covers the sums)."""
        out = []
        for r in range(self.table.rowCount()):
            name = self.table.cellWidget(r, 0).currentText().strip()
            text = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if name or text:
                try:
                    float(text.replace(",", "."))
                except ValueError:
                    out.append(f"gas row {r + 1}: the yield is not a number")
                if not name:
                    out.append(f"gas row {r + 1}: choose a species")
        t = self.residue_yield.text().strip()
        if t and self.residue() is None:
            out.append("the residue yield is not a number")
        return out

    def _remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
        self._edited()

    def _edited(self, silent: bool = False) -> None:
        g = self.gases()
        total = sum(g["yields"]) + (self.residue() or 0.0)
        left = 1.0 - total
        self.total.setText(f"Total {total:.3f}; unaccounted {max(left, 0.0):.3f}" +
                           ("   - more than 1, reduce a yield" if left < -1e-6 else ""))
        if not silent:
            self.changed.emit()


class PyrolysisCalculatorDialog(QDialog):
    """Work out a reaction's rate from a rate curve, a TGA peak, FDS's own fit, or typed values."""

    def __init__(self, api: Any, material: Any, targets: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api, self.material = api, material
        self.setWindowTitle(f"Pyrolysis Reaction - {material.name}")
        self.resize(520, 460)
        self._result: Optional[material_calc.CalcResult] = None
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.target = QComboBox(self)
        self.target.addItems(targets)
        form.addRow("Reaction", self.target)
        self.method = QComboBox(self)
        for key, label in material_calc.METHODS.items():
            self.method.addItem(label, key)
        self.method.currentIndexChanged.connect(self._on_method)
        form.addRow("Rate given by", self.method)
        self.order = QLineEdit("1", self)
        self.order.textChanged.connect(lambda _t: self.recalculate())
        form.addRow("Reaction order n", self.order)
        v.addLayout(form)
        self.pages = QStackedWidget(self)
        self.edits: Dict[str, QLineEdit] = {}
        self.texts: Dict[str, QPlainTextEdit] = {}
        self.pages.addWidget(self._page([("reference_temperature", "Reference temperature (C)"),
                                         ("heating_rate", "Heating rate (K/min)"), ("pyrolysis_range", "Pyrolysis range (K)")]))
        fit = self._page([], note="One measurement per line: temperature (C), rate (1/s) and, if you have it, "
                                  "remaining mass fraction.", text="fit")
        self.pages.addWidget(fit)
        self.pages.addWidget(self._page([("heating_rate", "Heating rate (K/min)"), ("peak_temperature", "Peak temperature (C)"),
                                         ("e", "Activation energy E (J/mol), if known")],
                                        note="Without E, give other runs below: heating rate (K/min) and peak temperature "
                                             "(C) on each line.", text="other_runs"))
        self.pages.addWidget(self._page([("a", "A (1/s)"), ("e", "E (J/mol)")], prefix="direct_"))
        v.addWidget(self.pages, 1)
        self.result_label = QLabel("", self)
        self.result_label.setWordWrap(True)
        v.addWidget(self.result_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self.recalculate()

    def _page(self, fields, note: str = "", text: Optional[str] = None, prefix: str = "") -> QWidget:
        page = QWidget(self)
        f = QFormLayout(page)
        if note:
            lab = QLabel(note, page)
            lab.setWordWrap(True)
            f.addRow(lab)
        for key, label in fields:
            e = QLineEdit(page)
            e.textChanged.connect(lambda _t: self.recalculate())
            self.edits[prefix + key if prefix else f"{self.pages.count()}:{key}"] = e
            f.addRow(label, e)
        if text:
            t = QPlainTextEdit(page)
            t.setMinimumHeight(110)
            t.textChanged.connect(self.recalculate)
            self.texts[text] = t
            f.addRow(t)
        return page

    def _on_method(self, _i: int) -> None:
        self.pages.setCurrentIndex(self.method.currentIndex())
        self.recalculate()

    def _field(self, key: str) -> Optional[str]:
        idx = self.pages.currentIndex()
        e = self.edits.get(f"direct_{key}" if idx == 3 else f"{idx}:{key}")
        return e.text().strip() if e is not None else None

    def inputs(self) -> Dict[str, Any]:
        """What the current page holds, as ``material_calc.compute`` expects it."""
        m = self.method.currentData()
        out: Dict[str, Any] = {"n": self.order.text().strip() or "1"}

        def num(key):
            t = self._field(key)
            return float(t.replace(",", ".")) if t else None
        if m == "match":
            out.update(reference_temperature=num("reference_temperature"), heating_rate=num("heating_rate"),
                       pyrolysis_range=num("pyrolysis_range"))
        elif m == "direct":
            out.update(a=num("a"), e=num("e"))
        elif m == "fit":
            rows = material_calc.parse_pairs(self.texts["fit"].toPlainText())
            if rows and any(len(r) < 2 for r in rows):
                raise ValueError("each line needs a temperature and a rate")
            out.update(temperatures=[r[0] for r in rows], rates=[r[1] for r in rows])
            if rows and all(len(r) > 2 for r in rows):
                out["remaining_mass"] = [r[2] for r in rows]
        else:
            out.update(heating_rate=num("heating_rate"), peak_temperature=num("peak_temperature"), e=num("e"),
                       other_runs=material_calc.parse_pairs(self.texts["other_runs"].toPlainText()))
        out["n"] = float(str(out["n"]).replace(",", "."))
        return out

    def recalculate(self) -> None:
        if not hasattr(self, "buttons"):
            return
        self._result = None
        try:
            self._result = material_calc.compute(self.api, self.material, self.method.currentData(), self.inputs())
            self.result_label.setStyleSheet("")
            self.result_label.setText(self._result.note)
        except ValueError as exc:
            self.result_label.setStyleSheet("color: #b3261e;")
            self.result_label.setText(str(exc))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._result is not None)

    def result(self) -> Optional[material_calc.CalcResult]:
        return self._result

    def target_index(self) -> int:
        return self.target.currentIndex()

    def method_key(self) -> str:
        return self.method.currentData()
