"""Edit menu actions and the Project Explorer context menu: clipboard, delete, group, find, rename."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QInputDialog, QMenu, QMessageBox

from pyfds.automation.commands import AddEntityCommand
from pyfds.gui.entity_dialogs import SchemaFormDialog
from pyfds.gui.property_schema import apply_edits, build_edit_schema

from .shared import (
    _ENTITY_COLLECTIONS,
)
from .selection import (
    _next_group_name,
)


class ActionsEditMixin:
    def _on_cut(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        self._on_copy()
        if self._clipboard_entity is not None:
            self._on_delete_selected()

    def _on_copy(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        if attr in ("scenarios", "floors"):
            QMessageBox.information(self, "Not supported", f"{attr.title()} cannot be copied.")
            return
        self._clipboard_entity = entity.model_copy(deep=True)
        self._paste_action.setEnabled(True)

    def _on_paste(self) -> None:
        if self._clipboard_entity is None:
            return
        new_entity = self._clipboard_entity.model_copy(deep=True)
        new_entity._uid = str(uuid.uuid4())
        if hasattr(new_entity, "name"):
            new_entity.name = f"{new_entity.name}_copy"
        try:
            self.api.history.execute(AddEntityCommand(self.api.project, new_entity))
        except Exception as exc:
            QMessageBox.critical(self, "Could not paste", str(exc))
        else:
            self.explorer.refresh()

    def _on_duplicate(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        if attr in ("scenarios", "floors"):
            QMessageBox.information(self, "Not supported", f"{attr.title()} cannot be duplicated.")
            return
        self._clipboard_entity = entity.model_copy(deep=True)
        self._paste_action.setEnabled(True)
        self._on_paste()

    def _attr_for_entity(self, entity: Any) -> Optional[str]:
        """Which api.<attr> collection *entity* lives in — needed to feed
        entities resolved outside the tree (e.g. GroupManager.members())
        back into explorer.select_entities(), which matches by (attr, id)
        pairs the same way the tree itself stores them."""
        for _, attr in _ENTITY_COLLECTIONS:
            try:
                collection = getattr(self.api, attr).all()
            except Exception:
                continue
            if any(e is entity for e in collection):
                return attr
        return None

    def _on_group_selected(self) -> None:
        pairs = self.explorer.selected_entities()
        if not pairs:
            QMessageBox.information(self, "Group Objects", "Nothing selected.")
            return
        existing = {g.name for g in self.api.groups.all()}
        name, ok = QInputDialog.getText(
            self, "Group Objects", "Group name:", text=_next_group_name(existing)
        )
        if not ok or not name:
            return
        if self.api.groups.get(name) is None:
            self.api.groups.create(name)
        for _, entity in pairs:
            self.api.groups.assign(entity, name)
        # Membership is a plain dict mutation, not a Command (same as
        # FloorManager.assign()) — it fires no COMMAND_EXECUTED event, so
        # the tree needs an explicit refresh.
        self.explorer.refresh()
        self.statusBar().showMessage(f"Grouped {len(pairs)} object(s) as {name!r}.")

    def _on_ungroup_selected(self) -> None:
        pairs = self.explorer.selected_entities()
        if not pairs:
            QMessageBox.information(self, "Ungroup Objects", "Nothing selected.")
            return
        count = 0
        for attr, entity in pairs:
            if attr == "groups":
                # A Group row itself was selected — ungroup (and remove)
                # the whole group rather than treating the Group object
                # itself as something to unassign.
                for member in self.api.groups.members(entity.name):
                    self.api.groups.unassign(member)
                    count += 1
                self.api.groups.delete_group(entity.name)
            elif self.api.groups.group_of(entity) is not None:
                self.api.groups.unassign(entity)
                count += 1
        self.explorer.refresh()
        self.statusBar().showMessage(f"Ungrouped {count} object(s).")

    def _on_select_group_members(self, group_name: str) -> None:
        pairs = []
        for member in self.api.groups.members(group_name):
            attr = self._attr_for_entity(member)
            if attr is not None:
                pairs.append((attr, member))
        if not pairs:
            QMessageBox.information(self, "Empty group", f"Group {group_name!r} has no members.")
            return
        self.explorer.select_entities(pairs)

    def _on_delete_selected(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        name = getattr(entity, "name", repr(entity))
        if QMessageBox.question(self, "Delete", f"Remove {name!r}?") != QMessageBox.Yes:
            return
        try:
            getattr(self.api, attr).remove(entity)
        except Exception as exc:
            QMessageBox.critical(self, "Could not remove entity", str(exc))

    def _on_edit_properties(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        _attr, entity = selected
        schema = build_edit_schema(entity)
        dialog = SchemaFormDialog(f"Edit {entity.name}", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            apply_edits(self.api, entity, dialog.values())
        except Exception as exc:
            QMessageBox.critical(self, "Could not update properties", str(exc))

    def _on_find(self) -> None:
        text, ok = QInputDialog.getText(self, "Find", "Search for (matches entity name):")
        if not ok or not text:
            return
        match = self.explorer.find_entity_by_name(text)
        if match is None:
            QMessageBox.information(self, "Find", f"No entity found matching {text!r}.")
            return
        self.explorer.setCurrentItem(match)

    def _on_rename_entity(self, entity: Any) -> None:
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=entity.name)
        if not ok or not new_name or new_name == entity.name:
            return
        try:
            self.api.set_property(entity, "name", new_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not rename", str(exc))

    def _on_toggle_enabled(self, entity: Any) -> None:
        try:
            self.api.set_property(entity, "enabled", not entity.enabled)
        except Exception as exc:
            QMessageBox.critical(self, "Could not change enabled state", str(exc))

    def _build_entity_context_menu(self, attr: str, entity: Any) -> QMenu:
        """Pure construction, no ``.exec()`` — kept separate so tests can
        inspect the menu's actions without ever risking a real modal popup.

        Scenario/Floor/Group rows get their own branch: all three are plain
        dataclasses stored internally in dicts keyed by name (not FdsEntity
        subclasses living in plain lists), so the generic Rename/Disable
        path — which assumes a bare ``setattr`` is always safe — would
        desync the dict key from the renamed object. Delete is still safe
        (whole-entry removal, not a rename) and reuses the same
        ``_on_delete_selected`` as every other entity type via the
        ``remove(entity)`` aliases on ``ScenarioManager``/``FloorManager``/
        ``GroupManager``."""
        menu = QMenu(self)
        if attr == "scenarios":
            menu.addAction("&Apply", lambda: self._on_apply_scenario(entity.name))
            menu.addAction("&Clone...", lambda: self._on_clone_scenario(entity.name))
            menu.addAction("&Set Override...", lambda: self._on_set_scenario_override(entity))
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        if attr == "floors":
            menu.addAction("&Properties...", self._on_edit_properties)
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        if attr == "groups":
            menu.addAction("&Select Members", lambda: self._on_select_group_members(entity.name))
            menu.addSeparator()
            menu.addAction("&Delete", self._on_delete_selected)
            return menu
        menu.addAction("&Properties...", self._on_edit_properties)
        menu.addAction("Re&name...", lambda: self._on_rename_entity(entity))
        toggle_label = "&Disable Object" if entity.enabled else "&Enable Object"
        menu.addAction(toggle_label, lambda: self._on_toggle_enabled(entity))
        menu.addSeparator()
        menu.addAction("&Delete", self._on_delete_selected)
        return menu

    def _on_explorer_context_menu(self) -> None:
        selected = self.explorer.selected()
        if selected is None:
            return
        attr, entity = selected
        self._build_entity_context_menu(attr, entity).exec(QCursor.pos())
