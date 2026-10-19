"""Hide-and-restore of panels and toolbars, shared by the model editor and the results viewer: focus mode (F11), a one-key hide
of all panels (Ctrl+B), and the Window menu lists of every toolbar and panel.

A window using it calls ``_make_layout_actions()`` once, may set ``_focus_keep`` (widgets that stay in focus mode, e.g. the time bar
of the results viewer) and gives its Window menu the lists through ``_fill_toolbars_menu`` / ``_fill_panels_menu``."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDockWidget, QMenu, QToolBar

from pyfds.gui.icons import icon


class PanelHidingMixin:
    _focus_keep: tuple = ()

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
        self._set_hidden("focus", [w for w in self.findChildren(QDockWidget) + self.findChildren(QToolBar) if w not in self._focus_keep], on)
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
