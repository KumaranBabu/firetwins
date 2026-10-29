"""ProjectExplorer: the navigation tree, laid out like PyroSim's (Views, Tags, Meshes, ... Model, Model Checks)."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QItemSelectionModel, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from pyfds.api import FdsApi
from pyfds.gui.icons import icon_for_entity, icon_for_text

from .shared import (
    _ENTITY_COLLECTIONS,
    _NAV_TREE,
    _REFRESH_EVENTS,
)


class ProjectExplorer(QTreeWidget):
    """Tree over the active project. Never mutates directly: right-click emits a signal for MainWindow to
    act on, like every other GUI-driven mutation going through FdsApi.

    Object rows carry ``(manager_attr, entity)`` in ``Qt.UserRole``; folders, collection headings and the
    read-only Views / Tags / Model Checks rows carry nothing. Groups are real folders: a group row holds its
    members. ``category_item(attr)`` finds a collection's heading wherever it sits in the tree.
    """

    entity_context_menu_requested = Signal()

    def __init__(self, api: FdsApi, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Project"])
        self._api = api
        self._categories: Dict[str, QTreeWidgetItem] = {}
        self._filter = ""
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
            return  # empty space, a folder or a heading: nothing to act on
        self.setCurrentItem(item)
        self.entity_context_menu_requested.emit()

    def refresh(self) -> None:
        """Rebuild the tree; the selection, the folders the user collapsed, the scroll position and the filter
        survive (entities still present stay selected)."""
        keep = self.selected_entities()
        collapsed = self._collapsed_paths()
        scroll = self.verticalScrollBar().value()
        self.blockSignals(True)
        try:
            self._rebuild()
            self._collapse(collapsed)
            self.select_entities(keep)
            self.apply_filter(self._filter)
        finally:
            self.blockSignals(False)
        self.verticalScrollBar().setValue(scroll)
        self.itemSelectionChanged.emit()

    # -- expansion and filter -------------------------------------------------------------
    @staticmethod
    def _key(item: QTreeWidgetItem) -> str:
        """A row's text without its count (``Meshes (3)`` -> ``Meshes``), so it is the same after objects change."""
        return re.sub(r" \(\d+\)$", "", item.text(0))

    def _path(self, item: QTreeWidgetItem) -> Tuple[str, ...]:
        parts = []
        while item is not None:
            parts.append(self._key(item))
            item = item.parent()
        return tuple(reversed(parts))

    def _all_items(self) -> Iterator[QTreeWidgetItem]:
        stack = [self.topLevelItem(i) for i in reversed(range(self.topLevelItemCount()))]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(i) for i in reversed(range(item.childCount())))

    def _collapsed_paths(self) -> Set[Tuple[str, ...]]:
        return {self._path(i) for i in self._all_items() if i.childCount() and not i.isExpanded()}

    def _collapse(self, paths: Set[Tuple[str, ...]]) -> None:
        if paths:
            for item in self._all_items():
                if item.childCount() and self._path(item) in paths:
                    item.setExpanded(False)

    def apply_filter(self, query: str) -> int:
        """Show only the object rows matching *query* (same rules as :meth:`find_matches`) and the folders that lead
        to them; an empty query shows everything. Returns the number of matching rows."""
        self._filter = query or ""
        items = list(self._all_items())
        if not self._filter.strip():
            for item in items:
                item.setHidden(False)
            return 0
        matches = {id(r) for r in self.find_matches(self._filter)}
        for item in items:
            item.setHidden(True)
        for item in items:
            if id(item) in matches:
                node = item
                while node is not None:
                    node.setHidden(False)
                    node = node.parent()
                if item.parent() is not None:
                    item.parent().setExpanded(True)
        return len(matches)

    # -- building -------------------------------------------------------------------------
    def _rebuild(self) -> None:
        self.clear()
        self._categories = {}
        self._owner = {id(e): attr for _l, attr in _ENTITY_COLLECTIONS for e in getattr(self._api, attr).all()}
        for label, kind, payload in _NAV_TREE:
            if kind == "collection":
                self.addTopLevelItem(self._collection_item(label, payload))
            elif kind == "folder":
                folder = QTreeWidgetItem([label])
                folder.setIcon(0, icon_for_entity(payload[0][1]))
                total = 0
                for sub_label, attr in payload:
                    child = self._collection_item(sub_label, attr)
                    folder.addChild(child)
                    total += self._count(attr)
                folder.setText(0, f"{label} ({total})")
                self.addTopLevelItem(folder)
            else:
                self.addTopLevelItem(self._info_item(label, kind))
        self.expandAll()

    def _count(self, attr: str) -> int:
        return len(getattr(self._api, attr).all())

    def _collection_item(self, label: str, attr: str) -> QTreeWidgetItem:
        entities = getattr(self._api, attr).all()
        top = QTreeWidgetItem([f"{label} ({len(entities)})"])
        top.setIcon(0, icon_for_entity(attr))
        for entity in entities:
            top.addChild(self._entity_row(attr, entity))
        self._categories[attr] = top
        return top

    def _entity_row(self, attr: str, entity: Any) -> QTreeWidgetItem:
        text = getattr(entity, "name", repr(entity))
        row = QTreeWidgetItem([text])
        row.setData(0, Qt.UserRole, (attr, entity))
        row.setIcon(0, icon_for_entity(attr, entity, disabled=not getattr(entity, "enabled", True)))
        if not getattr(entity, "enabled", True):
            row.setText(0, f"{text} (disabled)")
            row.setForeground(0, QColor("gray"))
        if attr == "groups":                       # a real folder: its members live inside it
            for member in self._api.groups.members(entity.name):
                m_attr = self._owner.get(id(member))
                if m_attr is not None:
                    row.addChild(self._entity_row(m_attr, member))
        return row

    def _info_item(self, label: str, kind: str) -> QTreeWidgetItem:
        rows: List[str] = []
        if kind == "views":
            active = self._api.views.active
            rows = [f"{v.name}{' (active)' if v.name == active else ''}" for v in self._api.views.all()]
        elif kind == "tags":
            counts: Dict[str, int] = {}
            for e in self._api.project.all_entities:
                for t in getattr(e, "tags", None) or []:
                    counts[t] = counts.get(t, 0) + 1
            rows = [f"{t} ({n})" for t, n in sorted(counts.items())]
        elif kind == "checks":
            rows = [f"{c['name']}{'' if c['enabled'] else ' (off)'}" for c in self._api.validation.checks()]
        top = QTreeWidgetItem([f"{label} ({len(rows)})" if kind != "views" else label])
        top.setIcon(0, icon_for_text(label))
        for text in rows:
            child = QTreeWidgetItem([text])
            child.setIcon(0, icon_for_text(label))
            top.addChild(child)
        return top

    # -- lookup ---------------------------------------------------------------------------
    def category_item(self, attr: str) -> Optional[QTreeWidgetItem]:
        """The heading row of the collection managed by ``api.<attr>`` (e.g. ``"obstructions"``)."""
        return self._categories.get(attr)

    def category_labels(self) -> List[str]:
        """Heading text of every collection (``"Meshes (2)"``), wherever it sits in the tree."""
        return [item.text(0) for item in self._categories.values()]

    def _iter_rows(self) -> Iterator[QTreeWidgetItem]:
        """Every object row, at any depth."""
        stack = [self.topLevelItem(i) for i in reversed(range(self.topLevelItemCount()))]
        while stack:
            item = stack.pop()
            if item.data(0, Qt.UserRole) is not None:
                yield item
            stack.extend(item.child(i) for i in reversed(range(item.childCount())))

    def selected(self) -> Optional[Tuple[str, Any]]:
        """(manager_attr, entity) for the first selected object row, or None (nothing, a folder or a heading)."""
        for item in self.selectedItems():
            data = item.data(0, Qt.UserRole)
            if data is not None:
                return data
        return None

    def selected_entities(self) -> List[Tuple[str, Any]]:
        """(manager_attr, entity) for every selected object row, each object once (an object shown both in its
        collection and inside a group counts once)."""
        result, seen = [], set()
        for item in self.selectedItems():
            data = item.data(0, Qt.UserRole)
            if data is not None and id(data[1]) not in seen:
                seen.add(id(data[1]))
                result.append(data)
        return result

    def select_entity(self, attr: str, entity: Any) -> None:
        """Select the row for (attr, entity), e.g. after a 3D pick. Identity comparison, not ==."""
        self.select_entities([(attr, entity)])

    def select_entities(self, pairs: List[Tuple[str, Any]]) -> None:
        """Select every row matching one of *pairs*, replacing the selection, but only if at least one row
        matches (a pick that resolves to nothing leaves the current selection alone)."""
        wanted = {(attr, id(entity)) for attr, entity in pairs}
        matched = [row for row in self._iter_rows()
                   if (row.data(0, Qt.UserRole)[0], id(row.data(0, Qt.UserRole)[1])) in wanted]
        if not matched:
            return
        self.clearSelection()
        for item in matched:
            item.setSelected(True)
        # setCurrentItem(item) alone resets the selection to just that item; NoUpdate keeps "current" in sync
        # for keyboard navigation without touching which rows are selected.
        self.setCurrentItem(matched[0], 0, QItemSelectionModel.NoUpdate)

    def find_entity_by_name(self, substring: str) -> Optional[QTreeWidgetItem]:
        """First object row whose name contains *substring* (case-insensitive), or None."""
        needle = substring.strip().lower()
        if not needle:
            return None
        for row in self._iter_rows():
            if needle in getattr(row.data(0, Qt.UserRole)[1], "name", "").lower():
                return row
        return None

    def find_matches(self, query: str) -> List[QTreeWidgetItem]:
        """Every object row matching *query* (case-insensitive), at any depth. Plain text matches the name (the FDS ID),
        a tag, or the kind of object (``obstructions``, ``Vent``...). ``name:``, ``tag:`` or ``type:`` in front limits the
        search to that one field."""
        text = query.strip().lower()
        field = None
        for prefix in ("name", "tag", "type"):
            if text.startswith(prefix + ":"):
                field, text = prefix, text[len(prefix) + 1:].strip()
                break
        if not text:
            return []
        rows = []
        for row in self._iter_rows():
            attr, entity = row.data(0, Qt.UserRole)
            hay = {"name": [str(getattr(entity, "name", ""))],
                   "tag": [str(t) for t in (getattr(entity, "tags", None) or [])],
                   "type": [str(attr), type(entity).__name__]}
            fields = [field] if field else ["name", "tag", "type"]
            if any(text in value.lower() for f in fields for value in hay[f]):
                rows.append(row)
        return rows

    def shutdown(self) -> None:
        for sub_id in self._sub_ids:
            self._api.unsubscribe(sub_id)
