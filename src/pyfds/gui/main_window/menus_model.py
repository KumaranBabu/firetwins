"""Menu construction: model, devices, output, hvac."""
from __future__ import annotations

from .shared import (
    _DEVICE_ACTIONS,
    _HVAC_ACTIONS,
    _MODEL_ACTIONS,
    _OUTPUT_ACTIONS,
)


class MenusModelMixin:
    def _build_model_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # MODEL MENU (20 items)
        # ════════════════════════════════════════════════════════════════════════
        model_menu = self.menuBar().addMenu("&Model")

        # Existing entity add actions
        for label, tool_name in _MODEL_ACTIONS:
            model_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        model_menu.addSeparator()

        # Additional model items (new)
        model_menu.addAction("Add &Control Element...", self._on_add_control)
        model_menu.addAction("Add &Property / Prop...", self._on_add_prop)
        model_menu.addAction("Add S&pecies...", self._on_add_species)

        model_menu.addSeparator()

        # Simulation configuration
        model_menu.addAction("&Simulation Parameters...", self._on_simulation_parameters)

        model_menu.addSeparator()

        # Validation and repair
        self._validate_action = model_menu.addAction("&Validate Project", self._on_validate)
        model_menu.addAction("Auto-&Fix", self._on_auto_fix)
        model_menu.addAction("Geometry &Repair...", self._on_geometry_repair)

        model_menu.addSeparator()

        # Geometry operations
        model_menu.addAction("Convert to &Blocks (Voxelize STL)...", self._on_convert_to_blocks)


    def _build_devices_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # DEVICES MENU (12 items) — Expanded from 3
        # ════════════════════════════════════════════════════════════════════════
        devices_menu = self.menuBar().addMenu("&Devices")

        # Existing device types
        for label, tool_name in _DEVICE_ACTIONS:
            devices_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        devices_menu.addSeparator()

        # Additional device types (new)
        devices_menu.addAction("Add &Heat Flux Sensor...", self._on_add_heat_flux)
        devices_menu.addAction("Add &Smoke Detector...", self._on_add_smoke_detector)
        devices_menu.addAction("Add &Beam Detector...", self._on_add_beam_detector)
        devices_menu.addAction("Add &Gas Sensor...", self._on_add_gas_sensor)
        devices_menu.addAction("Add &Anemometer...", self._on_add_anemometer)
        devices_menu.addAction("Add &Nozzle...", self._on_add_nozzle)
        devices_menu.addAction("Add &Velocity Probe...", self._on_add_velocity_probe)
        devices_menu.addAction("Add &Pressure Probe...", self._on_add_pressure_probe)

        devices_menu.addSeparator()

        # Device management
        self._device_labels_action = devices_menu.addAction("Device &Labels")
        self._device_labels_action.setCheckable(True)
        self._device_labels_action.toggled.connect(self._on_toggle_device_labels)


    def _build_output_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # OUTPUT MENU (5 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        output_menu = self.menuBar().addMenu("&Output")

        for label, tool_name in _OUTPUT_ACTIONS:
            output_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        output_menu.addSeparator()

        # Output Frequency (new)
        output_menu.addAction("Output &Frequency...", self._on_output_frequency)


    def _build_hvac_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # HVAC MENU (9 items) — Expanded from 6
        # ════════════════════════════════════════════════════════════════════════
        hvac_menu = self.menuBar().addMenu("HVA&C")

        # Existing HVAC components
        for label, tool_name in _HVAC_ACTIONS:
            hvac_menu.addAction(label, lambda checked=False, t=tool_name: self._on_add_entity(t))

        hvac_menu.addSeparator()

        # Additional HVAC tools (new)
        hvac_menu.addAction("&Network Editor", self._on_hvac_network_editor)
        hvac_menu.addAction("&Solver Setup...", self._on_hvac_solver_setup)
        hvac_menu.addAction("&Diagnostics", self._on_hvac_diagnostics)
