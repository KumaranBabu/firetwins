"""Results menu actions: browsers, plots, CSV, reports, animation and batch export, archive."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.render_worker import RenderWorker
from pyfds.gui.report_dialog import TextReportDialog

from .shared import (
    _import_figure_dialog,
)


class ActionsResultsMixin:
    def _on_slice_browser(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            entries = idx.find_slices()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load slices", str(exc))
            return
        if not entries:
            QMessageBox.information(self, "No slice data", "No slice files found in this directory.")
            return
        lines = [
            f"{e.quantity} ({e.units})  mesh={e.mesh_id}  {Path(e.filepath).name}"
            for e in entries
        ]
        TextReportDialog("Slice Browser", "\n".join(lines), self).exec()

    def _on_boundary_browser(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            entries = idx.find_boundaries()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load boundary files", str(exc))
            return
        if not entries:
            QMessageBox.information(self, "No boundary data", "No boundary files found in this directory.")
            return
        lines = [
            f"{e.quantity} ({e.units})  mesh={e.mesh_id}  {Path(e.filepath).name}"
            for e in entries
        ]
        TextReportDialog("Boundary Browser", "\n".join(lines), self).exec()

    def _on_plot_manager(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            FigureDialog = _import_figure_dialog()
        except ImportError:
            QMessageBox.critical(
                self, "Plotting unavailable",
                "Install with:\n  pip install pyfds[plot]",
            )
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
            if not device_names:
                QMessageBox.information(self, "No device data", "No device time-series data found.")
                return
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        name, ok = QInputDialog.getItem(self, "Plot Manager", "Device:", device_names, 0, False)
        if not ok:
            return
        try:
            fig = self.api.results.device_figure(name, index=idx)
        except Exception as exc:
            QMessageBox.critical(self, "Could not plot device", str(exc))
            return
        FigureDialog(f"Plot: {name}", fig, self).exec()

    def _on_isosurface_settings(self) -> None:
        self._on_add_entity("add_isosurface")

    def _on_export_csv(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        if not device_names:
            QMessageBox.information(self, "No device data", "No device time-series data found.")
            return
        name, ok = QInputDialog.getItem(self, "Export CSV", "Device:", device_names, 0, False)
        if not ok:
            return
        src = idx.find_device_file(name)
        if not src:
            QMessageBox.warning(self, "Not found", f"No CSV file found for device {name!r}.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export CSV As", f"{name}.csv", "CSV Files (*.csv)")
        if not dest:
            return
        try:
            shutil.copy(src, dest)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export CSV", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Device data exported to:\n{dest}")

    def _on_generate_report(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        dest, selected_filter = QFileDialog.getSaveFileName(
            self, "Generate Report As", "report.html",
            "HTML Report (*.html);;Text Report (*.txt)",
        )
        if not dest:
            return
        fmt = "html" if selected_filter.startswith("HTML") else "text"
        try:
            self.api.results.build_index(output_dir)
            report = self.api.results.generate_report()
            report.save(dest, fmt=fmt)
        except Exception as exc:
            QMessageBox.critical(self, "Could not generate report", str(exc))
        else:
            QMessageBox.information(self, "Report Generated", f"Report saved to:\n{dest}")

    def _on_batch_export(self) -> None:
        output_root = QFileDialog.getExistingDirectory(self, "Batch Study Output Root")
        if not output_root:
            return
        study_name, ok = QInputDialog.getText(
            self, "Batch Export", "Study name (blank = all variants under root):"
        )
        if not ok:
            return
        dest, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Batch Report As", "batch_report.html",
            "HTML Report (*.html);;JSON Report (*.json)",
        )
        if not dest:
            return
        try:
            report = self.api.results.analyze_batch(output_root, study_name=study_name or None)
            if selected_filter.startswith("HTML"):
                report.to_html(dest, title="Batch Study Report")
            else:
                report.to_json(dest)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export batch report", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Batch report saved to:\n{dest}")

    def _on_export_animation(self) -> None:
        """Render a movie of a result quantity via headless Smokeview."""
        smv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Smokeview File", "", "Smokeview Files (*.smv)"
        )
        if not smv_path:
            return
        schema = {
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "default": "TEMPERATURE"},
                "fps": {"type": "integer", "default": 10},
                "start_time": {"type": "number", "default": 0.0,
                               "description": "Seconds. 0 together with end time 0 = full range."},
                "end_time": {"type": "number", "default": 0.0},
            },
            "required": ["quantity"],
        }
        dialog = SchemaFormDialog("Export Animation", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export Animation As", "animation.mp4",
            "MP4 Video (*.mp4);;AVI Video (*.avi)",
        )
        if not out_path:
            return
        start = values.get("start_time") or None
        end = values.get("end_time") or None
        quantity = values.get("quantity") or "TEMPERATURE"
        fps = int(values.get("fps") or 10)
        worker = RenderWorker(
            lambda cancel: self.api.smokeview.render_movie(
                smv_path, out_path, quantity, fps=fps, start_time=start, end_time=end,
                cancel=cancel,
            ),
            self,
        )
        progress = QProgressDialog("Rendering animation with Smokeview...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Export Animation")
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(worker.cancel)
        worker.finished_rc.connect(
            lambda rc, err: self._on_render_finished(progress, out_path, rc, err, worker.cancelled)
        )
        self._render_worker = worker
        worker.start()
        progress.show()

    def _on_render_finished(self, progress, out_path: str, rc: int, err: str, cancelled: bool) -> None:
        progress.close()
        progress.deleteLater()
        if cancelled:
            QMessageBox.information(self, "Export Animation", "Export cancelled.")
        elif err:
            QMessageBox.critical(
                self, "Could not export animation",
                f"{err}\n\nCheck the 'smv_binary' setting in Preferences.",
            )
        elif rc == 0:
            QMessageBox.information(self, "Exported", f"Animation saved to:\n{out_path}")
        else:
            QMessageBox.warning(
                self, "Export Animation", f"Smokeview exited with return code {rc}."
            )

    def _on_view_time_history(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if not output_dir:
            return
        try:
            FigureDialog = _import_figure_dialog()
        except ImportError:
            QMessageBox.critical(
                self, "Plotting unavailable",
                "Install with:\n  pip install pyfds[plot]",
            )
            return
        try:
            idx = self.api.results.build_index(output_dir)
            device_names = idx.all_device_names()
            if not device_names:
                QMessageBox.information(self, "No device data", "No device time-series data found.")
                return
            fig = self.api.results.device_figure(device_names[0], index=idx)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load results", str(exc))
            return
        FigureDialog("Device Time History", fig, self).exec()

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
