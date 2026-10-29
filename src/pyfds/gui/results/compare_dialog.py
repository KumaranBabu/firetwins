"""Analysis > Compare Runs: two result folders device by device (``pyfds.results.comparator``).

Each ``*_devc.csv`` channel's peak and mean are compared; a difference above the threshold is flagged, and a channel
found in only one run is listed as missing. Typical use: a mesh-sensitivity run, or a design change, against a baseline.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

_COLUMNS = ["Channel", "Units", "Baseline peak", "Variant peak", "Peak diff %", "Mean diff %", "Status"]
_STATUS = {"ok": "ok", "warning": "above threshold", "missing_baseline": "variant only",
           "missing_variant": "baseline only"}


def _num(value: float, spec: str) -> str:
    """A number for the table; '-' where a run has no value (a channel only one run has)."""
    return "-" if math.isnan(value) else format(value, spec)


def _folder_row(parent: QWidget, edit: QLineEdit) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(edit, 1)
    browse = QPushButton("Browse...", parent)
    browse.clicked.connect(lambda: _pick(parent, edit))
    row.addWidget(browse)
    return row


def _pick(parent: QWidget, edit: QLineEdit) -> None:
    path = QFileDialog.getExistingDirectory(parent, "Result folder", edit.text() or "")
    if path:
        edit.setText(path)


class CompareRunsDialog(QDialog):
    def __init__(self, api: Any, baseline_dir: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Compare Runs")
        self.resize(780, 520)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.baseline = QLineEdit(baseline_dir, self)
        self.variant = QLineEdit(self)
        self.threshold = QDoubleSpinBox(self)
        self.threshold.setRange(0.1, 1000.0)
        self.threshold.setValue(5.0)
        self.threshold.setSuffix(" %")
        form.addRow("Baseline folder", _folder_row(self, self.baseline))
        form.addRow("Variant folder", _folder_row(self, self.variant))
        form.addRow("Flag differences above", self.threshold)
        v.addLayout(form)
        go = QPushButton("Compare", self)
        go.clicked.connect(self.compare)
        v.addWidget(go)
        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table, 1)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def compare(self) -> Optional[Any]:
        base, var = self.baseline.text().strip(), self.variant.text().strip()
        missing = [p for p in (base, var) if not p or not Path(p).is_dir()]
        if missing:
            self.table.setRowCount(0)
            self.summary.setText("Choose two existing result folders.")
            return None
        report = self.api.engineering.compare_runs(base, var, self.threshold.value())
        self.table.setRowCount(len(report.channels))
        for r, c in enumerate(report.channels):
            cells = [c.name, c.units, _num(c.baseline_peak, ".4g"), _num(c.variant_peak, ".4g"),
                     _num(c.peak_pct_diff, "+.1f"), _num(c.mean_pct_diff, "+.1f"), _STATUS.get(c.status, c.status)
                     + (f": {c.note}" if c.note and c.status == "warning" else "")]
            for k, text in enumerate(cells):
                self.table.setItem(r, k, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.summary.setText(f"{report.n_ok} within {report.threshold_pct:g} %, {report.n_warnings} above, "
                             f"{report.n_missing} in one run only." if report.channels
                             else "No *_devc.csv channels found in these folders.")
        return report


def install(window: Any) -> None:
    """Analysis > Compare Runs... in the results window; the open case's folder is the baseline."""
    bar = window.menuBar()
    menu = next((a.menu() for a in bar.actions() if a.menu() is not None and a.text().replace("&", "") == "Analysis"),
                None)
    if menu is None:
        menu = bar.addMenu("&Analysis")

    def show() -> CompareRunsDialog:
        smv = getattr(getattr(window.viewer, "viz", None), "results", None) or ""      # the open case's .smv
        window._compare_dialog = CompareRunsDialog(window.api, str(Path(smv).resolve().parent) if smv else "", window)
        window._compare_dialog.show()
        return window._compare_dialog

    window.open_compare_runs = show
    menu.addAction("&Compare Runs...", show)
