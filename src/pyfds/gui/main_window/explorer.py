"""ProjectExplorer: the tree over the active project's entity collections."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from PySide6.QtCore import Qt, QItemSelectionModel, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from pyfds.api import FdsApi
from pyfds.gui.icons import icon_for_entity

from .shared import (
    _ENTITY_COLLECTIONS,
    _REFRESH_EVENTS,
)


class ProjectExplorer(QTreeWidget):
    """Tree over the active project's entity collections. Never mutates
    directly — right-click emits a signal for MainWindow to act on, same
    as every other GUI-driven mutation in this app going through FdsApi."""

    entity_context_menu_requested = Signal()

    def __init__(self, api: FdsApi, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Project"])
        self._api = api
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._sub_ids = [api.subscribe(t, self._on_event) for t in _REFRESH_EVENTS]
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)
        self.refresh()

    def _on_event(self, event) -> None:
        self.refresh()

    def _on_context_menu_requested(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None or item.data(0, Qt.UserRole) is None:
            return  # empty space or a category row — nothing to act on
        self.setCurrentItem(item)
        self.entity_context_menu_requested.emit()

    def refresh(self) -> None:
        """Rebuild the tree; the selection survives (entities still present stay selected)."""
        keep = self.selected_entities()
        self.blockSignals(True)
        try:
            self._rebuild()
            self.select_entities(keep)
        finally:
            self.blockSignals(False)
        self.itemSelectionChanged.emit()

    def _rebuild(self) -> None:
        self.clear()
        for label, attr in _ENTITY_COLLECTIONS:
            entities = getattr(self._api, attr).all()
            top = QTreeWidgetItem([f"{label} ({len(entities)})"])
            top.setIcon(0, icon_for_entity(attr))
            for entity in entities:
                text = getattr(entity, "name", repr(entity))
                child = QTreeWidgetItem([text])
                child.setData(0, Qt.UserRole, (attr, entity))
                child.setIcon(0, icon_for_entity(attr, entity, disabled=not getattr(entity, "enabled", True)))
                if not getattr(entity, "enabled", True):
                    child.setText(0, f"{text} (disabled)")
                    child.setForeground(0, QColor("gray"))
                top.addChild(child)
            self.addTopLevelItem(top)
        self.expandAll()

    def selected(self) -> Optional[Tuple[str, Any]]:
        """(manager_attr, entity) for the first selected entity row, or None
        (nothing / a category row selected). Single-entity operations
        (Copy/Cut/Duplicate/Delete/Edit Properties/rename/context-menu) all
        use this and are unaffected by multi-select being enabled — they
        just act on whichever row is "current" among the selection, same as
        before ExtendedSelection existed."""
        items = self.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def selected_entities(self) -> List[Tuple[str, Any]]:
        """(manager_attr, entity) for every selected entity row — category
        rows carry no UserRole data and are skipped. Used by multi-entity
        operations (Move/Rotate/Scale/Mirror/Group Selected)."""
        result = []
        for item in self.selectedItems():
            data = item.data(0, Qt.UserRole)
            if data is not None:
                result.append(data)
        return result

    def select_entity(self, attr: str, entity: Any) -> None:
        """Select the tree row for (attr, entity) — e.g. driven by a 3D
        viewport pick. Identity comparison (not ==): it's the exact same
        object reference the row was built from."""
        self.select_entities([(attr, entity)])

    def select_entities(self, pairs: List[Tuple[str, Any]]) -> None:
        """Select every tree row matching one of *pairs* — e.g. driven by a
        3D viewport multi-pick, or "Select Members" on a Group row. Replaces
        any prior selection, same as a fresh click — but only once at least
        one row actually matches; a pick that resolves to nothing (e.g. a
        stray entity no longer in the tree) leaves the existing selection
        untouched instead of blanking it, matching the pre-multi-select
        behavior of ``select_entity``."""
        wanted = [(attr, id(entity)) for attr, entity in pairs]
        matched: List[QTreeWidgetItem] = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                data = child.data(0, Qt.UserRole)
                if data is not None and (data[0], id(data[1])) in wanted:
                    matched.append(child)
        if not matched:
            return
        self.clearSelection()
        for item in matched:
            item.setSelected(True)
        # setCurrentItem(item) alone (no selection-model flags) resets the
        # selection to just *that* item — confirmed empirically it silently
        # undid the multi-select loop above. NoUpdate keeps "current" (for
        # keyboard nav) in sync without touching which rows are selected.
        self.setCurrentItem(matched[0], 0, QItemSelectionModel.NoUpdate)

    def find_entity_by_name(self, substring: str) -> Optional[QTreeWidgetItem]:
        """First entity row whose name contains *substring* (case-insensitive),
        or None. Category rows are never matched."""
        needle = substring.strip().lower()
        if not needle:
            return None
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                data = child.data(0, Qt.UserRole)
                if data is None:
                    continue
                _attr, entity = data
                if needle in getattr(entity, "name", "").lower():
                    return child
        return None

    def shutdown(self) -> None:
        for sub_id in self._sub_ids:
            self._api.unsubscribe(sub_id)
