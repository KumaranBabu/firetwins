"""Menu entries that used to say "Coming soon" and now do real work (plan step F1): Add Control / Prop / Species, the
Grid / Axes / Device Labels toggles, Geometry Repair, Export Geometry and the Examples browser."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFileDialog, QMessageBox

from pyfds.core.viewport import VisibilityFlags
from pyfds.gui.examples_dialog import ExamplesDialog
from pyfds.gui.repair_dialog import GeometryRepairDialog


class ActionsMiscMixin:
    # -- Model > Add ... -------------------------------------------------------------------------------------
    def _on_add_control(self) -> Any:
        """A new activation control, opened in the Edit Activation Controls dialog."""
        return self._on_edit_activation_controls(new=True)

    def _on_add_prop(self) -> Any:
        return self._on_edit_collection("props", "Edit Properties", new=True)

    def _on_add_species(self) -> Any:
        return self._on_edit_collection("species", "Edit Species", new=True)

    # -- View / Devices toggles ------------------------------------------------------------------------------
    def _set_flag(self, flag: VisibilityFlags, on: bool) -> None:
        self.api.viewport.set_visibility(flag, bool(on))

    def _on_toggle_grid(self, checked: bool) -> None:
        self._set_flag(VisibilityFlags.GRID, checked)

    def _on_toggle_axes(self, checked: bool) -> None:
        self._set_flag(VisibilityFlags.AXES, checked)

    def _on_toggle_device_labels(self, checked: bool) -> None:
        self._set_flag(VisibilityFlags.LABELS, checked)

    # -- Geometry --------------------------------------------------------------------------------------------
    def _on_geometry_repair(self) -> GeometryRepairDialog:
        picked = self.explorer.selected()
        select = picked[1].name if picked is not None and picked[0] == "geom" else None
        dialog = GeometryRepairDialog(self.api, self, select)
        self._repair_dialog = dialog
        dialog.exec()
        return dialog

    def _on_export_geometry(self, path: str = "", include_obstructions: Any = None) -> int:
        """Write the imported/drawn shapes to an STL or OBJ file. Returns the triangle count (0 if cancelled)."""
        if not self.api.geom.all() and not self.api.obstructions.all():
            QMessageBox.information(self, "Export Geometry", "There is no geometry to export.")
            return 0
        path = path or QFileDialog.getSaveFileName(self, "Export Geometry", "geometry.stl",
                                                   "STL (*.stl);;OBJ (*.obj)")[0]
        if not path:
            return 0
        if include_obstructions is None:
            include_obstructions = bool(self.api.obstructions.all()) and QMessageBox.question(
                self, "Export Geometry", "Also write the obstructions as boxes?") == QMessageBox.Yes
        try:
            count = self.api.geom.export_geometry(path, include_obstructions=bool(include_obstructions))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Export Geometry", str(exc))
            return 0
        self.statusBar().showMessage(f"Wrote {count} triangles to {path}", 6000)
        return count

    # -- Help ------------------------------------------------------------------------------------------------
    def _on_examples(self) -> ExamplesDialog:
        def loaded(info):
            self._current_project_path = None
            self.explorer.refresh()
            self.statusBar().showMessage(f"Opened example: {info['title']}", 6000)
        dialog = ExamplesDialog(self.api, self, loaded)
        self._examples_dialog = dialog
        dialog.exec()
        return dialog
