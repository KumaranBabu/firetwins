"""Floors and groups (model organisation).

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pyfds.domain.editor_state import Floor, Group

from .base import _UndoableStore


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class FloorManager(_UndoableStore):
    """
    Organise project entities by building floor / storey.

    Floors are defined as elevation bands ``[z_min, z_max)``.  Entities can
    be assigned explicitly or auto-detected from their bounding-box z-centre.

    Accessible via ``api.floors``.

    Example::

        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.define_floor("Level 1", 3.0, 6.0)
        api.floors.auto_assign_all()
        for e in api.floors.entities_on_floor("Ground"):
            print(e.name)
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    # per-project state (each open document has its own)
    @property
    def _floors(self) -> Dict[str, Floor]:
        return self._api.project.editor.floors

    @property
    def _assignments(self) -> Dict[str, str]:
        return self._api.project.editor.floor_assignments

    def _capture_state(self):
        return (dict(self._floors), dict(self._assignments))

    def _restore_state(self, state) -> None:
        floors, assignments = state
        self._floors.clear(); self._floors.update(floors)
        self._assignments.clear(); self._assignments.update(assignments)

    def define_floor(
        self, name: str, z_min: float, z_max: float, description: str = ""
    ) -> Floor:
        """Define (or update) a floor band; returns the :class:`Floor`."""
        def act() -> Floor:
            f = Floor(name=name, z_min=float(z_min), z_max=float(z_max),
                      description=description)
            self._floors[name] = f
            return f
        return self._do(f"define floor {name!r}", act)

    def all_floors(self) -> List[Floor]:
        """Return floors sorted by z_min."""
        return sorted(self._floors.values(), key=lambda f: f.z_min)

    def all(self) -> List[Floor]:
        """Alias for ``all_floors()`` — lets Floors slot into the same
        generic ``getattr(api, attr).all()`` tree-building loop as every
        other manager, without sorting-by-z_min semantics leaking into that
        shared code."""
        return self.all_floors()

    def get_floor(self, name: str) -> Optional[Floor]:
        return self._floors.get(name)

    def delete_floor(self, name: str) -> None:
        def act() -> None:
            self._floors.pop(name, None)
            for uid, fn in list(self._assignments.items()):
                if fn == name:
                    del self._assignments[uid]
        self._do(f"delete floor {name!r}", act)

    def remove(self, entity: Any) -> None:
        """Alias for ``delete_floor(entity.name)`` — lets Floor rows go
        through the same generic "Delete Selected" path as every other
        entity type."""
        self.delete_floor(entity.name)

    def assign(self, entity: Any, floor_name: str) -> None:
        """Manually assign *entity* to *floor_name*."""
        def act() -> None:
            if floor_name not in self._floors:
                raise KeyError(f"Floor {floor_name!r} is not defined.")
            uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
            self._assignments[uid] = floor_name
        self._do(f"assign to floor {floor_name!r}", act)

    def floor_of(self, entity: Any) -> Optional[Floor]:
        """
        Return the floor that contains *entity*.

        Checks manual assignments first, then falls back to bbox z-centre.
        """
        uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
        if uid in self._assignments:
            return self._floors.get(self._assignments[uid])
        # Auto-detect from bbox
        bb = entity.bbox() if hasattr(entity, "bbox") else None
        if bb is None:
            return None
        z_centre = (bb[4] + bb[5]) * 0.5
        for floor in self.all_floors():
            if floor.z_min <= z_centre < floor.z_max:
                return floor
        return None

    def entities_on_floor(self, floor_name: str) -> List[Any]:
        """Return all project entities whose z-centre falls on *floor_name*."""
        floor = self._floors.get(floor_name)
        if floor is None:
            return []
        result = []
        for entity in self._api.project.all_entities:
            f = self.floor_of(entity)
            if f is not None and f.name == floor_name:
                result.append(entity)
        return result

    def auto_assign_all(self) -> int:
        """
        Auto-assign every geometric entity to a floor by bbox z-centre.

        Returns the number of entities assigned.
        """
        def act() -> int:
            count = 0
            for entity in self._api.project.all_entities:
                f = self.floor_of(entity)
                if f is not None:
                    uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
                    self._assignments[uid] = f.name
                    count += 1
            return count
        return self._do("auto-assign entities to floors", act)

    def export_floors(self, filepath: str) -> None:
        """
        Serialize floor definitions and entity assignments to *filepath* as
        JSON.

        Assignments are keyed by entity *name*, not the in-memory ``uid``
        (a fresh UUID every time a project is constructed/parsed) — a
        reloaded project's freshly-created entities can still be re-matched
        by name in :meth:`import_floors`, while uids never would be.
        """
        import json
        from pathlib import Path

        name_by_uid = {
            (e.uid if hasattr(e, "uid") else str(id(e))): getattr(e, "name", None)
            for e in self._api.project.all_entities
        }
        data = {
            "floors": [
                {"name": f.name, "z_min": f.z_min, "z_max": f.z_max, "description": f.description}
                for f in self.all_floors()
            ],
            "assignments": {
                name_by_uid[uid]: floor_name
                for uid, floor_name in self._assignments.items()
                if name_by_uid.get(uid) is not None
            },
        }
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def import_floors(self, filepath: str) -> int:
        """
        Load floor definitions and name-keyed assignments from *filepath*
        (as written by :meth:`export_floors`) into the active project.

        Existing floors/assignments are replaced, not merged. Returns the
        number of assignments successfully re-matched by entity name against
        the currently loaded project — entities renamed or removed since
        export are silently skipped, not errored.
        """
        import json

        def act() -> int:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            self._floors.clear()
            self._assignments.clear()
            for f in data.get("floors", []):
                self.define_floor(f["name"], f["z_min"], f["z_max"], f.get("description", ""))

            entity_by_name = {
                getattr(e, "name", None): e for e in self._api.project.all_entities
            }
            count = 0
            for entity_name, floor_name in data.get("assignments", {}).items():
                entity = entity_by_name.get(entity_name)
                if entity is not None and floor_name in self._floors:
                    self.assign(entity, floor_name)
                    count += 1
            return count
        return self._do("import floors", act)

    def __repr__(self) -> str:
        return f"<FloorManager floors={list(self._floors.keys())}>"


