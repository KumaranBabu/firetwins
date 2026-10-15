"""Type-specific parts of the collection editor (plan step F5): the surface-type selector and live check on Edit
Surfaces; the Byproducts tab and the pyrolysis calculator on Edit Materials. Mixed into ``EntityCollectionEditor``."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .material_widgets import ByproductsWidget, PyrolysisCalculatorDialog
from .widgets import FieldWidget

_BYPRODUCT_NAMES = ("spec_ids", "nu_gases", "nu_residue", "residue_id")


class EditorExtrasMixin:
    _chosen_kind: Optional[str] = None
    _byproducts: Optional[ByproductsWidget] = None

    # -- surfaces: type selector and live check --------------------------------------------------------
    def _build_type_row(self, layout: QVBoxLayout, parent: QWidget) -> None:
        self.type_row = QWidget(parent)
        row = QHBoxLayout(self.type_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Surface type", self.type_row))
        self.type_combo = QComboBox(self.type_row)
        if self.attr == "surfaces":
            for key, text in self.api.surfaces.kinds().items():
                self.type_combo.addItem(text, key)
        self.type_combo.activated.connect(self._on_type_chosen)
        row.addWidget(self.type_combo, 1)
        layout.addWidget(self.type_row)
        self.type_note = QLabel("", parent)
        self.type_note.setWordWrap(True)
        layout.addWidget(self.type_note)
        self.type_row.setVisible(self.attr == "surfaces")
        self.type_note.setVisible(self.attr == "surfaces")

    def _kind_for(self, entity: Any, pending: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """The tab layout to use: the user's pick, else the type the surface's values add up to."""
        if self.attr != "surfaces":
            return None
        if self._chosen_kind:
            return self._chosen_kind
        return self.api.surfaces.kind(self.model.probe(entity, pending) if pending else entity)

    def _select_type_combo(self, kind: Optional[str]) -> None:
        if kind is not None:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(kind)))
            self.type_combo.blockSignals(False)

    def _on_type_chosen(self, index: int) -> None:
        """Show the tabs of another type. Values already typed are kept; nothing is cleared."""
        self._chosen_kind = self.type_combo.itemData(index)
        if self._current is not None:
            self._load(self._current, keep=self.pending())

    def _refresh_type_note(self) -> None:
        if self.attr != "surfaces" or self._current is None:
            return
        try:
            probe = self.model.probe(self._current, self.pending())
            detected = self.api.surfaces.kind(probe)
            problems = self.api.surfaces.problems(probe)
        except Exception as exc:
            self.type_note.setText(str(exc))
            return
        text = f"Values add up to: {detected.replace('_', ' ')}"
        if problems:
            text += "\n" + "\n".join("! " + p for p in problems)
        self.type_note.setStyleSheet("color: #b3261e;" if problems else "")
        self.type_note.setText(text)

    # -- materials: byproducts and the calculator ----------------------------------------------------------
    def _species_choices(self) -> List[str]:
        names = {s.name for s in self.api.species.all()}
        names |= {r.fuel for r in self.api.reactions.all() if r.fuel}
        try:
            names |= set(self.api.library.names("species"))
        except Exception:
            pass
        return sorted(names)

    def _add_byproducts_tab(self, entity: Any, shown: Dict[str, Any], tabs, specs_by_name: Dict[str, Any]) -> None:
        widget = ByproductsWidget(self._species_choices(), [m.name for m in self.model.entities() if m is not entity], self)
        widget.load(shown.get("spec_ids"), shown.get("nu_gases"), shown.get("nu_residue"), shown.get("residue_id"))
        getters = {"spec_ids": lambda: widget.gases()["species"] or None, "nu_gases": lambda: widget.gases()["yields"] or None,
                   "nu_residue": widget.residue, "residue_id": widget.residue_id}
        for name in _BYPRODUCT_NAMES:
            spec = specs_by_name.get(name)
            if spec is not None:
                self._widgets[name] = FieldWidget(spec, widget, getters[name], lambda _v: None, self)
        widget.changed.connect(self._update_preview)
        self._byproducts = widget
        tabs.addTab(widget, "Byproducts")

    def _add_calculator_button(self, form_layout) -> None:
        btn = QPushButton("Pyrolysis calculator...", self)
        btn.clicked.connect(lambda _c=False: self.open_pyrolysis_calculator())
        form_layout.addRow(btn)

    def _extra_problems(self) -> List[str]:
        return self._byproducts.problems() if self._byproducts is not None and self.attr == "materials" else []

    def open_pyrolysis_calculator(self) -> Optional[Dict[str, Any]]:
        """Ask for a rate by one of four methods and put the result on the chosen reaction's fields (unsaved until
        Apply). Returns the values applied, or None if cancelled."""
        if self._current is None or self.attr != "materials":
            return None
        rows = self._widgets["reactions"].value() if "reactions" in self._widgets else []
        targets = [f"Step {i + 1}" for i in range(len(rows))] if rows else ["Main reaction"]
        dlg = PyrolysisCalculatorDialog(self.api, self._current, targets, self)
        self._calculator = dlg
        if dlg.exec() != QDialog.Accepted or dlg.result() is None:
            return None
        return self.apply_calculation(dlg.result().values, dlg.target_index() if rows else None, dlg.method_key())

    def apply_calculation(self, values: Dict[str, Any], step: Optional[int], method: str) -> Optional[Dict[str, Any]]:
        """Write calculator results onto the main reaction (step None) or onto table row *step*."""
        if step is None:
            for name, value in values.items():
                if name in self._widgets:
                    self._widgets[name].set_value(value)
            return values
        if method == "match":
            QMessageBox.information(self, "Pyrolysis Reaction",
                                    "Matching a rate curve sets the main reaction only. Use another method for a step "
                                    "of a multi-step material, or remove the steps.")
            return None
        fw = self._widgets["reactions"]
        rows = fw.value()
        for key in ("a", "e", "n_s"):
            rows[step][key] = values.get(key)
        fw.set_value(rows)
        fw.changed.emit()
        return {k: values.get(k) for k in ("a", "e", "n_s")}
