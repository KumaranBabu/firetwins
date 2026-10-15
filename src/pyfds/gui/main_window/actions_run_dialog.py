"""Run FDS dialogs, stop / cancel, MPI preview, and the Results-menu entries that open the in-app viewer (step F6)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from pyfds.gui.run import model as run_model
from pyfds.gui.run.dialog import RunDialog
from pyfds.gui.run.model import RunSetup

_FINISHED = ("done", "failed", "cancelled", "dry_run")


class ActionsRunDialogMixin:
    _run_handle: Any = None
    _run_setup: Optional[RunSetup] = None

    # -- starting -----------------------------------------------------------------------------
    def _on_run_dialog(self, mode: str = "local", setup: Optional[RunSetup] = None) -> Any:
        """Ask how to run (unless *setup* is given), start the run and follow it. Returns the run handle."""
        if self._run_is_active():
            QMessageBox.information(self, "Run FDS", "A simulation is already running. Stop or cancel it first.")
            return None
        if setup is None:
            dialog = RunDialog(self.api, mode, self)
            self._run_dialog = dialog
            if dialog.exec() != QDialog.Accepted:
                return None
            setup = dialog.setup()
        try:
            handle = run_model.start(self.api, setup)
        except Exception as exc:
            QMessageBox.critical(self, "Could not start the run", str(exc))
            return None
        self._begin_tracking(handle, setup)
        return handle

    def _begin_tracking(self, handle: Any, setup: RunSetup) -> None:
        self._run_handle, self._run_setup = handle, setup
        self._last_run_dir = setup.output_dir
        if setup.mode != "cloud":
            getattr(self, "_show_run_monitor", lambda d: None)(setup.output_dir)
        self._set_run_actions(running=handle.state not in _FINISHED)
        self.statusBar().showMessage(f"{setup.mode.title()} run started in {setup.output_dir}")
        timer = QTimer(self)
        timer.timeout.connect(self._poll_run)
        timer.start(500)
        self._run_poll = timer
        if handle.state in _FINISHED:
            self._poll_run()

    def _run_is_active(self) -> bool:
        return self._run_handle is not None and self.api.solvers.status(self._run_handle) not in _FINISHED

    def _set_run_actions(self, running: bool) -> None:
        for name in ("_run_local_action", "_run_parallel_action", "_run_cluster_action", "_run_cloud_action"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(not running)
        for name in ("_stop_action", "_cancel_action"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(running)

    # -- following ------------------------------------------------------------------------------
    def _poll_run(self) -> str:
        handle, setup = self._run_handle, self._run_setup
        if handle is None:
            return "idle"
        state = self.api.solvers.status(handle)
        if state not in _FINISHED:
            self.statusBar().showMessage(f"{setup.mode.title()} run: {state}")
            return state
        timer = getattr(self, "_run_poll", None)
        if timer is not None:
            timer.stop()
        if handle.extra.get("reported"):                 # already told the user; polling again changes nothing
            return state
        handle.extra["reported"] = True
        self._set_run_actions(running=False)
        self._finish_run(handle, setup, state)
        self._refresh_status()
        return state

    def _finish_run(self, handle: Any, setup: RunSetup, state: str) -> None:
        if state == "dry_run":
            QMessageBox.information(self, "Run FDS", "Nothing was started (dry run).")
        elif state == "cancelled":
            self.statusBar().showMessage("Simulation cancelled", 6000)
        elif state == "failed":
            QMessageBox.warning(self, "Simulation did not complete", handle.message or "FDS reported an error")
        else:
            out = setup.output_dir
            if setup.mode == "cloud":
                try:
                    out = str(Path(setup.output_dir) / "results")
                    self.api.solvers.fetch(handle, out)
                    self._last_run_dir = out
                except Exception as exc:
                    QMessageBox.warning(self, "Could not fetch the results", str(exc))
                    return
            stopped = handle.extra.get("stop_requested")
            QMessageBox.information(
                self, "Simulation stopped" if stopped else "Simulation complete",
                (f"Stopped on request; a restart file was written (use Resume).\nOutput: {out}" if stopped
                 else f"Output: {out}"))
            smv = Path(out) / f"{self.api.project.chid}.smv"
            if setup.open_smokeview and smv.is_file():
                try:
                    self.api.smokeview.open(str(smv), blocking=False)
                except Exception as exc:
                    QMessageBox.warning(self, "Could not open Smokeview", str(exc))

    # -- control --------------------------------------------------------------------------------
    def _on_stop_simulation(self) -> None:
        """Stop cleanly: FDS finishes the step and writes a restart file (FDS has no pause)."""
        if not self._run_is_active():
            QMessageBox.information(self, "Stop Simulation", "No simulation is running.")
            return
        try:
            self.api.solvers.stop(self._run_handle)
            self.statusBar().showMessage("Stop requested: FDS will write a restart file and exit", 8000)
        except Exception as exc:
            QMessageBox.warning(self, "Stop Simulation", str(exc))

    def _on_cancel_simulation(self) -> None:
        """End the run now, without a restart file."""
        if not self._run_is_active():
            QMessageBox.information(self, "Cancel Simulation", "No simulation is running.")
            return
        self.api.solvers.cancel(self._run_handle)
        self._poll_run()

    def _on_mpi_preview(self) -> None:
        n = len(self.api.project.meshes)
        if n < 2:
            QMessageBox.information(self, "MPI Preview", "A parallel run needs at least two meshes.")
            return
        rows = run_model.assignment(self.api, RunSetup(mode="parallel", processes=n))
        lines = ["Process  ->  mesh"] + [f"  {r + 1:>3}      {self.api.project.meshes[r].name}"
                                         for row in rows for r in row["meshes"]]
        QMessageBox.information(self, "MPI Preview", "\n".join(lines))

    # -- results ----------------------------------------------------------------------------------
    def _on_preview_model(self) -> Optional[str]:
        """Show the model in the results viewer without a real run (FDS runs for zero simulated time)."""
        path = getattr(self, "_current_project_path", None)
        work = str(Path(path).parent / "preview") if path else QFileDialog.getExistingDirectory(
            self, "Folder for the model preview")
        if not work:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            smv = self.api.solvers.preview_model(work)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could not preview the model", str(exc))
            return None
        QApplication.restoreOverrideCursor()
        self.show_results_tab(smv)
        return smv

    def _on_view_results(self) -> None:
        """Open the last run's results in the viewer tab (or ask which case to open)."""
        folder = getattr(self, "_last_run_dir", None)
        smv = Path(folder) / f"{self.api.project.chid}.smv" if folder else None
        self.show_results_tab(str(smv) if smv is not None and smv.is_file() else None)
