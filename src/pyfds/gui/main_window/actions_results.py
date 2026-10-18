"""Results menu actions that stay in the model editor: isosurface definitions and archive / restore of a result index."""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from pyfds.gui.report_dialog import TextReportDialog


class ActionsResultsMixin:
    def _on_isosurface_settings(self) -> None:
        self._on_add_entity("add_isosurface")

    def _on_archive_results(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Archive Results As", "", "JSON Files (*.json)")
        if not save_path:
            return
        try:
            self.api.results.build_index(output_dir)
            self.api.results.archive(save_path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not archive results", str(exc))
        else:
            QMessageBox.information(self, "Archived", f"Result index archived to:\n{save_path}")

    def _on_restore_results(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore Results", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            idx = self.api.results.restore(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not restore results", str(exc))
            return
        TextReportDialog("Restored Result Index", idx.summary(), self).exec()
