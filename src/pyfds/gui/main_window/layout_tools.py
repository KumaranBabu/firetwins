"""Room for the 3D view: focus mode (F11), a one-key hide of all panels (Ctrl+B), a list of every toolbar and panel under
Window, compact default docks and toolbars, and the icon strip over the 3D view (``view_overlay``)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu, QToolBar

from pyfds.core.viewport import CameraPreset
from pyfds.gui.icons import icon, icon_for_text

from pyfds.gui.panel_hiding import PanelHidingMixin

from .view_overlay import ViewOverlay

_SIDE_WIDTH = 270                                  # the left and right docks start this wide
_LAYOUT_VERSION = 5                                # saved window states of older layouts are ignored (bottom dock height, full-height left column)
_OVERLAY_VIEWS = (("Front", CameraPreset.FRONT), ("Top", CameraPreset.TOP), ("Left", CameraPreset.LEFT),
                  ("Iso", CameraPreset.ISOMETRIC))


class LayoutToolsMixin(PanelHidingMixin):

    # -- compact defaults ---------------------------------------------------------------------------------------------
    def _build_layout_tools(self) -> None:
        """Called once the bars exist (and have their icons): slim toolbars, tabbed side docks, the strip over the 3D view."""
        for bar in (self.findChild(QToolBar, "QuickAccessToolBar"), self.drawing_bar):
            bar.setToolButtonStyle(Qt.ToolButtonIconOnly)         # the names are in the tooltips
        self.view_tabs.tabBar().setAutoHide(True)                 # no tab strip while "Model" is the only tab
        self.view_bar.hide()                                      # the strip over the 3D view replaces it (Window > Toolbars brings it back)
        # one column on the left (project tree above, properties below) instead of one on each side: the 3D view gets the width back.
        # Qt cannot split a dock that is already in a tab stack, so the left docks are taken out and put back in the right order.
        self.setDockOptions(self.dockOptions() | QMainWindow.AllowNestedDocks)
        # the left column runs the full height; the bottom Messages dock sits only under the 3D view (on a 768 px
        # screen the column otherwise lost ~190 px to it and the project tree showed four rows)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        docks = (self.explorer_dock, self.layers_dock, self.tool_properties_dock, self.properties_dock, self.agent_dock)
        shown = [d for d in docks if not d.isHidden()]
        for d in docks:
            self.removeDockWidget(d)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.properties_dock)
        self.splitDockWidget(self.explorer_dock, self.properties_dock, Qt.Vertical)
        self.tabifyDockWidget(self.explorer_dock, self.layers_dock)
        self.tabifyDockWidget(self.layers_dock, self.tool_properties_dock)
        self.tabifyDockWidget(self.properties_dock, self.agent_dock)
        for d in docks:
            d.setVisible(d in shown)
        self.filter_bar.hide()                                    # the Show menu on the strip over the 3D view replaces this row
        self.explorer_dock.raise_()
        self.properties_dock.raise_()
        self.resizeDocks([self.explorer_dock, self.properties_dock], [_SIDE_WIDTH, _SIDE_WIDTH], Qt.Horizontal)
        self.resizeDocks([self.explorer_dock, self.properties_dock], [600, 400], Qt.Vertical)     # the tree gets more
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

        def show_menu(button) -> None:
            button.setIcon(icon("eye"))
            button.setToolTip("What to show in the 3D view, mesh display, grid and polar snap")
            button.setPopupMode(button.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            menu.aboutToShow.connect(lambda: self._fill_show_menu(menu))
            button.setMenu(menu)

        groups = [[self._render_actions[m] for m in self._render_actions],
                  views + [self._reset_view_action],
                  [self._grid_action, self._axes_action],
                  [self.snap_action, self.ortho_action],
                  [self.snapshot_action],
                  [show_menu],
                  [self.panels_action, self.focus_action, toolbars_menu]]
        self.view_overlay = ViewOverlay(self.viewport_widget, groups, collapse_icon=icon("menu"))

    def _fill_show_menu(self, menu: QMenu) -> None:
        """The Filter toolbar as a menu: the same actions and combo boxes, so both always agree."""
        menu.clear()
        for action in self._filter_actions.values():
            menu.addAction(action)
        for title, combo in (("Mesh display", self.mesh_display_combo), ("Snap grid", self.grid_combo), ("Polar snap", self.polar_combo)):
            sub = menu.addMenu(title)
            for i in range(combo.count()):
                a = sub.addAction(combo.itemText(i))
                a.setCheckable(True)
                a.setChecked(i == combo.currentIndex())
                a.triggered.connect(lambda _c=False, c=combo, k=i: (c.setCurrentIndex(k), c.activated.emit(k)))
