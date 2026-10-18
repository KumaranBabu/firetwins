"""Devices, Output and HVAC menu actions."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import QDialog, QMessageBox

from pyfds.agent.registry import get_tool
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.report_dialog import TextReportDialog


class ActionsDevicesHvacMixin:
    def _on_add_device_by_quantity(self, quantity: str, dialog_title: str) -> None:
        """Shared path for every 'named sensor' menu item — each is really
        just the generic add_device tool with its QUANTITY default
        pre-filled; the dropdown still lets the user pick any DEVC quantity."""
        tool = get_tool("add_device")
        schema = copy.deepcopy(tool.input_schema)
        schema["properties"]["quantity"]["default"] = quantity
        dialog = SchemaFormDialog(dialog_title, tool.description, schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.dispatcher.call(tool.name, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not add device", str(exc))

    def _on_add_heat_flux(self) -> None:
        self._on_add_device_by_quantity("HEAT FLUX", "Add Heat Flux Sensor")

    def _on_add_smoke_detector(self) -> None:
        self._on_add_device_by_quantity("OPTICAL DENSITY", "Add Smoke Detector")

    def _on_add_beam_detector(self) -> None:
        self._on_add_device_by_quantity("EXTINCTION COEFFICIENT", "Add Beam Detector")

    def _on_add_gas_sensor(self) -> None:
        self._on_add_device_by_quantity("CARBON MONOXIDE", "Add Gas Sensor")

    def _on_add_anemometer(self) -> None:
        self._on_add_device_by_quantity("VELOCITY", "Add Anemometer")

    def _on_add_nozzle(self) -> None:
        # Mechanically identical to a sprinkler in FDS (a PROP-referenced
        # spray device at a point) — reuses add_sprinkler rather than
        # inventing a separate, redundant "add_nozzle" tool.
        self._on_add_entity("add_sprinkler")

    def _on_add_velocity_probe(self) -> None:
        self._on_add_device_by_quantity("VELOCITY", "Add Velocity Probe")

    def _on_add_pressure_probe(self) -> None:
        self._on_add_device_by_quantity("PRESSURE", "Add Pressure Probe")

    def _on_add_hrr_device(self) -> None:
        self._on_add_device_by_quantity("HRR", "Add Heat Release Rate Device")

    def _on_add_layer_zoning(self) -> None:
        self._on_add_device_by_quantity("LAYER HEIGHT", "Add Layer Zoning Device")

    def _on_add_flow_measurement(self) -> None:
        self._on_add_device_by_quantity("MASS FLOW RATE", "Add Flow Measurement")

    def _on_add_statistics_device(self) -> None:
        self._on_add_device_by_quantity("TEMPERATURE", "Add Statistics Device (fill in a statistic)")

    def _on_output_frequency(self) -> None:
        dump = self.api.project.dump
        schema = {
            "type": "object",
            "properties": {
                "dt_slcf": {"type": "number", "default": dump.dt_slcf, "description": "Slice file output interval, s."},
                "dt_bndf": {"type": "number", "default": dump.dt_bndf, "description": "Boundary file output interval, s."},
                "dt_isof": {"type": "number", "default": dump.dt_isof, "description": "Isosurface output interval, s."},
                "dt_pl3d": {"type": "number", "default": dump.dt_pl3d, "description": "Plot3D output interval, s."},
                "dt_devc": {"type": "number", "default": dump.dt_devc, "description": "Device output interval, s."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Output Frequency", "Maps to the &DUMP namelist.", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            for field_name, value in dialog.values().items():
                self.api.set_property(dump, field_name, value)
        except Exception as exc:
            QMessageBox.critical(self, "Could not update output frequency", str(exc))

    def _on_hvac_network_editor(self) -> None:
        """Open the HVAC Network Editor (2D schematic node/duct diagram),
        reusing the same instance on repeat opens rather than stacking
        windows."""
        if self._hvac_editor is None:
            from pyfds.gui.hvac_network_editor import HvacNetworkEditorDialog
            self._hvac_editor = HvacNetworkEditorDialog(self.api, self)
        self._hvac_editor.show()
        self._hvac_editor.raise_()
        self._hvac_editor.activateWindow()

    def _on_hvac_solver_setup(self) -> None:
        """Configure HVAC solver parameters and run the network solver."""
        schema = {
            "type": "object",
            "properties": {
                "rho": {"type": "number", "default": 1.2,
                        "description": "Air density (kg/m³)."},
                "max_iter": {"type": "integer", "default": 200,
                             "description": "Maximum Hardy-Cross iterations."},
                "tol": {"type": "number", "default": 1e-5,
                        "description": "Convergence tolerance (m³/s)."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("HVAC Solver Setup", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            result = self.api.hvac.solve_network(
                rho=values.get("rho", 1.2),
                max_iter=values.get("max_iter", 200),
                tol=values.get("tol", 1e-5),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not solve HVAC network", str(exc))
            return
        TextReportDialog("HVAC Solver Result", result.summary(), self).exec()

    def _on_hvac_diagnostics(self) -> None:
        """Run the HVAC network solver with default parameters."""
        try:
            result = self.api.hvac.solve_network()
        except Exception as exc:
            QMessageBox.critical(self, "Could not run HVAC diagnostics", str(exc))
            return
        TextReportDialog("HVAC Diagnostics", result.summary(), self).exec()
