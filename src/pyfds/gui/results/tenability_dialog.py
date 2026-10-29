"""Analysis > Tenability (FED): Purser's fractional effective dose from device curves, time to incapacitation, ASET margin.

The gases come from loaded CSV columns (File > Load CSV File, or the case's ``_devc.csv`` loaded with the results); the
dose uses FDS's own constants (``pyfds.tenability.fed``), so it agrees with an FDS ``QUANTITY='FED'`` device.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


NONE = "(none)"
#: role -> (label, words that suggest a column for it)
ROLES = {
    "co": ("Carbon monoxide", ("carbon monoxide", " co ", "_co", "co_", "co ppm")),
    "o2": ("Oxygen", ("oxygen", " o2", "_o2", "o2_")),
    "co2": ("Carbon dioxide", ("carbon dioxide", " co2", "_co2", "co2_")),
    "hcn": ("Hydrogen cyanide", ("hydrogen cyanide", "hcn")),
    "temp": ("Gas temperature", ("temperature", "temp", "tc")),
}


def to_ppm(values: np.ndarray, unit: str) -> np.ndarray:
    u = (unit or "").strip().lower()
    if u in ("mol/mol", "kg/kg", "", "-"):           # FDS volume fraction (mass fraction is close enough only if asked)
        return values * 1e6
    if u == "%":
        return values * 1e4
    if u == "ppm":
        return values
    raise ValueError(f"cannot convert {unit!r} to ppm")


def to_percent(values: np.ndarray, unit: str) -> np.ndarray:
    return to_ppm(values, unit) / 1e4


def _place_tag(sid: str) -> str:
    """What a device name says about where it is: 'CO_15' -> '15', 'O2_ROOM' -> 'room' (the gas word removed)."""
    name = sid.rsplit("/", 1)[-1].strip().lower()
    return re.sub(r"^(co2|co|o2|hcn)[_\- .]*|[_\- .]*(co2|co|o2|hcn)$", "", name)


def guess(series: Dict[str, Any], role: str, near: Optional[str] = None) -> Optional[str]:
    """The first column whose quantity or name suggests *role* (a CO2 column is never taken for CO or O2). With *near*
    (the chosen CO column), a column whose name carries the same place tag wins: GAS_T_15 for CO_15, not TC_060."""
    words = ROLES[role][1]
    hits = []
    for sid, s in series.items():
        text = f" {s.quantity} {s.description} {sid} ".lower()
        if role in ("co", "o2") and ("co2" in text or "dioxide" in text):
            continue
        in_degrees = role == "temp" and str(getattr(s, "unit", "")).strip().lower() in ("c", "°c", "k")
        if in_degrees or any(w in text for w in words):          # a _devc.csv column has only its name and unit
            hits.append(sid)
    tag = _place_tag(near) if near else ""
    if tag and tag != near.rsplit("/", 1)[-1].strip().lower():
        same = [sid for sid in hits
                if re.search(rf"(^|[_\- .]){re.escape(tag)}($|[_\- .])", sid.rsplit("/", 1)[-1].strip().lower())]
        if same:
            return same[0]
    return hits[0] if hits else None


def tenability(api: Any, series: Dict[str, Any], picks: Dict[str, Optional[str]],
               rset_s: float) -> List[Tuple[str, str]]:
    """Result rows for the chosen columns. CO is required; the others are optional (ambient air assumed)."""
    if not picks.get("co"):
        raise ValueError("choose the carbon monoxide column")
    co = series[picks["co"]]
    t = np.asarray(co.times, dtype=float)

    def on_t(role: str) -> Optional[np.ndarray]:
        sid = picks.get(role)
        if not sid:
            return None
        s = series[sid]
        return np.interp(t, np.asarray(s.times, float), np.asarray(s.values, float)), s.unit

    co_ppm = to_ppm(np.asarray(co.values, float), co.unit)
    o2 = on_t("o2")
    co2 = on_t("co2")
    hcn = on_t("hcn")
    temp = on_t("temp")
    res = api.engineering.fed(
        list(t), list(co_ppm),
        o2_pct=list(to_percent(*o2)) if o2 else None,
        hcn_ppm=list(to_ppm(*hcn)) if hcn else None,
        co2_pct=list(to_percent(*co2)) if co2 else None,
        temp_c=list(temp[0]) if temp else None,
    )
    fmt = lambda x: "not reached" if x is None else f"{x:.1f} s"     # noqa: E731
    margin = float("inf") if res.t_incapacitation is None else res.t_incapacitation - rset_s
    rows = [
        ("Maximum FED (gases)", f"{res.max_fed:.3g}"),
        (f"Time to FED {res.incapacitation_threshold:g} (incapacitation, ASET)", fmt(res.t_incapacitation)),
        ("Time to FED 1 (lethality)", fmt(res.t_lethality)),
        ("Time to heat dose 1 (separate from FED)", fmt(res.t_heat_incapacitation) if temp else "no temperature chosen"),
        ("ASET - RSET", "ASET not reached in this run" if margin == float("inf") else f"{margin:.1f} s"),
        ("End of the curves", f"{t[-1]:.1f} s"),
    ]
    return rows


class TenabilityDialog(QDialog):
    def __init__(self, api: Any, viewer: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.viewer = viewer
        self.setWindowTitle("Tenability (FED)")
        self.resize(560, 460)
        self.series = viewer.csv_series()
        v = QVBoxLayout(self)
        note = QLabel("Fractional effective dose (Purser, with FDS's constants) from device curves. "
                      "Load the case's _devc.csv first (File > Load CSV File) if no columns are listed.", self)
        note.setWordWrap(True)
        v.addWidget(note)
        form = QFormLayout()
        self.combos: Dict[str, QComboBox] = {}
        co_pick = guess(self.series, "co")
        for role, (label, _words) in ROLES.items():
            box = QComboBox(self)
            box.addItem(NONE, None)
            for sid in self.series:
                box.addItem(sid, sid)
            hit = guess(self.series, role, near=None if role == "co" else co_pick)   # the gases' own place
            if hit:
                box.setCurrentIndex(box.findData(hit))
            form.addRow(label, box)
            self.combos[role] = box
        self.rset = QDoubleSpinBox(self)
        self.rset.setRange(0.0, 1e6)
        self.rset.setValue(120.0)
        self.rset.setSuffix(" s")
        form.addRow("Required safe egress time (RSET)", self.rset)
        v.addLayout(form)
        go = QPushButton("Calculate", self)
        go.clicked.connect(self.calculate)
        v.addWidget(go)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Result", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        v.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def picks(self) -> Dict[str, Optional[str]]:
        return {role: box.currentData() for role, box in self.combos.items()}

    def calculate(self) -> List[Tuple[str, str]]:
        try:
            rows = tenability(self.api, self.series, self.picks(), self.rset.value())
        except (ValueError, KeyError) as exc:
            self.table.setRowCount(0)
            self.message.setText(str(exc))
            return []
        self.table.setRowCount(len(rows))
        for r, (name, value) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(value))
        self.table.resizeColumnToContents(0)
        self.message.setText("At the device locations only; NOx and irritant gases are not included.")
        return rows


def install(window: Any) -> None:
    """Analysis > Tenability (FED)... in the results window."""
    bar = window.menuBar()
    menu = next((a.menu() for a in bar.actions() if a.menu() is not None and a.text().replace("&", "") == "Analysis"),
                None)
    if menu is None:
        menu = bar.addMenu("&Analysis")
    menu.addSeparator()

    def show() -> TenabilityDialog:
        window._tenability_dialog = TenabilityDialog(window.api, window.viewer, window)
        window._tenability_dialog.show()
        return window._tenability_dialog

    window.open_tenability = show
    menu.addAction("&Tenability (FED)...", show)
