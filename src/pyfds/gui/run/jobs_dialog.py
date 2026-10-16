"""Run > Run Jobs...: every run started in this session, with its state and progress and what can be done with it.

The window never holds run state itself: it asks ``api.solvers.jobs()`` on a timer and acts on the selected row through
``api.solvers`` (stop, cancel, fetch, forget). Opening results and folders is handed in by the main window.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

_COLUMNS = ["Case", "Where", "State", "Progress", "Started", "Folder"]
_WHERE = {"local": "This computer", "cluster": "Cluster", "cloud": "Cloud / remote"}
_REFRESH_MS = 2000


def _started(epoch: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(epoch)) if epoch else ""


class JobsDialog(QDialog):
    def __init__(self, api: Any, open_results: Optional[Callable[[str], None]] = None,
                 open_folder: Optional[Callable[[str], None]] = None, parent: Optional[QWidget] = None,
                 auto_refresh: bool = True) -> None:
        super().__init__(parent)
        self.api = api
        self._open_results = open_results
        self._open_folder = open_folder
        self._jobs: List[Dict[str, Any]] = []
        self.setWindowTitle("Run Jobs")
        self.resize(820, 340)
        v = QVBoxLayout(self)
        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        v.addWidget(self.table, 1)
        self.empty = QLabel("No runs have been started in this session.", self)
        self.empty.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty)
        row = QHBoxLayout()
        self.stop_button = self._button(row, "Stop (restart file)", self.stop_selected)
        self.cancel_button = self._button(row, "Cancel now", self.cancel_selected)
        self.fetch_button = self._button(row, "Fetch Results...", lambda: self.fetch_selected())
        self.results_button = self._button(row, "View Results", self.open_results_selected)
        self.folder_button = self._button(row, "Open Folder", self.open_folder_selected)
        row.addStretch(1)
        self.clear_button = self._button(row, "Remove Finished", self.remove_finished)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
        self.refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._auto = auto_refresh
        if auto_refresh:
            self._timer.start(_REFRESH_MS)

    def _button(self, row, text: str, slot) -> QPushButton:
        b = QPushButton(text, self)
        b.clicked.connect(lambda _c=False: slot())
        row.addWidget(b)
        return b

    # -- the list ---------------------------------------------------------------------
    def refresh(self) -> None:
        keep = self.selected_id()
        self._jobs = self.api.solvers.jobs()
        self.table.setRowCount(len(self._jobs))
        for r, j in enumerate(self._jobs):
            cells = [j["chid"], _WHERE.get(j["kind"], j["kind"]), j["state"] + (f": {j['message']}" if j["message"] else ""),
                     j["progress"], _started(j["created"]), j["work_dir"]]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, j["id"])
                self.table.setItem(r, c, item)
        self.empty.setVisible(not self._jobs)
        if keep:
            self.select(keep)
        self._update_buttons()

    def selected_id(self) -> Optional[str]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None

    def selected_job(self) -> Optional[Dict[str, Any]]:
        sid = self.selected_id()
        return next((j for j in self._jobs if j["id"] == sid), None)

    def select(self, job_id: str) -> None:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == job_id:
                self.table.selectRow(r)
                return

    def _update_buttons(self) -> None:
        j = self.selected_job()
        self.stop_button.setEnabled(bool(j and j["can_stop"]))
        self.cancel_button.setEnabled(bool(j and j["can_cancel"]))
        self.fetch_button.setEnabled(bool(j and j["can_fetch"]))
        self.results_button.setEnabled(bool(j and j["smv"]) and self._open_results is not None)
        self.folder_button.setEnabled(j is not None and self._open_folder is not None)
        self.clear_button.setEnabled(any(not k["can_cancel"] and k["state"] != "unknown" for k in self._jobs))

    # -- acting on the selected run ------------------------------------------------------
    def _guard(self, what: str, fn: Callable[[Dict[str, Any]], Any]) -> bool:
        j = self.selected_job()
        if j is None:
            return False
        try:
            fn(j)
        except Exception as exc:
            QMessageBox.warning(self, what, str(exc))
            return False
        self.refresh()
        return True

    def stop_selected(self) -> bool:
        return self._guard("Stop", lambda j: self.api.solvers.stop(j["id"]))

    def cancel_selected(self) -> bool:
        return self._guard("Cancel", lambda j: self.api.solvers.cancel(j["id"]))

    def fetch_selected(self, dest: Optional[str] = None) -> bool:
        """Bring a finished cloud run's results to *dest* (asks for a folder when none is given)."""
        j = self.selected_job()
        if j is None:
            return False
        dest = dest or QFileDialog.getExistingDirectory(self, "Fetch results to...")
        if not dest:
            return False
        return self._guard("Fetch Results", lambda job: self.api.solvers.fetch(job["id"], dest))

    def open_results_selected(self) -> bool:
        j = self.selected_job()
        if j is None or not j["smv"] or self._open_results is None:
            return False
        self._open_results(j["smv"])
        return True

    def open_folder_selected(self) -> bool:
        j = self.selected_job()
        if j is None or self._open_folder is None:
            return False
        self._open_folder(j["work_dir"])
        return True

    def remove_finished(self) -> int:
        n = self.api.solvers.forget_finished()
        self.refresh()
        return n

    def showEvent(self, event) -> None:                       # noqa: N802 (Qt API)
        super().showEvent(event)
        if self._auto and not self._timer.isActive():         # shown again after being closed
            self._timer.start(_REFRESH_MS)

    def done(self, result: int) -> None:                      # stop polling once closed
        self._timer.stop()
        super().done(result)
