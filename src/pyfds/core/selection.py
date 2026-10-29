"""
PyFDS Selection Manager
=======================
GUI-independent selection state for any FDS entity.

Design contract for future GUI
-------------------------------
The backend manages *what* is selected; the GUI only *displays* it.
A GUI widget calls ``api.selection.select(entity)`` and subscribes to
``EventType.SELECTION_CHANGED`` to rebuild its highlight list.

The SelectionManager never holds rendering state (colours, handles, glows).
It only tracks which ``FdsEntity`` objects are in the active selection set.

Features
--------
- Single / multi-select
- Type-filtered select-all
- Box-select via bounding-box predicate
- Group tag support for named subsets (e.g., "fire_zone", "sprinkler_grid")
- Thread-safe
- Full undo support: returns the previous selection snapshot for callers
  that want to push a ``SelectionCommand`` onto the CommandPipeline

Emitted events
--------------
``SELECTION_CHANGED``  — every time the selection set changes
``SELECTION_CLEARED``  — when the selection is fully emptied
"""
from __future__ import annotations

import logging

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Type


logger = logging.getLogger(__name__)


class SelectionMode(Enum):
    REPLACE  = auto()   # new selection replaces old (Ctrl not held)
    ADD      = auto()   # add to existing selection (Ctrl held)
    REMOVE   = auto()   # remove from existing selection (Alt held)
    TOGGLE   = auto()   # toggle membership


@dataclass(frozen=True)
class SelectionSnapshot:
    """Immutable snapshot of the selection set (for undo/redo)."""
    entity_uids: FrozenSet[str]

    def is_empty(self) -> bool:
        return len(self.entity_uids) == 0

    def __len__(self) -> int:
        return len(self.entity_uids)


