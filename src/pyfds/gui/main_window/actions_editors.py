"""Opening the generic collection editor (plan step F5) from the Model menu and the object context menu."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QMenu

from pyfds.gui.actions import EDITOR_MENU
from pyfds.gui.editors.collection_editor import EntityCollectionEditor


class ActionsEditorsMixin:
    def _install_editor_menu(self) -> None:
        """Put the 'Edit <Things>...' entries at the top of the Model menu."""
        model = next((a.menu() for a in self.menuBar().actions() if a.text().replace("&", "") == "Model"), None)
        if model is None:
            return
        self._editor_scratch = QMenu(self)
        self.action_registry._fill(self, self._editor_scratch, EDITOR_MENU)
        first = model.actions()[0] if model.actions() else None
        model.insertActions(first, self._editor_scratch.actions())

    def _on_edit_collection(self, attr: str, title: str, select: Optional[str] = None) -> EntityCollectionEditor:
        """Open the editor for one collection (modal). *select* names the object to start on."""
        if select is None:
            picked = self.explorer.selected()
            if picked is not None and picked[0] == attr:
                select = picked[1].name
        dialog = EntityCollectionEditor(self.api, attr, title, self, select)
        self._collection_editor = dialog
        dialog.exec()
        return dialog

    def _on_open_in_editor(self, attr: str, entity: Any) -> None:
        from pyfds.gui.actions.editor_menu import EDITORS
        title = next((t for _l, a, t in EDITORS if a == attr), f"Edit {attr.replace('_', ' ').title()}")
        self._on_edit_collection(attr, title, entity.name)
