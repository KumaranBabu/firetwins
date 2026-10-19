"""File menu actions: new / open / save / recent / import / export / project settings."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from pyfds.gui.entity_dialogs import SchemaFormDialog


class ActionsFileMixin:
    def _on_save(self) -> None:
        """Save to the last-used path; falls back to Save As if the project
        has never been saved/opened in this session."""
        if self._current_project_path is None:
            self._on_save_as()
            return
        try:
            self.api.save(self._current_project_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _on_preferences(self) -> None:
        """Shared by File > Preferences and Tools > Preferences — one real
        dialog, not two separate placeholders, since they're the same thing."""
        cfg = self.api.config
        schema = {
            "type": "object",
            "properties": {
                "fds_binary": {"type": "string", "default": cfg.get("fds_binary", "fds")},
                "smv_binary": {"type": "string", "default": cfg.get("smv_binary", "smokeview")},
                "mpiexec_binary": {"type": "string", "default": cfg.get("mpiexec_binary", "mpiexec")},
                "default_mpi_processes": {"type": "integer", "default": cfg.get("default_mpi_processes", 1)},
                "max_job_workers": {"type": "integer", "default": cfg.get("max_job_workers", 4)},
                "auto_validate": {"type": "boolean", "default": cfg.get("auto_validate", True)},
                "auto_save": {"type": "boolean", "default": cfg.get("auto_save", False)},
                "create_backup_on_open": {"type": "boolean", "default": cfg.get("create_backup_on_open", True)},
                "undo_depth": {"type": "integer", "default": cfg.get("undo_depth", 200)},
                "log_level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                              "default": cfg.get("log_level", "INFO")},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Preferences", "Kept between sessions (user_data/config.json).", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        cfg.set_many(values)
        if values.get("undo_depth"):
            self.api.history.set_depth(int(values["undo_depth"]))
        try:
            cfg.save()
        except OSError as exc:
            QMessageBox.warning(self, "Preferences", "The settings apply now but could not be saved:" + chr(10) + str(exc))

    _RECENT_MAX = 10

    def _recent_paths(self) -> list:
        settings = QSettings("PyFDS", "PyFDS")
        paths = settings.value("recent_projects", [])
        if isinstance(paths, str):
            paths = [paths]
        return list(paths or [])

    def _add_recent_path(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        paths = [p for p in self._recent_paths() if p != resolved]
        paths.insert(0, resolved)
        QSettings("PyFDS", "PyFDS").setValue("recent_projects", paths[:self._RECENT_MAX])
        self._rebuild_recent_menu()

    def _on_clear_recent(self) -> None:
        QSettings("PyFDS", "PyFDS").setValue("recent_projects", [])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        """Numbered entries with the full path as the tooltip; files that were deleted or moved drop out of the list."""
        self._recent_submenu.clear()
        paths = self._recent_paths()
        kept = [p for p in paths if Path(p).exists()]
        if kept != paths:
            QSettings("PyFDS", "PyFDS").setValue("recent_projects", kept)
        if not kept:
            action = self._recent_submenu.addAction("(No Recent Projects)")
            action.setEnabled(False)
            return
        for n, path in enumerate(kept, start=1):
            label = f"&{n} {Path(path).name or path}" if n < 10 else f"{n} {Path(path).name or path}"
            action = self._recent_submenu.addAction(label, lambda checked=False, p=path: self._on_open_recent(p))
            action.setToolTip(path)
            action.setStatusTip(path)
        self._recent_submenu.addSeparator()
        self._recent_submenu.addAction("&Clear Recent Projects", self._on_clear_recent)

    def _on_open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(self, "File not found", f"{path}\n\nThis file no longer exists.")
            paths = [p for p in self._recent_paths() if p != path]
            QSettings("PyFDS", "PyFDS").setValue("recent_projects", paths)
            self._rebuild_recent_menu()
            return
        try:
            self.api.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._current_project_path = path
        self._add_recent_path(path)

    def _on_import_stl(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import STL Geometry", "", "STL Files (*.stl)")
        if not path:
            return
        surf_id, ok = QInputDialog.getText(self, "Import STL", "Surface ID (material/boundary condition):", text="INERT")
        if not ok:
            return
        try:
            self.api.geom.load_stl(path, surf_id=surf_id or "INERT")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
        else:
            self.explorer.refresh()

    def _on_export_as_fds(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export as FDS", "", "FDS Files (*.fds)")
        if not path:
            return
        if not path.lower().endswith(".fds"):
            path += ".fds"
        try:
            self.api.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _on_project_settings(self) -> None:
        project = self.api.project
        schema = {
            "type": "object",
            "properties": {
                "chid": {"type": "string", "default": project.chid,
                          "description": "FDS CHID — base name for all output files."},
                "title": {"type": "string", "default": project.title},
            },
            "required": ["chid"],
        }
        dialog = SchemaFormDialog("Project Settings", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.set_property(project, "chid", values["chid"])
            self.api.set_property(project, "title", values.get("title", ""))
        except Exception as exc:
            QMessageBox.critical(self, "Could not update project settings", str(exc))

    def _on_new(self) -> None:
        self.api.new()
        self._current_project_path = None

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "FDS/PyFDS Files (*.fds *.pyfds)")
        if not path:
            return
        try:
            self.api.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
        else:
            self._current_project_path = path
            self._add_recent_path(path)

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "FDS Files (*.fds);;PyFDS Files (*.pyfds)")
        if not path:
            return
        try:
            self.api.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
        else:
            self._current_project_path = path
            self._add_recent_path(path)

    def _on_new_from_template(self) -> None:
        presets = self.api.templates.list_presets()
        if not presets:
            QMessageBox.information(self, "No templates", "No scenario templates are available.")
            return
        preset_name, ok = QInputDialog.getItem(
            self, "New From Template", "Template:", presets, 0, False
        )
        if not ok or not preset_name:
            return
        try:
            self.api.templates.apply(preset_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not apply template", str(exc))

    def _on_export_db(self, kind: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, f"Export {kind.title()} Database", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            getattr(self.api.engineering, f"export_{kind}")(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"{kind.title()} database exported to:\n{path}")

    def _on_export_db_all(self) -> None:
        dirpath = QFileDialog.getExistingDirectory(self, "Export Database Folder")
        if not dirpath:
            return
        try:
            self.api.engineering.export_db(dirpath)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Database exported to:\n{dirpath}")