class SelectionManager:
    """
    Manages the active selection set for a PyFDS session.

    Thread-safe. Emits ``SELECTION_CHANGED`` and ``SELECTION_CLEARED``
    through the global EventBus on every state change.

    Parameters
    ----------
    project : FdsProject, optional
        Required for ``select_all`` / ``filter_select`` operations.
        Can be updated later by assigning ``manager.project``.

    Example::

        api.selection.select(mesh_entity)
        api.selection.add(obst_entity)
        for entity in api.selection.selected:
            print(entity.name)
        api.selection.clear()
    """

    def __init__(self, project: Any = None) -> None:
        self.project = project
        self._lock = threading.Lock()
        self._selected: Dict[str, Any] = {}   # uid → FdsEntity
        self._groups: Dict[str, Set[str]] = {}  # group_name → set of uids
        #: Callables run (no arguments) after every change; used by the UI history.
        self.observers: List[Callable[[], None]] = []

    # ── Core select/deselect ─────────────────────────────────────────────────

    def select(self, entity: Any, mode: SelectionMode = SelectionMode.REPLACE) -> None:
        """Select *entity* according to *mode*."""
        with self._lock:
            uid = entity.uid
            if mode == SelectionMode.REPLACE:
                self._selected = {uid: entity}
            elif mode == SelectionMode.ADD:
                self._selected[uid] = entity
            elif mode == SelectionMode.REMOVE:
                self._selected.pop(uid, None)
            elif mode == SelectionMode.TOGGLE:
                if uid in self._selected:
                    del self._selected[uid]
                else:
                    self._selected[uid] = entity
        self._emit_changed()

    def select_many(
        self,
        entities: List[Any],
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """Select a list of entities atomically."""
        with self._lock:
            if mode == SelectionMode.REPLACE:
                self._selected = {e.uid: e for e in entities}
            elif mode == SelectionMode.ADD:
                for e in entities:
                    self._selected[e.uid] = e
            elif mode == SelectionMode.REMOVE:
                for e in entities:
                    self._selected.pop(e.uid, None)
            elif mode == SelectionMode.TOGGLE:
                for e in entities:
                    uid = e.uid
                    if uid in self._selected:
                        del self._selected[uid]
                    else:
                        self._selected[uid] = e
        self._emit_changed()

    def deselect(self, entity: Any) -> None:
        """Remove *entity* from the selection."""
        self.select(entity, SelectionMode.REMOVE)

    def toggle(self, entity: Any) -> None:
        """Toggle *entity*'s membership in the selection."""
        self.select(entity, SelectionMode.TOGGLE)

    def clear(self) -> None:
        """Empty the selection and emit SELECTION_CLEARED."""
        with self._lock:
            self._selected.clear()
        self._emit_cleared()

    # ── Bulk helpers ─────────────────────────────────────────────────────────

    def select_all(self, entity_type: Optional[Type] = None) -> None:
        """
        Select all entities in the project.

        Parameters
        ----------
        entity_type : type, optional
            If given, only entities of this type are selected.
        """
        if self.project is None:
            return
        entities = self.project.all_entities
        if entity_type is not None:
            entities = [e for e in entities if isinstance(e, entity_type)]
        self.select_many(entities, SelectionMode.REPLACE)

    def filter_select(
        self,
        predicate: Callable[[Any], bool],
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """Select all project entities for which *predicate(entity)* is True."""
        if self.project is None:
            return
        matches = [e for e in self.project.all_entities if predicate(e)]
        self.select_many(matches, mode)

    def box_select(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        z_min: float, z_max: float,
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """
        Select all entities whose bounding box intersects the given region.

        Works with any entity that has x_min/x_max/y_min/y_max/z_min/z_max
        attributes (Mesh, Obstruction, Vent, Hole, Zone, Init).
        """
        def _in_box(e: Any) -> bool:
            try:
                return (
                    e.x_min < x_max and e.x_max > x_min and
                    e.y_min < y_max and e.y_max > y_min and
                    e.z_min < z_max and e.z_max > z_min
                )
            except AttributeError:
                return False

        self.filter_select(_in_box, mode)

    # ── Groups ───────────────────────────────────────────────────────────────

    def save_group(self, group_name: str) -> None:
        """Save the current selection as a named group."""
        with self._lock:
            self._groups[group_name] = set(self._selected.keys())

    def restore_group(
        self,
        group_name: str,
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> bool:
        """
        Restore a named group as the current selection.

        Returns True if the group was found.
        """
        with self._lock:
            uids = self._groups.get(group_name)
            if uids is None:
                return False
            if self.project is None:
                return False
            entities = [
                self.project.get_by_uid(uid)
                for uid in uids
                if self.project.get_by_uid(uid) is not None
            ]
        self.select_many(entities, mode)
        return True

    def delete_group(self, group_name: str) -> bool:
        with self._lock:
            return self._groups.pop(group_name, None) is not None

    @property
    def group_names(self) -> List[str]:
        with self._lock:
            return list(self._groups.keys())

    # ── Snapshot / restore (for undo) ────────────────────────────────────────

    def snapshot(self) -> SelectionSnapshot:
        """Capture an immutable snapshot of the current selection (for undo)."""
        with self._lock:
            return SelectionSnapshot(frozenset(self._selected.keys()))

    def restore(self, snapshot: SelectionSnapshot) -> None:
        """Restore selection from a previous snapshot (used by undo commands)."""
        if self.project is None:
            return
        entities = [
            self.project.get_by_uid(uid)
            for uid in snapshot.entity_uids
            if self.project.get_by_uid(uid) is not None
        ]
        with self._lock:
            self._selected = {e.uid: e for e in entities}
        self._emit_changed()

    # ── Read access ──────────────────────────────────────────────────────────

    @property
    def selected(self) -> List[Any]:
        """List of currently selected entities (insertion order)."""
        with self._lock:
            return list(self._selected.values())

    @property
    def selected_uids(self) -> FrozenSet[str]:
        with self._lock:
            return frozenset(self._selected.keys())

    def selected_of_type(self, entity_type: Type) -> List[Any]:
        """Return selected entities filtered to *entity_type*."""
        with self._lock:
            return [e for e in self._selected.values() if isinstance(e, entity_type)]

    def is_selected(self, entity: Any) -> bool:
        with self._lock:
            return entity.uid in self._selected

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._selected)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._selected) == 0

    # ── First / only helpers ─────────────────────────────────────────────────

    @property
    def first(self) -> Optional[Any]:
        """Return the first selected entity, or None."""
        with self._lock:
            return next(iter(self._selected.values()), None)

    @property
    def only(self) -> Optional[Any]:
        """Return the selected entity if exactly one is selected, else None."""
        with self._lock:
            if len(self._selected) == 1:
                return next(iter(self._selected.values()))
            return None

    # ── Tag helpers ──────────────────────────────────────────────────────────

    def select_by_tag(
        self,
        tag: str,
        mode: "SelectionMode" = SelectionMode.REPLACE,
    ) -> List[Any]:
        """
        Select all project entities whose ``tags`` list contains *tag*.

        Returns the matched entities.
        """
        if self.project is None:
            return []
        matches = [
            e for e in self.project.all_entities
            if tag in getattr(e, "tags", [])
        ]
        self.select_many(matches, mode)
        return matches

    @staticmethod
    def tag_entity(entity: Any, tag: str) -> None:
        """Add *tag* to *entity*.tags if not already present."""
        tags = getattr(entity, "tags", None)
        if tags is None:
            entity.tags = [tag]
        elif tag not in tags:
            entity.tags = list(tags) + [tag]

    @staticmethod
    def untag_entity(entity: Any, tag: str) -> None:
        """Remove *tag* from *entity*.tags."""
        tags = getattr(entity, "tags", [])
        entity.tags = [t for t in tags if t != tag]

    # ── Internal ─────────────────────────────────────────────────────────────

    def _notify_observers(self) -> None:
        for fn in list(self.observers):
            try:
                fn()
            except Exception:
                logger.exception("selection observer failed")

    def _emit_changed(self) -> None:
        self._notify_observers()
        try:
            from pyfds.core.events import get_global_bus, EventType
            with self._lock:
                payload = {
                    "count": len(self._selected),
                    "uids": frozenset(self._selected.keys()),
                }
            get_global_bus().emit(EventType.SELECTION_CHANGED, payload,
                                  source="SelectionManager")
        except Exception:
            logger.exception("selection event listener failed")

    def _emit_cleared(self) -> None:
        self._notify_observers()
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.SELECTION_CLEARED, None,
                                  source="SelectionManager")
        except Exception:
            logger.exception("selection event listener failed")

    def __repr__(self) -> str:
        return f"<SelectionManager selected={self.count}>"
