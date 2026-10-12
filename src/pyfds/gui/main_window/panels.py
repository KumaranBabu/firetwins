"""Dockable panels of the main window: Properties (right), Validation and Run Monitor (bottom tabs)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMessageBox, QTabWidget

from pyfds.gui.panels import PropertiesPanel, ValidationPanel
from pyfds.gui.run_monitor import RunMonitorPanel

from .shared import _REFRESH_EVENTS


class PanelsMixin:
    def _build_panels(self) -> None:
        """Create the Properties dock and the bottom Messages dock, and wire them to the explorer."""
        self.properties_panel = PropertiesPanel(
            self.api, self, on_error=lambda m: QMessageBox.critical(self, "Could not update properties", m))
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("PropertiesDock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)
        self.splitDockWidget(self.properties_dock, self.agent_dock, Qt.Vertical)   # AI Assistant below

        self.validation_panel = ValidationPanel(self)
        self.run_panel = RunMonitorPanel(self)
        self.messages_tabs = QTabWidget(self)
        self.messages_tabs.addTab(self.validation_panel, "Validation")
        self.messages_tabs.addTab(self.run_panel, "Run Monitor")
        self.messages_dock = QDockWidget("Messages", self)
        self.messages_dock.setObjectName("MessagesDock")
        self.messages_dock.setWidget(self.messages_tabs)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.messages_dock)
        self.resizeDocks([self.messages_dock], [210], Qt.Vertical)   # keep the 3D view the biggest area
        self.messages_dock.hide()                 # opens when a validation or a run produces something

        self.explorer.itemSelectionChanged.connect(self._on_selection_changed)
        self.validation_panel.validate_requested.connect(self._on_validate)
        self.validation_panel.auto_fix_requested.connect(self._on_auto_fix)
        self.validation_panel.entity_activated.connect(self._on_finding_activated)
        self._panel_sub_ids = [self.api.subscribe(t, self._on_panel_event) for t in _REFRESH_EVENTS]

    # -- Properties --------------------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        selected = self.explorer.selected()
        self.properties_panel.show_entity(*(selected if selected else (None, None)))

    def _on_panel_event(self, event) -> None:
        """A command changed the model: refresh the form unless the user is typing in it."""
        if not self.properties_panel.isAncestorOf(self.focusWidget()):
            self.properties_panel.reload()
        if hasattr(self, "layers_panel"):
            self.layers_panel.sync()

    # -- Messages ----------------------------------------------------------------------------------
    def _show_messages(self, panel) -> None:
        self.messages_tabs.setCurrentWidget(panel)
        self.messages_dock.show()
        self.messages_dock.raise_()

    def _on_finding_activated(self, name: str) -> None:
        match = self.explorer.find_entity_by_name(name)
        if match is not None:
            self.explorer.setCurrentItem(match)
