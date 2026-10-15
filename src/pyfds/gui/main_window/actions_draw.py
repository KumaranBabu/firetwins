"""Draw menu actions: primitives, boolean operations, draw modes, box-footprint picking."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from pyfds.gui.entity_dialogs import SchemaFormDialog


class ActionsDrawMixin:
    def _on_draw_sphere(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Sphere"},
                "center": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                           "default": [0.0, 0.0, 1.0], "description": "Center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center", "radius"],
        }
        dialog = SchemaFormDialog("Draw Sphere", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.sphere(
                values["center"], values["radius"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Sphere",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create sphere", str(exc))
        else:
            self.explorer.refresh()

    def _on_draw_cylinder(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Cylinder"},
                "center_base": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                 "default": [0.0, 0.0, 0.0], "description": "Base center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "height": {"type": "number", "default": 2.0},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center_base", "radius", "height"],
        }
        dialog = SchemaFormDialog("Draw Cylinder", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.cylinder(
                values["center_base"], values["radius"], values["height"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Cylinder",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create cylinder", str(exc))
        else:
            self.explorer.refresh()

    def _on_draw_cone(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Cone"},
                "center_base": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                 "default": [0.0, 0.0, 0.0], "description": "Base center [x, y, z] (m)"},
                "radius": {"type": "number", "default": 0.5},
                "height": {"type": "number", "default": 2.0},
                "surf_id": {"type": "string", "default": "INERT"},
            },
            "required": ["center_base", "radius", "height"],
        }
        dialog = SchemaFormDialog("Draw Cone", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.geom.cone(
                values["center_base"], values["radius"], values["height"],
                surf_id=values.get("surf_id") or "INERT",
                name=values.get("name") or "Cone",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create cone", str(exc))
        else:
            self.explorer.refresh()

    def _on_boolean_union(self) -> None:
        self._on_boolean_op("union")

    def _on_boolean_difference(self) -> None:
        self._on_boolean_op("difference")

    def _on_boolean_intersection(self) -> None:
        self._on_boolean_op("intersection")

    def _on_boolean_op(self, op: str) -> None:
        """Shared handler for Union/Difference/Intersection — needs exactly
        2 selected Geom entities. Source Geoms are left untouched; the
        result is added as a new, independent Geom (user's choice: keep
        both, don't replace)."""
        geoms = [e for a, e in self.explorer.selected_entities() if a == "geom"]
        if len(geoms) != 2:
            QMessageBox.information(
                self, f"Boolean {op.capitalize()}",
                "Select exactly 2 Geom entities first."
            )
            return
        geom_a, geom_b = geoms
        try:
            self.api.geom.boolean(op, geom_a, geom_b, name=f"{op.capitalize()}_{geom_a.name}_{geom_b.name}")
        except (ValueError, KeyError) as exc:
            QMessageBox.critical(self, f"Could not compute {op}", str(exc))

    def _on_set_draw_mode(self, tool_name: str) -> None:
        if hasattr(self.viewport_widget, "set_draw_mode"):
            self.viewport_widget.set_draw_mode(tool_name)
        self.statusBar().showMessage(
            f"Draw mode ({tool_name}): click two points in the 3D view to set the footprint..."
        )

    def _on_cancel_draw_mode(self) -> None:
        if hasattr(self.viewport_widget, "set_draw_mode"):
            self.viewport_widget.set_draw_mode(None)
        for action in self._draw_actions.values():
            action.setChecked(False)
        self._refresh_status()

    def _on_box_footprint_picked(
        self, tool_name: str, x_min: float, x_max: float, y_min: float, y_max: float
    ) -> None:
        # Viewport3D already auto-exited draw mode after the second click —
        # reflect that in the menu's checked state too.
        for action in self._draw_actions.values():
            action.setChecked(False)

        z_min, ok = QInputDialog.getDouble(self, "Height", "Z min (m):", 0.0, -1000.0, 1000.0, 2)
        if not ok:
            self._refresh_status()
            return
        z_max, ok = QInputDialog.getDouble(self, "Height", "Z max (m):", max(z_min + 3.0, 0.1), -1000.0, 1000.0, 2)
        if not ok:
            self._refresh_status()
            return

        try:
            self.dispatcher.call(tool_name, {"xb": [x_min, x_max, y_min, y_max, z_min, z_max]})
        except Exception as exc:
            QMessageBox.critical(self, "Could not create entity", str(exc))
        self._refresh_status()

    def _on_convert_to_blocks(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "STL File to Voxelize", "", "STL Files (*.stl)")
        if not path:
            return
        try:
            obstructions = self.api.geom.voxelize(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not voxelize", str(exc))
            return
        QMessageBox.information(self, "Voxelize Complete", f"Created {len(obstructions)} obstruction(s).")
