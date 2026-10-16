"""Model menu actions: add entity, simulation parameters, validate, scenarios and floors."""
from __future__ import annotations

import copy
from typing import Any, Optional

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from pyfds.agent.registry import get_tool
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.property_schema import build_edit_schema
from pyfds.gui.report_dialog import TextReportDialog


class ActionsModelMixin:
    def _on_add_entity(self, tool_name: str) -> None:
        tool = get_tool(tool_name)
        dialog = SchemaFormDialog(tool.name, tool.description, tool.input_schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not add entity", str(exc))

    def _on_simulation_parameters(self) -> Any:
        """Edit the global parameters (time, output, environment, pressure, radiation) in one dialog."""
        from pyfds.gui.editors.sim_params import SimulationParametersDialog
        dialog = SimulationParametersDialog(self.api, self)
        self._sim_params_dialog = dialog
        dialog.exec()
        return dialog

    def _on_validate(self) -> None:
        report = self.api.validation.validate()
        self.validation_panel.show_report(report)
        self._show_messages(self.validation_panel)

    def _on_auto_fix(self) -> None:
        self.api.validation.auto_fix()
        # auto_fix() mutates entities directly (not through CommandPipeline), so
        # it fires no COMMAND_EXECUTED event — refresh the tree/status explicitly.
        report = self.api.validation.validate()
        self.validation_panel.show_report(report)
        self.explorer.refresh()
        self._refresh_status()
        TextReportDialog("Auto-Fix Report (after fixing)", str(report), self).exec()

    def _on_new_scenario(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        }
        dialog = SchemaFormDialog("New Scenario", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.scenarios.create(values["name"], values.get("description", ""))
        except Exception as exc:
            QMessageBox.critical(self, "Could not create scenario", str(exc))
        else:
            self.explorer.refresh()

    def _on_clone_scenario(self, base_name: Optional[str] = None) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        schema = {
            "type": "object",
            "properties": {
                "base_name": {"type": "string", "enum": names, "default": base_name or names[0]},
                "new_name": {"type": "string"},
            },
            "required": ["base_name", "new_name"],
        }
        dialog = SchemaFormDialog("Clone Scenario", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.scenarios.clone(values["base_name"], values["new_name"])
        except Exception as exc:
            QMessageBox.critical(self, "Could not clone scenario", str(exc))
        else:
            self.explorer.refresh()

    def _on_apply_scenario_dialog(self) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        name, ok = QInputDialog.getItem(self, "Apply Scenario", "Scenario:", names, 0, False)
        if not ok or not name:
            return
        self._on_apply_scenario(name)

    def _on_apply_scenario(self, name: str) -> None:
        try:
            self.api.scenarios.apply(name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not apply scenario", str(exc))
        else:
            self.explorer.refresh()
            self._refresh_status()

    def _on_reset_scenario(self) -> None:
        if self.api.scenarios.active is None:
            QMessageBox.information(self, "No active scenario", "No scenario is currently applied.")
            return
        self.api.scenarios.reset()
        self.explorer.refresh()
        self._refresh_status()

    def _on_set_scenario_override(self, entity: Any) -> None:
        names = [s.name for s in self.api.scenarios.all()]
        if not names:
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        edit_schema = build_edit_schema(entity)
        fields = list(edit_schema["properties"].keys())
        if not fields:
            QMessageBox.information(self, "No editable fields", f"{entity.name} has no simple fields to override.")
            return
        schema = {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": names},
                "field_name": {"type": "string", "enum": fields},
                "value": {"type": "string", "description": "New value for this field in the scenario."},
            },
            "required": ["scenario", "field_name", "value"],
        }
        dialog = SchemaFormDialog(f"Set Scenario Override — {entity.name}", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        field_name = values["field_name"]
        prop = edit_schema["properties"].get(field_name, {})
        try:
            value = self._coerce_scenario_value(values["value"], prop)
            self.api.scenarios.set_override(values["scenario"], entity, field_name, value)
        except Exception as exc:
            QMessageBox.critical(self, "Could not set override", str(exc))

    @staticmethod
    def _coerce_scenario_value(raw: str, prop: dict) -> Any:
        """Type-coerce a scenario-override value against *its target
        field's* schema — can't reuse SchemaFormDialog's own coercion
        because that's keyed to the "value" field's own (fixed, "string")
        schema entry, not the dynamically chosen target field."""
        ptype = prop.get("type")
        if ptype == "number":
            return float(raw)
        if ptype == "integer":
            return int(raw)
        if ptype == "boolean":
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if ptype == "array":
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            item_type = prop.get("items", {}).get("type")
            if item_type == "number":
                return [float(p) for p in parts]
            if item_type == "integer":
                return [int(p) for p in parts]
            return parts
        return raw

    def _on_export_scenarios(self) -> None:
        if not self.api.scenarios.all():
            QMessageBox.information(self, "No scenarios", "Create a scenario first.")
            return
        dirpath = QFileDialog.getExistingDirectory(self, "Export Scenarios Folder")
        if not dirpath:
            return
        try:
            written = self.api.scenarios.export_all(dirpath)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export scenarios", str(exc))
        else:
            self.explorer.refresh()
            lines = "\n".join(f"{name}: {path}" for name, path in written.items())
            QMessageBox.information(self, "Exported", f"{len(written)} scenario(s) exported:\n{lines}")

    def _on_define_floor(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "z_min": {"type": "number"},
                "z_max": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["name", "z_min", "z_max"],
        }
        dialog = SchemaFormDialog("Define Floor", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            self.api.floors.define_floor(
                values["name"], values["z_min"], values["z_max"], values.get("description", "")
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not define floor", str(exc))
        else:
            self.explorer.refresh()

    def _on_auto_assign_floors(self) -> None:
        if not self.api.floors.all_floors():
            QMessageBox.information(self, "No floors", "Define a floor first.")
            return
        count = self.api.floors.auto_assign_all()
        self.explorer.refresh()
        QMessageBox.information(self, "Auto-Assign", f"{count} entities assigned to a floor by elevation.")

    def _on_assign_to_floor(self) -> None:
        floors = [f.name for f in self.api.floors.all_floors()]
        if not floors:
            QMessageBox.information(self, "No floors", "Define a floor first.")
            return
        selected = self.explorer.selected()
        if selected is None or selected[0] in ("scenarios", "floors"):
            QMessageBox.information(self, "No entity selected", "Select an entity in the Project Explorer first.")
            return
        _attr, entity = selected
        floor_name, ok = QInputDialog.getItem(self, "Assign to Floor", f"Floor for {entity.name}:", floors, 0, False)
        if not ok or not floor_name:
            return
        try:
            self.api.floors.assign(entity, floor_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not assign floor", str(exc))
        else:
            self.explorer.refresh()

    def _on_export_floors(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Floors", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            self.api.floors.export_floors(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not export floors", str(exc))
        else:
            QMessageBox.information(self, "Exported", f"Floors exported to:\n{path}")

    def _on_import_floors(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Floors", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            count = self.api.floors.import_floors(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import floors", str(exc))
        else:
            self.explorer.refresh()
            QMessageBox.information(
                self, "Imported", f"Floors imported; {count} entity assignment(s) re-matched by name."
            )
