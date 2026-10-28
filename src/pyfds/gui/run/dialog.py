"""RunDialog (plan step F6): Run FDS / Parallel / Cluster / Cloud in one dialog.

The mode picks the page. Everything it decides lives in ``gui.run.model``; this class shows the setup, previews which
meshes go where, and lists what would stop the run before the Run button is pressed.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from html import escape

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import model
from .model import MODES, TITLES, RunSetup

_NODES_KEY = "cluster_nodes"
_MODE_LABELS = {"local": "This computer", "parallel": "This computer, in parallel (MPI)",
                "cluster": "A cluster of computers", "cloud": "Cloud / remote service"}


class RunDialog(QDialog):
    def __init__(self, api: Any, mode: str = "local", parent: Optional[QWidget] = None,
                 setup: Optional[RunSetup] = None, installs: Optional[List[Any]] = None,
                 fds_found: Optional[bool] = None, show_checks: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.api = api
        self._setup = setup or model.default_setup(api, mode)
        self._installs = installs if installs is not None else self._find_installs()
        self._fds_found = fds_found if fds_found is not None else (bool(self._installs) or model.fds_available(api))
        self._show_checks = show_checks
        try:                                   # once: the model cannot change while this dialog is open
            self.report = api.validation.validate()
        except Exception:
            self.report = None
        self.setWindowTitle(TITLES[self._setup.mode])
        self.resize(560, 480)
        self._build()
        self._load(self._setup)
        self.refresh()

    # -- layout ---------------------------------------------------------------------------------
    def _find_installs(self) -> List[Any]:
        try:
            return self.api.solvers.installs()
        except Exception:
            return []

    def _build(self) -> None:
        root = QVBoxLayout(self)
        top = QFormLayout()
        self.mode_combo = QComboBox(self)
        for m in MODES:
            self.mode_combo.addItem(_MODE_LABELS[m], m)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top.addRow("Where to run", self.mode_combo)
        row = QHBoxLayout()
        self.folder = QLineEdit(self)
        self.folder.textChanged.connect(lambda _t: self.refresh())
        browse = QPushButton("Browse...", self)
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        top.addRow("Input and results folder", row)
        self.fds_combo = QComboBox(self)
        self.fds_combo.addItem("(as configured)", None)
        for inst in self._installs:
            self.fds_combo.addItem(f"{inst.name}  -  {inst.path}", inst.name)
        self.fds_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)   # long install paths
        self.fds_combo.setMinimumContentsLength(28)                                          # must not widen the dialog
        fds_row = QHBoxLayout()
        fds_row.addWidget(self.fds_combo, 1)
        locate = QPushButton("Locate FDS...", self)
        locate.clicked.connect(self._locate_fds)
        fds_row.addWidget(locate)
        top.addRow("FDS version", fds_row)
        root.addLayout(top)

        box = QGroupBox("Before you run", self)          # what the run will compute, and the model checks
        col = QVBoxLayout(box)
        self.summary_label = QLabel("", box)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.RichText)
        col.addWidget(self.summary_label)
        self.checks_button = QPushButton("Show the problems", box)
        self.checks_button.setToolTip("Close this dialog and list the model checks in the Validation panel")
        self.checks_button.clicked.connect(self._on_show_checks)
        self.checks_button.setVisible(False)
        col.addWidget(self.checks_button, 0, Qt.AlignLeft)
        root.addWidget(box)

        self.pages = QStackedWidget(self)
        local_note = QLabel("Runs FDS on this computer with one process.", self)
        local_note.setWordWrap(True)
        self.pages.addWidget(local_note)
        self.pages.addWidget(self._parallel_page())
        self.pages.addWidget(self._cluster_page())
        self.pages.addWidget(self._cloud_page())
        root.addWidget(self.pages, 1)

        self.validate_box = QCheckBox("Check the model first and stop if it has errors", self)
        self.validate_box.setChecked(True)
        self.validate_box.toggled.connect(lambda _b: self.refresh())
        self.smokeview_box = QCheckBox("Open Smokeview when the run finishes", self)
        root.addWidget(self.validate_box)
        root.addWidget(self.smokeview_box)
        self.problem_label = QLabel("", self)
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet("color: #b3261e;")
        root.addWidget(self.problem_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.button(QDialogButtonBox.Ok).setText("Run")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _assignment_table(self, parent: QWidget, first: str = "Host") -> QTableWidget:
        t = QTableWidget(0, 3, parent)
        t.setHorizontalHeaderLabels([first, "Processes", "Meshes"])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        return t

    def _parallel_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.processes = QSpinBox(page)
        self.processes.setRange(1, 4096)
        self.processes.valueChanged.connect(lambda _v: self.refresh())
        form.addRow("MPI processes", self.processes)
        self.parallel_table = self._assignment_table(page, "Process")
        form.addRow("Assigned meshes", self.parallel_table)
        return page

    def _cluster_page(self) -> QWidget:
        page = QWidget(self)
        v = QVBoxLayout(page)
        note = QLabel("Nodes, in mesh order. The folder must be visible to every node under the same path "
                      "(a UNC path without spaces on Windows).", page)
        note.setWordWrap(True)                     # unwrapped, this one line made the whole dialog ~1500 px wide
        v.addWidget(note)
        self.hosts_table = QTableWidget(0, 2, page)
        self.hosts_table.setHorizontalHeaderLabels(["Host", "Processes"])
        self.hosts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hosts_table.itemChanged.connect(lambda _i: self.refresh())
        v.addWidget(self.hosts_table)
        row = QHBoxLayout()
        add = QPushButton("Add node", page)
        add.clicked.connect(lambda _c=False: self.add_host("", 1))
        rem = QPushButton("Remove selected", page)
        rem.clicked.connect(lambda _c=False: self._remove_hosts())
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.addLayout(row)
        self.cluster_table = self._assignment_table(page)
        v.addWidget(QLabel("Assigned meshes", page))
        v.addWidget(self.cluster_table)
        return page

    def _cloud_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.provider = QComboBox(page)
        self.provider.addItems(self.api.solvers.cloud_providers())
        self.provider.currentTextChanged.connect(lambda _t: self.refresh())
        form.addRow("Provider", self.provider)
        self.spool = QLineEdit(page)
        self.spool.setPlaceholderText("folder the 'directory' provider runs jobs in")
        self.spool.textChanged.connect(lambda _t: self.refresh())
        form.addRow("Spool folder", self.spool)
        self.vcpus = QSpinBox(page)
        self.vcpus.setRange(1, 4096)
        form.addRow("Number of vCPUs", self.vcpus)
        self.memory = QSpinBox(page)
        self.memory.setRange(1, 512)
        self.memory.setSuffix(" GB per vCPU")
        form.addRow("Memory", self.memory)
        self.fds_version = QLineEdit(page)
        self.fds_version.setPlaceholderText("e.g. 6.10.1 (passed to the provider)")
        form.addRow("FDS version", self.fds_version)
        return page

    # -- loading and reading ---------------------------------------------------------------------
    def _load(self, s: RunSetup) -> None:
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(max(0, MODES.index(s.mode)))
        self.mode_combo.blockSignals(False)
        self.pages.setCurrentIndex(MODES.index(s.mode))
        self.folder.setText(s.output_dir)
        self.processes.setValue(max(s.processes, 1))
        self.fds_combo.setCurrentIndex(max(0, self.fds_combo.findData(s.install)))
        self.validate_box.setChecked(s.validate_first)
        self.smokeview_box.setChecked(s.open_smokeview)
        hosts = s.hosts or self._remembered_hosts() or model.default_setup(self.api, "cluster").hosts
        self.hosts_table.blockSignals(True)
        for h in hosts:
            name, _, n = h.partition(":")
            self.add_host(name, int(n or 1))
        self.hosts_table.blockSignals(False)
        i = self.provider.findText(s.provider)
        self.provider.setCurrentIndex(max(0, i))
        self.spool.setText(str(s.provider_config.get("root", "")))
        self.vcpus.setValue(int(s.options.get("vcpus", max(self.api.meshes.run_count(), 1))))
        self.memory.setValue(int(s.options.get("memory_gb_per_vcpu", 2)))
        self.fds_version.setText(str(s.options.get("fds_version", "")))

    @staticmethod
    def _remembered_hosts() -> List[str]:
        v = QSettings("PyFDS", "PyFDS").value(_NODES_KEY, [])
        return [str(x) for x in (v if isinstance(v, list) else [v] if v else [])]

    def add_host(self, name: str, processes: int) -> None:
        r = self.hosts_table.rowCount()
        self.hosts_table.insertRow(r)
        self.hosts_table.setItem(r, 0, QTableWidgetItem(name))
        self.hosts_table.setItem(r, 1, QTableWidgetItem(str(processes)))

    def _remove_hosts(self) -> None:
        for r in sorted({i.row() for i in self.hosts_table.selectedIndexes()}, reverse=True):
            self.hosts_table.removeRow(r)
        self.refresh()

    def _hosts(self) -> List[str]:
        out = []
        for r in range(self.hosts_table.rowCount()):
            name = (self.hosts_table.item(r, 0).text() if self.hosts_table.item(r, 0) else "").strip()
            n = (self.hosts_table.item(r, 1).text() if self.hosts_table.item(r, 1) else "1").strip()
            out.append(f"{name}:{n if n.isdigit() else 0}")
        return out

    def setup(self) -> RunSetup:
        mode = self.mode_combo.currentData()
        options = {"vcpus": self.vcpus.value(), "memory_gb_per_vcpu": self.memory.value()}
        if self.fds_version.text().strip():
            options["fds_version"] = self.fds_version.text().strip()
        return RunSetup(
            mode=mode, output_dir=self.folder.text().strip(), processes=self.processes.value(),
            hosts=self._hosts(), provider=self.provider.currentText() or "directory",
            provider_config={"root": self.spool.text().strip()} if self.spool.text().strip() else {},
            options=options, install=self.fds_combo.currentData(),
            open_smokeview=self.smokeview_box.isChecked(), validate_first=self.validate_box.isChecked())

    # -- behaviour --------------------------------------------------------------------------------
    def _on_mode_changed(self, _i: int) -> None:
        self.pages.setCurrentIndex(self.mode_combo.currentIndex())
        self.setWindowTitle(TITLES[self.mode_combo.currentData()])
        self.refresh()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Input and results folder", self.folder.text())
        if path:
            self.folder.setText(path)

    def _fill(self, table: QTableWidget, rows: List[dict]) -> None:
        table.setRowCount(0)
        for row in rows:
            r = table.rowCount()
            table.insertRow(r)
            for c, text in enumerate((row["host"], str(len(row["ranks"])),
                                      ", ".join(str(m + 1) for m in row["meshes"]) or "-")):
                table.setItem(r, c, QTableWidgetItem(text))

    def refresh(self) -> None:
        """Re-check the setup: update the mesh assignment previews and the list of problems."""
        if not hasattr(self, "buttons"):
            return
        s = self.setup()
        try:
            if s.mode == "parallel":
                self._fill(self.parallel_table, model.assignment(self.api, s))
            elif s.mode == "cluster":
                self._fill(self.cluster_table, model.assignment(self.api, s))
            found = model.problems(self.api, s, self.report, self._fds_found)
        except Exception as exc:                        # a half-typed host table must not break the dialog
            found = [str(exc)]
        self.problem_label.setText("\n".join(found))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not found)
        self._show_summary(s)

    def _show_summary(self, s: RunSetup) -> None:
        try:
            lines = model.summary_lines(model.summary(self.api, s, self.report))
        except Exception as exc:                        # the summary is information: it must never block the dialog
            lines = [f"! Could not summarise the model: {exc}"]
        html = []
        for line in lines:
            if line.startswith("!"):
                html.append(f"<span style='color:#b3261e'>{escape(line[1:].strip())}</span>")
            else:
                html.append(escape(line))
        self.summary_label.setText("<br>".join(html))
        has_findings = self.report is not None and bool(self.report.errors or self.report.warnings)
        self.checks_button.setVisible(has_findings and self._show_checks is not None)

    def _on_show_checks(self) -> None:
        self.reject()
        if self._show_checks is not None:
            self._show_checks()

    def _locate_fds(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate the FDS executable", "", "FDS (fds*.exe fds*);;All files (*)")
        if not path:
            return
        try:
            inst = self.api.solvers.add_install(path)
        except Exception as exc:
            QMessageBox.warning(self, "Locate FDS", str(exc))
            return
        self._installs.append(inst)
        self.fds_combo.addItem(f"{inst.name}  -  {inst.path}", inst.name)
        self.fds_combo.setCurrentIndex(self.fds_combo.count() - 1)
        self._fds_found = True
        self.refresh()

    def problems(self) -> List[str]:
        t = self.problem_label.text()
        return t.split("\n") if t else []

    def accept(self) -> None:
        if self.problems():
            return
        if self.setup().mode == "cluster":              # PyroSim remembers the nodes for next time
            QSettings("PyFDS", "PyFDS").setValue(_NODES_KEY, self._hosts())
        super().accept()
