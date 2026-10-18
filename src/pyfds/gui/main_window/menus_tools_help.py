"""Menu construction: tools, window, help."""
from __future__ import annotations

from .shared import (
    _FDS_USER_GUIDE,
    _PYROSIM_USER_MANUAL,
    _SMV_VERIFICATION_GUIDE,
)


class MenusToolsHelpMixin:
    def _build_tools_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # TOOLS MENU (11 items) — NEW MENU
        # ════════════════════════════════════════════════════════════════════════
        tools_menu = self.menuBar().addMenu("&Tools")

        # Validation and diagnostics
        tools_menu.addAction("&Validation...", self._on_tools_validation)
        tools_menu.addAction("&Find Errors...", self._on_find_errors)
        tools_menu.addAction("&Mesh Diagnostics...", self._on_mesh_diagnostics)
        tools_menu.addAction("&Geometry Repair...", self._on_geometry_repair)
        tools_menu.addAction("&Mesh Checker...", self._on_mesh_checker)

        tools_menu.addSeparator()

        # Utilities
        tools_menu.addAction("&Plugin Manager...", self._on_plugin_manager)
        tools_menu.addAction("&Preferences...", self._on_preferences)
        tools_menu.addAction("&Units Conversion...", self._on_units_conversion)
        tools_menu.addAction("&Calculator", self._on_calculator)

        tools_menu.addSeparator()

        # Development/preview
        tools_menu.addAction("&FDS Preview (EXPERIMENTAL)...", self._on_fds_preview)
        tools_menu.addAction("&Script Console...", self._on_script_console)


    def _build_window_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # WINDOW MENU (4 items) — NEW MENU
        # ════════════════════════════════════════════════════════════════════════
        window_menu = self.menuBar().addMenu("&Window")

        window_menu.addAction(self.focus_action)
        window_menu.addAction(self.panels_action)
        panels_menu = window_menu.addMenu("Show &Panels")             # filled when opened, so panels added later appear too
        panels_menu.aboutToShow.connect(lambda m=panels_menu: self._fill_panels_menu(m))
        toolbars_menu = window_menu.addMenu("Show &Toolbars")
        toolbars_menu.aboutToShow.connect(lambda m=toolbars_menu: self._fill_toolbars_menu(m))
        window_menu.addSeparator()
        workspaces = window_menu.addMenu("&Workspaces")
        for label, key in (("&Model", "model"), ("&Run", "run"), ("&Results", "results")):
            workspaces.addAction(label, lambda k=key: self._apply_workspace(k))
        window_menu.addAction("&Layouts...", self._on_layouts)
        window_menu.addAction("&Workspace...", self._on_workspace)
        window_menu.addSeparator()
        window_menu.addAction("&Reset Window Layout", self._on_reset_window_layout)


    def _build_help_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # HELP MENU (8 items) — Expanded from 4
        # ════════════════════════════════════════════════════════════════════════
        help_menu = self.menuBar().addMenu("&Help")

        help_menu.addAction("&FDS User Guide", lambda: self._on_open_doc(_FDS_USER_GUIDE))
        help_menu.addAction("&Smokeview Verification Guide", lambda: self._on_open_doc(_SMV_VERIFICATION_GUIDE))
        help_menu.addAction("Pyro&Sim User Manual (reference)", lambda: self._on_open_doc(_PYROSIM_USER_MANUAL))

        help_menu.addSeparator()

        # Learning resources (new)
        help_menu.addAction("&Examples...", self._on_examples)
        help_menu.addAction("&Tutorials...", self._on_tutorials)
        help_menu.addAction("&Keyboard Shortcuts...", self._on_keyboard_shortcuts)

        help_menu.addSeparator()

        # About and updates (new)
        help_menu.addAction("&Check for Updates...", self._on_check_updates)
        help_menu.addAction("&About PyFDS", self._on_about)
