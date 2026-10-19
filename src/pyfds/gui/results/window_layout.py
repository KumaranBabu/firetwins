"""Room for the 3D view in PyFDS Results: focus mode (F11), hide panels (Ctrl+B), a Window menu with every toolbar and panel, the
Tools and Record bars hidden until wanted, and the icon strip over the 3D view with the controls used most (navigation, standard
views, rendering mode)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDockWidget, QMenu, QToolBar

from pyfds.gui.icons import icon
from pyfds.gui.main_window.view_overlay import ViewOverlay
from pyfds.gui.panel_hiding import PanelHidingMixin
from pyfds.api.viz import model as vm

from .parity import _MODE_ICONS

_NAV_WIDTH = 230


class ResultsLayoutMixin(PanelHidingMixin):
    def _build_layout(self) -> None:
        """Called last in the constructor, once the menus, toolbars and their icons exist."""
        self._make_layout_actions()
        bars = {b.windowTitle(): b for b in self.findChildren(QToolBar)}
        self._focus_keep = tuple(b for t, b in bars.items() if t == "Time")      # playback stays reachable in focus mode
        for title in ("Tools", "Record"):
            if title in bars:
                bars[title].hide()                                # the strip over the 3D view and the menus replace them
        self.resizeDocks(self.findChildren(QDockWidget)[:1], [_NAV_WIDTH], Qt.Horizontal)
        self._build_window_menu()
        tools = bars.get("Tools")
        wanted = {a.text(): a for a in (tools.actions() if tools else [])}
        nav = [wanted[t] for t in ("Orbit", "Pan", "Zoom", "Roam") if t in wanted]
        views = [wanted[t] for t in ("Top", "Front", "Left side") if t in wanted]
        self.view_overlay = ViewOverlay(self.view, [nav, views, [self._mode_button], [self.panels_action, self.focus_action, self._bars_button]],
                                        collapse_icon=icon("menu"))

    def _build_window_menu(self) -> None:
        mb = self.menuBar()
        menu = QMenu("&Window", self)
        menu.addAction(self.focus_action)
        menu.addAction(self.panels_action)
        menu.addSeparator()
        bars, panels = menu.addMenu("&Toolbars"), menu.addMenu("&Panels")
        bars.menuAction().setIcon(icon("toolbars"))
        panels.menuAction().setIcon(icon("panels"))
        bars.aboutToShow.connect(lambda: self._fill_toolbars_menu(bars))
        panels.aboutToShow.connect(lambda: self._fill_panels_menu(panels))
        help_menu = next((a for a in mb.actions() if a.text() == "&Help"), None)
        if help_menu is not None:
            mb.insertMenu(help_menu, menu)
        else:
            mb.addMenu(menu)

    def _mode_button(self, button) -> None:
        """Rendering mode as a drop-down on the strip."""
        button.setIcon(icon(_MODE_ICONS.get(self.viewer.viz.rendering_mode, "shaded")))
        button.setToolTip("Rendering mode")
        button.setPopupMode(button.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for mode in vm.RENDER_MODES:
            a = QAction(icon(_MODE_ICONS.get(mode, "shaded")), mode.replace("_", " ").capitalize(), menu)
            a.triggered.connect(lambda _c=False, m=mode, i=icon(_MODE_ICONS.get(mode, "shaded")):
                                self._try(lambda: (self.viewer.set_rendering_mode(m), button.setIcon(i), self.sync())))
            menu.addAction(a)
        button.setMenu(menu)

    def _bars_button(self, button) -> None:
        button.setIcon(icon("toolbars"))
        button.setToolTip("Show or hide the toolbars")
        button.setPopupMode(button.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.aboutToShow.connect(lambda: self._fill_toolbars_menu(menu))
        button.setMenu(menu)
