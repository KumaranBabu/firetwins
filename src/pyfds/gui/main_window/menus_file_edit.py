"""Menu construction: file, edit (built from the declarative tables in ``pyfds.gui.actions``)."""
from __future__ import annotations

from pyfds.gui.actions import EDIT_MENU, FILE_MENU, ActionRegistry


class MenusFileEditMixin:
    @property
    def action_registry(self) -> ActionRegistry:
        if "_action_registry" not in self.__dict__:
            self._action_registry = ActionRegistry()
        return self._action_registry

    def _build_file_menu(self) -> None:
        # Actions stashed on self.* (see ``attr`` in FILE_MENU) are reused in the toolbar, so checkable state
        # stays in sync between menu and toolbar automatically.
        self.action_registry.build_menu(self, self.menuBar(), "&File", FILE_MENU, menu_id="file")

    def _build_edit_menu(self) -> None:
        self.action_registry.build_menu(self, self.menuBar(), "&Edit", EDIT_MENU, menu_id="edit")
