"""Right-click menus in the 3D view and the plan (UI-30): the object under the cursor, the active drawing tool, or the
view itself. Built from the window's existing handlers, so each item is the same undoable action as in the menu bar."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QMenu


class ContextMenusMixin:
    def connect_context_menu(self, view: Any) -> None:
        """Route a view's ``context_requested(entity, global_pos)`` to the menu below."""
        if hasattr(view, "context_requested"):
            view.context_requested.connect(self._on_view_context)

    def _on_view_context(self, entity: Optional[tuple], global_pos: Any) -> None:
        self._build_view_context_menu(entity).exec(global_pos)

    def _build_view_context_menu(self, entity: Optional[tuple]) -> QMenu:
        """Pure construction (no ``exec``) so tests can read the actions. An object under the cursor gets the same menu
        as in the navigation tree; a half-done drawing gets Finish / Cancel; empty space gets view commands."""
        tools = self.tool_manager
        if tools.current.active():
            menu = QMenu(self)
            menu.addAction("&Finish", tools.finish)
            menu.addAction("&Cancel Drawing", tools.escape)
            return menu
        if entity is not None:
            attr, ent = entity
            selected = self.explorer.selected()
            if selected is None or selected[1] is not ent:
                self.explorer.select_entity(attr, ent)
            return self._build_entity_context_menu(attr, ent)
        menu = QMenu(self)
        if tools.current.name != "select":
            menu.addAction("&Select Tool", lambda: self.viewport_widget.activate_tool("select"))
            menu.addSeparator()
        menu.addAction("&Select All", self._on_select_all)
        menu.addAction("Show &All", self._on_show_all)
        menu.addAction("&Paste", self._on_paste)
        menu.addSeparator()
        menu.addAction("&Reset View", self._on_reset_view)
        return menu
