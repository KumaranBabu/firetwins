"""Run menu actions: run / resume simulation, Smokeview, results folder."""
from __future__ import annotations

import shutil

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .shared import (
    _default_fds_binary,
    _default_smv_binary,
)


class ActionsRunMixin:
    def _on_run_simulation(self) -> None:
        cfg = self.api.config
        if not shutil.which(getattr(cfg, "fds_binary", "") or ""):
            bundled = _default_fds_binary()
            if bundled:
                cfg.set("fds_binary", bundled)
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Locate FDS Executable")
                if not path:
                    return
                cfg.set("fds_binary", path)

        if not shutil.which(getattr(cfg, "smv_binary", "") or ""):
            bundled_smv = _default_smv_binary()
            if bundled_smv:
                cfg.set("smv_binary", bundled_smv)

        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return

        num_processes, ok = QInputDialog.getInt(
            self, "Run Simulation", "Number of MPI processes:", 1, 1, 128
        )
        if not ok:
            return

        self._run_action.setEnabled(False)
        self.statusBar().showMessage("Running simulation...")
        self._run_future = self.api.execution.run_async(
            output_dir=output_dir,
            validate_first=True,
            open_smokeview=self._open_smokeview_action.isChecked(),
            num_processes=num_processes,
        )
        self._run_timer = QTimer(self)
        self._run_timer.timeout.connect(self._poll_run_future)
        self._run_timer.start(500)
        self._last_run_dir = output_dir
        getattr(self, "_show_run_monitor", lambda d: None)(output_dir)   # extras.py: live monitor window

    def _poll_run_future(self) -> None:
        if not self._run_future.done():
            return
        self._run_timer.stop()
        self._run_action.setEnabled(True)
        try:
            result = self._run_future.result()
        except Exception as exc:
            QMessageBox.critical(self, "Simulation failed", str(exc))
            self._refresh_status()
            return
        if result.success:
            QMessageBox.information(
                self, "Simulation complete",
                f"Wall time: {result.wall_time_seconds:.1f}s\nOutput: {result.output_dir}",
            )
        else:
            QMessageBox.warning(self, "Simulation did not complete", result.error or "Unknown error")
        self._refresh_status()

    def _on_resume_simulation(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Original FDS Input File", "", "FDS Files (*.fds)")
        if not path:
            return
        num_processes, ok = QInputDialog.getInt(
            self, "Resume Simulation", "Number of MPI processes:", 1, 1, 128
        )
        if not ok:
            return

        # Mirrors _on_run_simulation's own executor.submit()/QTimer polling —
        # ExecutionManager has no resume_from_checkpoint_async, so the same
        # off-main-thread pattern is applied here directly rather than
        # blocking the UI for the duration of a real FDS resume run.
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._resume_future = executor.submit(
            self.api.execution.resume_from_checkpoint, path, num_processes=num_processes
        )
        executor.shutdown(wait=False)
        self.statusBar().showMessage("Resuming simulation...")
        self._resume_timer = QTimer(self)
        self._resume_timer.timeout.connect(self._poll_resume_future)
        self._resume_timer.start(500)

    def _poll_resume_future(self) -> None:
        if not self._resume_future.done():
            return
        self._resume_timer.stop()
        try:
            result = self._resume_future.result()
        except Exception as exc:
            QMessageBox.critical(self, "Resume failed", str(exc))
            self._refresh_status()
            return
        if result.success:
            QMessageBox.information(
                self, "Resume complete",
                f"Wall time: {result.wall_time_seconds:.1f}s\nOutput: {result.output_dir}",
            )
        else:
            QMessageBox.warning(self, "Resume did not complete", result.error or "Unknown error")
        self._refresh_status()

    def _on_openmp_environment(self) -> None:
        current = self.api.project.misc.openmp_threads or 0
        threads, ok = QInputDialog.getInt(
            self, "OpenMP Environment", "Number of threads (0 = auto):", current, 0, 128
        )
        if not ok:
            return
        self.api.set_property(self.api.project.misc, "openmp_threads", threads or None)

    def _on_open_smokeview_results(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Smokeview File", "", "Smokeview Files (*.smv)")
        if not path:
            return
        try:
            self.api.smokeview.open(path, blocking=False)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open Smokeview", str(exc))

    def _on_open_results_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Results Folder")
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
