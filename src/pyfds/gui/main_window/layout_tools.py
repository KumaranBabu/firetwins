"""Room for the 3D view: focus mode (F11), a one-key hide of all panels (Ctrl+B), a list of every toolbar and panel under
Window, compact default docks and toolbars, and the icon strip over the 3D view (``view_overlay``)."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDockWidget, QMenu, QToolBar

from pyfds.core.viewport import CameraPreset
from pyfds.gui.icons import icon, icon_for_text

from .view_overlay import ViewOverlay

_SIDE_WIDTH = 270                                  # the left and right docks start this wide
_LAYOUT_VERSION = 2                                # saved window states of older layouts are ignored (they would undo the compact docks)
_OVERLAY_VIEWS = (("Front", CameraPreset.FRONT), ("Top", CameraPreset.TOP), ("Left", CameraPreset.LEFT),
                  ("Iso", CameraPreset.ISOMETRIC))


class LayoutToolsMixin:
    # -- actions and menus (made before the Window menu is built) -----------------------------------------------------
    def _make_layout_actions(self) -> None:
        self._hidden: Dict[str, tuple] = {}
        self.focus_action = self._layout_action("Focus 3D View", "F11", "Hide every panel and toolbar so the 3D view fills the "
                                                "window (F11 again brings them back)", self.toggle_focus_mode)
        self.panels_action = self._layout_action("Hide Panels", "Ctrl+B", "Hide or show all panels, keeping the toolbars",
                                                 self.toggle_panels)
        self.focus_action.setIcon(icon("focus"))
        self.panels_action.setIcon(icon("panels"))

    def _layout_action(self, text: str, key: str, tip: str, slot) -> QAction:
        a = QAction(text, self)
        a.setCheckable(True)
        a.setShortcut(QKeySequence(key))
        a.setShortcutContext(Qt.WindowShortcut)
        a.setToolTip(f"{text} ({key}): {tip}")
        a.setStatusTip(tip)
        a.toggled.connect(slot)
        self.addAction(a)
        return a

    def _fill_toolbars_menu(self, menu: QMenu) -> None:
        menu.clear()
        for bar in self.findChildren(QToolBar):
            if bar.windowTitle():
                menu.addAction(bar.toggleViewAction())

    def _fill_panels_menu(self, menu: QMenu) -> None:
        menu.clear()
        for dock in self.findChildren(QDockWidget):
            menu.addAction(dock.toggleViewAction())

    # -- hide and show ------------------------------------------------------------------------------------------------
    @property
    def focus_mode(self) -> bool:
        return "focus" in self._hidden

    @property
    def panels_hidden(self) -> bool:
        return "panels" in self._hidden

    def _set_hidden(self, key: str, widgets: List, hide: bool) -> None:
        if hide and key not in self._hidden:
            shown = [w for w in widgets if not w.isHidden()]
            front = [w for w in shown if isinstance(w, QDockWidget) and w.isVisible()]      # the tab in front of each stack
            self._hidden[key] = (shown, front)
            for w in shown:
                w.hide()
        elif not hide and key in self._hidden:
            shown, front = self._hidden.pop(key)
            for w in shown:
                w.show()
            for dock in front:
                dock.raise_()                                   # showing in any order would leave other tabs in front

    def toggle_focus_mode(self, on: bool = None) -> bool:
        """Show only the 3D view (and the menu and status bars), or bring everything back. Returns the new state."""
        on = (not self.focus_mode) if on is None else bool(on)
        self._set_hidden("focus", self.findChildren(QDockWidget) + self.findChildren(QToolBar), on)
        self._sync_layout_actions()
        return self.focus_mode

    def toggle_panels(self, on: bool = None) -> bool:
        """Hide every dock panel (toolbars stay) or show them again. Leaves focus mode first when it is on."""
        if self.focus_mode:
            self.toggle_focus_mode(False)
            return self.panels_hidden
        on = (not self.panels_hidden) if on is None else bool(on)
        self._set_hidden("panels", self.findChildren(QDockWidget), on)
        self._sync_layout_actions()
        return self.panels_hidden

    def _sync_layout_actions(self) -> None:
        for action, state in ((self.focus_action, self.focus_mode), (self.panels_action, self.panels_hidden)):
            action.blockSignals(True)
            action.setChecked(state)
            action.blockSignals(False)

    def _layout_was_reset(self) -> None:
        self._hidden.clear()
        self._sync_layout_actions()

    # -- compact defaults ---------------------------------------------------------------------------------------------
    def _build_layout_tools(self) -> None:
        """Called once the bars exist (and have their icons): slim toolbars, tabbed side docks, the strip over the 3D view."""
        for bar in (self.findChild(QToolBar, "QuickAccessToolBar"), self.drawing_bar):
            bar.setToolButtonStyle(Qt.ToolButtonIconOnly)         # the names are in the tooltips
        self.view_tabs.tabBar().setAutoHide(True)                 # no tab strip while "Model" is the only tab
        self.view_bar.hide()                                      # the strip over the 3D view replaces it (Window > Toolbars brings it back)
        self.tabifyDockWidget(self.layers_dock, self.tool_properties_dock)
        self.tabifyDockWidget(self.properties_dock, self.agent_dock)
        self.explorer_dock.raise_()
        self.properties_dock.raise_()
        self.resizeDocks([self.explorer_dock, self.properties_dock], [_SIDE_WIDTH, _SIDE_WIDTH], Qt.Horizontal)
        self.tool_manager.subscribe(self._raise_for_tool)
        self._build_view_overlay()

    def _raise_for_tool(self) -> None:
        """Drawing shows the Tool Properties tab; going back to Select shows the project tree again."""
        if self.tool_manager.current.name == "select":
            if not self.tool_properties_dock.isHidden() and not self.explorer_dock.isHidden():
                self.explorer_dock.raise_()
        elif not self.tool_properties_dock.isHidden():
            self.tool_properties_dock.raise_()

    def _build_view_overlay(self) -> None:
        views = []
        for label, preset in _OVERLAY_VIEWS:
            a = QAction(label, self)
            a.setIcon(icon_for_text(label))
            a.setToolTip(f"{label} view")
            a.triggered.connect(lambda _c=False, p=preset: self._on_camera_preset(p))
            views.append(a)

        def toolbars_menu(button) -> None:
            button.setIcon(icon("toolbars"))
            button.setToolTip("Show or hide the toolbars")
            button.setPopupMode(button.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            menu.aboutToShow.connect(lambda: self._fill_toolbars_menu(menu))
            button.setMenu(menu)

        groups = [[self._render_actions[m] for m in self._render_actions],
                  views + [self._reset_view_action],
                  [self._grid_action, self._axes_action],
                  [self.snap_action, self.ortho_action],
                  [self.snapshot_action],
                  [self.panels_action, self.focus_action, toolbars_menu]]
        self.view_overlay = ViewOverlay(self.viewport_widget, groups, collapse_icon=icon("menu"))