class GroupManager(_UndoableStore):
    """
    Organise project entities into named, editor-only groups.

    Modeled directly on ``FloorManager`` (same file, same shape): a group
    is a name plus a set of member entities, tracked by the members'
    stable ``uid`` (not their ``name``) so membership survives renames.
    A entity belongs to at most one group at a time — assigning it to a
    new group implicitly removes it from any previous one, same
    one-floor-per-entity semantics ``FloorManager`` already uses.

    Accessible via ``api.groups``.

    Example::

        api.groups.create("Kitchen Block")
        api.groups.assign(obst1, "Kitchen Block")
        api.groups.assign(obst2, "Kitchen Block")
        api.groups.members("Kitchen Block")  # -> [obst1, obst2]
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    # per-project state (each open document has its own)
    @property
    def _groups(self) -> Dict[str, Group]:
        return self._api.project.editor.groups

    @property
    def _memberships(self) -> Dict[str, str]:
        return self._api.project.editor.group_memberships

    def _capture_state(self):
        return (dict(self._groups), dict(self._memberships))

    def _restore_state(self, state) -> None:
        groups, memberships = state
        self._groups.clear(); self._groups.update(groups)
        self._memberships.clear(); self._memberships.update(memberships)

    def create(self, name: str, description: str = "") -> Group:
        """Create (or update the description of) a named group."""
        def act() -> Group:
            g = Group(name=name, description=description)
            self._groups[name] = g
            return g
        return self._do(f"create group {name!r}", act)

    def all(self) -> List[Group]:
        """All defined groups — lets Groups slot into the same generic
        ``getattr(api, attr).all()`` tree-building loop as every other
        manager."""
        return list(self._groups.values())

    def get(self, name: str) -> Optional[Group]:
        return self._groups.get(name)

    def remove(self, entity: Any) -> None:
        """Alias for ``delete_group(entity.name)`` — lets Group rows go
        through the same generic "Delete Selected" path as every other
        entity type."""
        self.delete_group(entity.name)

    def delete_group(self, name: str) -> None:
        def act() -> None:
            self._groups.pop(name, None)
            for uid, gn in list(self._memberships.items()):
                if gn == name:
                    del self._memberships[uid]
        self._do(f"delete group {name!r}", act)

    def assign(self, entity: Any, group_name: str) -> None:
        """Assign *entity* to *group_name*, replacing any prior group
        membership it had."""
        def act() -> None:
            if group_name not in self._groups:
                raise KeyError(f"Group {group_name!r} is not defined.")
            uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
            self._memberships[uid] = group_name
        self._do(f"assign to group {group_name!r}", act)

    def unassign(self, entity: Any) -> None:
        """Remove *entity* from whatever group it's in, if any."""
        uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
        self._do("remove from group", lambda: self._memberships.pop(uid, None) and None)

    def group_of(self, entity: Any) -> Optional[str]:
        """The name of the group *entity* belongs to, or None."""
        uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
        return self._memberships.get(uid)

    def members(self, group_name: str) -> List[Any]:
        """Every project entity currently assigned to *group_name*."""
        uids = {uid for uid, gn in self._memberships.items() if gn == group_name}
        if not uids:
            return []
        return [
            e for e in self._api.project.all_entities
            if (e.uid if hasattr(e, "uid") else str(id(e))) in uids
        ]

    def __repr__(self) -> str:
        return f"<GroupManager groups={list(self._groups.keys())}>"
