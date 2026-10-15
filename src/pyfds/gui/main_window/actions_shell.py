"""Shell actions (plan step F1): theme, units, selection and visibility, replace, section box, view history.
Each handler asks for input if needed and calls ``api``; none holds model logic."""
from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from pyfds.gui.theme import apply_theme


class ActionsShellMixin:
    # -- theme and units --------------------------------------------------------------------
    def _on_theme_chosen(self, name: str) -> None:
        apply_theme(name)
        self.statusBar().showMessage(f"Theme: {name}", 4000)

    def _on_units_metric(self) -> None:
        self.api.units.set_system("SI")

    def _on_units_imperial(self) -> None:
        self.api.units.set_system("EN")

    # -- selection and visibility -------------------------------------------------------------
    def _selected_objects(self) -> List[Any]:
        return [e for _a, e in self.explorer.selected_entities()]

    def _on_select_all(self) -> None:
        rows = [r.data(0, Qt.UserRole) for r in self.explorer._iter_rows()]
        self.explorer.select_entities(rows)

    def _on_hide_selected(self) -> None:
        objs = self._selected_objects()
        if not objs:
            self.statusBar().showMessage("Nothing selected to hide", 4000)
            return
        n = self.api.view.hide(objs)
        self.statusBar().showMessage(f"Hid {n} object(s)", 4000)

    def _on_show_selected(self) -> None:
        self.api.view.show(self._selected_objects())

    def _on_isolate_selected(self) -> None:
        objs = self._selected_objects()
        if not objs:
            self.statusBar().showMessage("Nothing selected to filter on", 4000)
            return
        n = self.api.view.isolate(objs)
        self.statusBar().showMessage(f"Showing only the selection ({n} others hidden)", 4000)

    def _on_show_all(self) -> None:
        self.api.view.show_all()
        self._sync_shell_bars()

    def _on_copy_fds_records(self) -> None:
        """Put the FDS records of the selected objects on the clipboard as text."""
        objs = self._selected_objects()
        try:
            text = self.api.clipboard.to_fds_text(objs, include_dependencies=False)
        except (ValueError, KeyError) as exc:
            QMessageBox.information(self, "Copy FDS Records", str(exc))
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"Copied the FDS records of {len(objs)} object(s)", 4000)

    def _on_select_referencing(self, entity: Any) -> None:
        """Select the objects that use *entity* by name (a surface's obstructions, a ramp's surfaces ...)."""
        refs = [r for r in self.api.project.find_references(entity.name) if r is not entity]
        pairs = [(self.explorer._owner[id(r)], r) for r in refs if id(r) in self.explorer._owner]
        if not pairs:
            self.statusBar().showMessage(f"Nothing refers to {entity.name}", 4000)
            return
        self.explorer.select_entities(pairs)
        self.statusBar().showMessage(f"{len(pairs)} object(s) refer to {entity.name}", 4000)

    # -- find and replace -----------------------------------------------------------------------
    def _on_replace(self) -> None:
        find, ok = QInputDialog.getText(self, "Replace", "Find in names:")
        if not ok or not find:
            return
        rep, ok = QInputDialog.getText(self, "Replace", f"Replace {find!r} with:")
        if not ok:
            return
        try:
            preview = self.api.find.replace(find, rep, dry_run=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Replace", str(exc))
            return
        n, skipped = len(preview["changed"]), preview["skipped"]
        if not n:
            note = f"\n{len(skipped)} match(es) skipped: {skipped[0][1]}" if skipped else ""
            QMessageBox.information(self, "Replace", f"Nothing to replace.{note}")
            return
        extra = f"\n{len(skipped)} other match(es) will be skipped." if skipped else ""
        if QMessageBox.question(self, "Replace", f"Rename {n} object(s)?{extra}") != QMessageBox.Yes:
            return
        try:
            self.api.find.replace(find, rep)
        except ValueError as exc:
            QMessageBox.critical(self, "Replace", str(exc))
            return
        self.statusBar().showMessage(f"Renamed {n} object(s)", 4000)

    # -- section box and view history ------------------------------------------------------------
    def _on_section_box_around_selection(self) -> None:
        objs = self._selected_objects()
        if not objs:
            self.statusBar().showMessage("Select objects to put a section box around", 4000)
            return
        try:
            self.api.views.fit_section_box(objs, margin=0.5)
        except ValueError as exc:
            QMessageBox.information(self, "Section Box", str(exc))

    def _on_reset_section_box(self) -> None:
        self.api.views.reset_section_box()

    def _on_undo_view(self) -> None:
        label = self.api.ui_history.undo()
        self.statusBar().showMessage(f"Undid view change: {label}" if label else "No view change to undo", 4000)

    def _on_redo_view(self) -> None:
        label = self.api.ui_history.redo()
        self.statusBar().showMessage(f"Redid view change: {label}" if label else "No view change to redo", 4000)
