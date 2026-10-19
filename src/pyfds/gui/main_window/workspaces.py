"""Extra panels (Layers, Output, Results), workspace presets (Model / Run / Results), saved layout and status labels."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QLabel

from pyfds.gui.panels.layers_panel import LayersPanel
from pyfds.gui.panels.output_panel import OutputPanel
from pyfds.gui.panels.results_panel import ResultsPanel

from .layout_tools import _LAYOUT_VERSION

_SETTINGS = ("PyFDS", "PyFDS")


class WorkspacesMixin:
    def _build_extra_panels(self) -> None:
        """Layers beside the explorer; Output and Results as extra tabs of the bottom Messages dock."""
        self.layers_panel = LayersPanel(self.api, self)
        self.layers_dock = QDockWidget("Layers", self)
        self.layers_dock.setObjectName("LayersDock")
        self.layers_dock.setWidget(self.layers_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.layers_dock)
        self.tabifyDockWidget(self.explorer_dock, self.layers_dock)
        self.explorer_dock.raise_()

        self.output_panel = OutputPanel(self.api, self)
        self.results_panel = ResultsPanel(self._results_folder, self._open_results_from_panel, self)
        self.messages_tabs.addTab(self.results_panel, "Results")
        self.messages_tabs.addTab(self.output_panel, "Output")

        self.selection_label = QLabel("")
        self.run_label = QLabel("")
        self.statusBar().addPermanentWidget(self.selection_label)
        self.statusBar().addPermanentWidget(self.run_label)
        self.explorer.itemSelectionChanged.connect(self._update_selection_label)
        self._update_selection_label()
        self.run_panel.timer.timeout.connect(self._update_run_label)

    # -- results ----------------------------------------------------------------------------------
    def _results_folder(self):
        folder = getattr(self, "_last_run_dir", None)
        if folder:
            return folder
        path = getattr(self, "_current_project_path", None)
        return str(Path(path).parent) if path else None

    def _open_results_from_panel(self, smv: str) -> None:
        getattr(self, "_show_results_window", lambda s: None)(smv)

    # -- status bar -------------------------------------------------------------------------------
    def _update_selection_label(self) -> None:
        n = len(self.explorer.selected_entities())
        self.selection_label.setText(f"{n} selected" if n else "")

    def _update_run_label(self) -> None:
        panel = self.run_panel
        pct = f" {panel.bar.value() / 10:.0f}%" if panel.state == "running" else ""
        self.run_label.setText(f"Run: {panel.state}{pct}")

    # -- workspaces -------------------------------------------------------------------------------
    def _apply_workspace(self, name: str) -> None:
        """Show the panels that suit a task: ``model``, ``run`` or ``results``."""
        self.toggle_focus_mode(False)
        self._layout_was_reset()
        shown = {
            "model": {self.explorer_dock, self.properties_dock, self.agent_dock},
            "run": {self.explorer_dock, self.messages_dock},
            "results": {self.messages_dock},
        }[name]
        tab = {"model": self.validation_panel, "run": self.run_panel, "results": self.results_panel}[name]
        for dock in (self.explorer_dock, self.layers_dock, self.properties_dock, self.agent_dock, self.messages_dock):
            dock.setVisible(dock in shown or (dock is self.layers_dock and name == "model"))
        if name != "model":
            self.messages_tabs.setCurrentWidget(tab)
        if name == "results":
            self.results_panel.refresh()
        if name == "model":
            self.show_model_tab()
        self.statusBar().showMessage(f"Workspace: {name}.", 4000)

    # -- layout persistence (real application only; tests never touch the settings) ---------------
    def restore_saved_layout(self) -> None:
        state = QSettings(*_SETTINGS).value("main_window/state")
        geometry = QSettings(*_SETTINGS).value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state, _LAYOUT_VERSION)

    def has_saved_geometry(self) -> bool:
        return QSettings(*_SETTINGS).value("main_window/geometry") is not None

    def save_layout(self) -> None:
        settings = QSettings(*_SETTINGS)
        settings.setValue("main_window/state", self.saveState(_LAYOUT_VERSION))
        settings.setValue("main_window/geometry", self.saveGeometry())
