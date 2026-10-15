"""Primary application window: wires the Qt GUI and the optional AI assistant panel over one shared ``FdsApi``.

Every widget either calls an ``FdsApi``/manager method in response to user action, or subscribes to the global
``EventBus`` and re-renders; it never mutates ``api.project`` directly. The behaviour lives in the mixins
imported below (one per menu area); this module only assembles the window.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.core.viewport import CameraPreset

from .shared import (
    _REFRESH_EVENTS,
)
from .explorer import ProjectExplorer

from .actions_file import ActionsFileMixin
from .actions_edit import ActionsEditMixin
from .actions_transform import ActionsTransformMixin
from .actions_view import ActionsViewMixin
from .actions_draw import ActionsDrawMixin
from .actions_model import ActionsModelMixin
from .actions_devices_hvac import ActionsDevicesHvacMixin
from .actions_run import ActionsRunMixin
from .actions_results import ActionsResultsMixin
from .actions_tools_help import ActionsToolsHelpMixin
from .menus_file_edit import MenusFileEditMixin
from .shell_bars import ShellBarsMixin
from .actions_shell import ActionsShellMixin
from .actions_editors import ActionsEditorsMixin
from .menus_view_draw import MenusViewDrawMixin
from .menus_model import MenusModelMixin
from .menus_run_results import MenusRunResultsMixin
from .menus_tools_help import MenusToolsHelpMixin
from .panels import PanelsMixin
from .workspaces import WorkspacesMixin
from .central_tabs import CentralTabsMixin
from .placeholders import PlaceholderMixin


class MainWindow(
    ActionsFileMixin,
    ActionsEditMixin,
    ActionsTransformMixin,
    ActionsViewMixin,
    ActionsDrawMixin,
    ActionsModelMixin,
    ActionsDevicesHvacMixin,
    ActionsRunMixin,
    ActionsResultsMixin,
    ActionsToolsHelpMixin,
    MenusFileEditMixin,
    MenusViewDrawMixin,
    MenusModelMixin,
    MenusRunResultsMixin,
    MenusToolsHelpMixin,
    PlaceholderMixin,
    ShellBarsMixin,
    ActionsShellMixin,
    ActionsEditorsMixin,
    PanelsMixin,
    WorkspacesMixin,
    CentralTabsMixin,
    QMainWindow,
):
    """Primary application window. The AI panel is one optional dock among many."""

    def __init__(self, api: Optional[FdsApi] = None) -> None:
        super().__init__()
        self.api = api or FdsApi()
        self.setWindowTitle("PyFDS")
        self.resize(1200, 750)
        self._current_project_path: Optional[str] = None
        self._clipboard_entity: Any = None
        self._view_bookmarks: dict = {}
        self._hvac_editor = None  # lazily-built singleton, see _on_hvac_network_editor

        self.dispatcher = AgentToolDispatcher(self.api)

        self.explorer = ProjectExplorer(self.api, self)
        self.explorer.itemDoubleClicked.connect(lambda item, col: self._on_edit_properties())
        self.explorer.entity_context_menu_requested.connect(self._on_explorer_context_menu)
        self.explorer_dock = QDockWidget("Project Explorer", self)
        self.explorer_dock.setObjectName("ProjectExplorerDock")
        self.explorer_dock.setWidget(self._build_explorer_container())
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)

        self.viewport_widget = self._build_viewport_widget()
        self._build_central_tabs()
        if hasattr(self.viewport_widget, "entity_picked"):
            self.viewport_widget.entity_picked.connect(self.explorer.select_entity)
        if hasattr(self.viewport_widget, "selection_changed"):
            self.viewport_widget.selection_changed.connect(self.explorer.select_entities)
        if hasattr(self.viewport_widget, "box_footprint_picked"):
            self.viewport_widget.box_footprint_picked.connect(self._on_box_footprint_picked)

        self.agent_dock = self._build_agent_dock()
        self.addDockWidget(Qt.RightDockWidgetArea, self.agent_dock)
        self._build_panels()
        self._build_extra_panels()
        self._build_cursor_label()

        self._build_menu()
        from pyfds.gui.extras import install_extras
        install_extras(self)      # room/library/run-monitor/results-viewer entries (see extras.py)
        self._restructure_menu_bar()
        self._install_editor_menu()
        self._build_toolbar()
        self._build_shell_bars()
        from pyfds.gui.icons import install_icons
        install_icons(self, "pyfds")      # task-coloured icons on every menu entry and toolbar button
        self._default_window_state = self.saveState()
        self._status_sub_ids = [self.api.subscribe(t, self._on_status_event) for t in _REFRESH_EVENTS]
        self._refresh_status()

    def _build_menu(self) -> None:
        """Build the complete menu bar: one builder per menu, in menu-bar order."""
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_draw_menu()
        self._build_model_menu()
        self._build_devices_menu()
        self._build_output_menu()
        self._build_hvac_menu()
        self._build_scenarios_menu()
        self._build_floors_menu()
        self._build_run_menu()
        self._build_results_menu()
        self._build_tools_menu()
        self._build_window_menu()
        self._build_help_menu()


    def _build_toolbar(self) -> None:
        """Quick-access icon-free toolbar — reuses the exact QAction objects
        from the menu bar (see _build_menu), so this is pure UX convenience,
        not a second code path."""
        bar = self.addToolBar("Quick Access")
        bar.setObjectName("QuickAccessToolBar")
        bar.setMovable(False)
        bar.addAction(self._new_action)
        bar.addAction(self._open_action)
        bar.addAction(self._save_as_action)
        bar.addSeparator()
        bar.addAction(self._undo_action)
        bar.addAction(self._redo_action)
        bar.addAction(self._delete_action)
        bar.addSeparator()
        bar.addAction(self._reset_view_action)
        bar.addAction(self._camera_preset_actions[CameraPreset.ISOMETRIC])
        bar.addAction(self._wireframe_action)
        bar.addSeparator()
        bar.addAction(self._validate_action)
        bar.addAction(self._run_action)

    def _on_status_event(self, event) -> None:
        self._refresh_status()
        self._sync_shell_bars()

    def _refresh_status(self) -> None:
        # a long title would push the right-hand labels (cursor, selection, run) out of view: cut it short
        lines = [ln if not ln.startswith("Title") or len(ln) < 36 else ln[:33] + "..." for ln in self.api.info().split("\n")]
        self.statusBar().showMessage("   |   ".join(lines))

    def _build_agent_dock(self) -> QDockWidget:
        dock = QDockWidget("AI Assistant", self)
        dock.setObjectName("AIAssistantDock")
        try:
            import anthropic  # noqa: F401
        except ImportError:
            dock.setWidget(QLabel(
                "AI assistant unavailable.\n\n"
                "Install with:\n  pip install pyfds[agent_anthropic]",
                dock,
            ))
            return dock

        from pyfds.agent import AgentSession
        from pyfds.gui.agent_panel import AgentChatPanel

        session = AgentSession(dispatcher=self.dispatcher)
        dock.setWidget(AgentChatPanel(session, self.api.history, dock))
        return dock

    def _build_viewport_widget(self) -> Any:
        # QtInteractor needs a real OpenGL-capable native window. Qt's
        # offscreen QPA platform (used by the headless test suite) cannot
        # provide one on this machine — attempting construction there is a
        # native access violation, not a catchable Python exception. Never
        # build the real widget under that platform.
        if QApplication.instance().platformName() == "offscreen":
            return QLabel(
                "3D viewport unavailable under the offscreen Qt platform "
                "(no OpenGL context here).\nRun the desktop app normally to "
                "see the 3D view.",
                self,
            )
        try:
            from pyfds.gui.viewport_3d import Viewport3D
        except ImportError:
            return QLabel(
                "3D viewport unavailable.\n\nInstall with:\n  pip install pyfds[viewport]",
                self,
            )
        return Viewport3D(self.api, self)

    def closeEvent(self, event) -> None:
        if self._results_window is not None and not self._results_window.close():
            event.ignore()                # the user cancelled "Save changes?" in the results tab: stay open
            return
        self.explorer.shutdown()
        self.output_panel.shutdown()
        if getattr(self, "_persist_layout", False):
            self.save_layout()
        if hasattr(self.viewport_widget, "shutdown"):
            self.viewport_widget.shutdown()
        for sub_id in self._status_sub_ids + self._panel_sub_ids:
            self.api.unsubscribe(sub_id)
        super().closeEvent(event)
