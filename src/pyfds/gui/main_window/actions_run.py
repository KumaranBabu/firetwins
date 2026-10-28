"""Run menu actions: run / resume simulation, Smokeview, results folder."""
from __future__ import annotations

import shutil

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .shared import _default_smv_binary


class ActionsRunMixin:
    def _on_run_simulation(self) -> None:
        """Run > Run Simulation: the Run dialog, on MPI when the model has several meshes (one process each)."""
        cfg = self.api.config
        if not shutil.which(getattr(cfg, "smv_binary", "") or ""):          # 'Open Smokeview after the run' needs it
            bundled_smv = _default_smv_binary()
            if bundled_smv:
                cfg.set("smv_binary", bundled_smv)
        return self._on_run_dialog("parallel" if self.api.meshes.run_count() > 1 else "local")

    def _on_resume_simulation(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Original FDS Input File", "", "FDS Files (*.fds)")
        if not path:
            return
        num_processes, ok = QInputDialog.getInt(
            self, "Resume Simulation", "Number of MPI processes:", 1, 1, 128
        )
        if not ok:
            return

        # ExecutionManager has no resume_from_checkpoint_async: run it on a worker thread and poll, rather than
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
