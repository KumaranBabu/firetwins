"""Opening the generic collection editor (plan step F5) from the Model menu and the object context menu."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QMenu

from pyfds.gui.actions import EDITOR_MENU
from pyfds.gui.editors.collection_editor import EntityCollectionEditor
from pyfds.gui.editors.model_checks import ModelChecksDialog
from pyfds.gui.editors.scenarios import ScenariosDialog


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

    def _show_check_report(self, report: Any) -> None:
        self.validation_panel.show_report(report)
        self._show_messages(self.validation_panel)

    def _on_edit_model_checks(self) -> ModelChecksDialog:
        """Switch checks on/off and share check sets (modal); its Run button fills the Validation panel."""
        dialog = ModelChecksDialog(self.api, self, self._show_check_report)
        self._model_checks_dialog = dialog
        if dialog.exec():
            self.explorer.refresh()
        return dialog

    def _on_run_model_checks(self) -> Any:
        report = self.api.validation.validate()
        self._show_check_report(report)
        return report

    def _on_edit_scenarios(self) -> ScenariosDialog:
        """Create, clone, rename and delete scenarios and edit what each one changes (modal)."""
        def changed():
            self.explorer.refresh()
            self._refresh_status()
        dialog = ScenariosDialog(self.api, self, changed)
        self._scenarios_dialog = dialog
        dialog.exec()
        self.explorer.refresh()
        return dialog
