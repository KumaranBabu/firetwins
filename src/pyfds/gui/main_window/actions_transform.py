"""Move / Rotate / Scale / Mirror Selected and snap settings (the maths lives in ``api.transform``)."""
from __future__ import annotations

from typing import Any, Callable, List

from PySide6.QtWidgets import QDialog, QMessageBox

from pyfds.gui.entity_dialogs import SchemaFormDialog


class ActionsTransformMixin:
    def _resolve_transform_targets(self) -> List[Any]:
        """Selected entities, expanded so selecting one grouped entity pulls in its whole group."""
        return self.api.transform.expand_groups(e for _, e in self.explorer.selected_entities())

    def _run_transform(self, title: str, schema: dict, call: Callable[[List[Any], dict], dict]) -> None:
        """Ask for the parameters, run ``call(entities, values)`` and report; one undo step."""
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, title, "Nothing selected.")
            return
        dialog = SchemaFormDialog(title, "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            result = call(entities, dialog.values())
        except ValueError as exc:
            QMessageBox.information(self, title, str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, f"Could not {title.lower()}", str(exc))
            return
        suffix = f" ({result['skipped']} skipped)" if result["skipped"] else ""
        self.statusBar().showMessage(f"{title}: {result['transformed']} object(s) transformed{suffix}.")

    def _on_move_selected(self) -> None:
        schema = {"type": "object", "required": [], "properties": {
            "dx": {"type": "number", "default": 0.0}, "dy": {"type": "number", "default": 0.0},
            "dz": {"type": "number", "default": 0.0}}}
        self._run_transform("Move Selected", schema, lambda ents, v: self.api.transform.move(
            ents, v.get("dx", 0.0), v.get("dy", 0.0), v.get("dz", 0.0), expand_groups=False))

    def _on_rotate_selected(self) -> None:
        schema = {"type": "object", "required": [], "properties": {
            "degrees": {"type": "number", "default": 90.0,
                        "description": "About Z, shared pivot. XB entities (Obstruction/Mesh/Vent/Hole) "
                                       "only accept multiples of 90."}}}
        self._run_transform("Rotate Selected", schema, lambda ents, v: self.api.transform.rotate(
            ents, v.get("degrees", 90.0), expand_groups=False))

    def _on_scale_selected(self) -> None:
        schema = {"type": "object", "required": [], "properties": {
            "factor": {"type": "number", "default": 1.0,
                       "description": "Uniform scale about the selection's shared centroid."}}}
        self._run_transform("Scale Selected", schema, lambda ents, v: self.api.transform.scale(
            ents, v.get("factor", 1.0), expand_groups=False))

    def _on_mirror_selected(self) -> None:
        schema = {"type": "object", "required": [], "properties": {
            "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"}}}
        self._run_transform("Mirror Selected", schema, lambda ents, v: self.api.transform.mirror(
            ents, v.get("axis", "X"), expand_groups=False))

    def _on_snap_settings(self) -> None:
        snap = self.api.viewport.state.snap
        schema = {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": snap.enabled},
                "grid_size": {"type": "number", "default": snap.grid_size, "description": "Metres per grid division."},
                "angle_step_deg": {"type": "number", "default": snap.angle_step_deg},
                "snap_to_grid": {"type": "boolean", "default": snap.snap_to_grid},
                "snap_to_vertex": {"type": "boolean", "default": snap.snap_to_vertex},
                "snap_to_edge": {"type": "boolean", "default": snap.snap_to_edge},
                "snap_to_face": {"type": "boolean", "default": snap.snap_to_face},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Snap Settings", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.api.viewport.set_snap(**dialog.values())
