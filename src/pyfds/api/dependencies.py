"""Who uses an object, and deleting it with a replacement for those uses: ``api.dependencies`` (PyroSim 2025.1:
"replace the remaining dependencies when multiple objects depend on an object being deleted")."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple


def _is_reference_field(field: str) -> bool:
    return field.endswith(("_id", "_ids", "_id1", "_id2", "_id3")) or field in ("id", "ids")


class DependencyManager:
    def __init__(self, api) -> None:
        self._api = api

    def dependents(self, entity: Any) -> List[Tuple[Any, str]]:
        """``[(object, field)]`` for every other object whose ``*_id`` / ``*_ids`` field names *entity*."""
        name = getattr(entity, "name", None)
        if not name:
            return []
        found = []
        for other in self._api.project.all_entities:
            if other is entity:
                continue
            for field in type(other).model_fields:
                if not _is_reference_field(field):
                    continue
                if self._uses(getattr(other, field, None), name):
                    found.append((other, field))
        return found

    @staticmethod
    def _uses(value: Any, name: str) -> bool:
        if isinstance(value, str):
            return value == name
        if isinstance(value, (list, tuple)):
            return any(DependencyManager._uses(v, name) for v in value)
        return False

    @staticmethod
    def _swap(value: Any, old: str, new: str) -> Any:
        if isinstance(value, str):
            return new if value == old else value
        if isinstance(value, list):
            return [DependencyManager._swap(v, old, new) for v in value]
        if isinstance(value, tuple):
            return tuple(DependencyManager._swap(v, old, new) for v in value)
        return value

    def collection_of(self, entity: Any) -> Optional[str]:
        """The ``api.<collection>`` that holds *entity*, or None."""
        for name in sorted(set(self._api.project._TYPE_MAP.values())):
            manager = getattr(self._api, name, None)
            try:
                if manager is not None and any(e is entity for e in manager.all()):
                    return name
            except Exception:
                continue
        return None

    def delete(self, entity: Any, replacement: Optional[str] = None) -> int:
        """Remove *entity* in one undo step. With *replacement* (the name of another object of the same kind), every
        use of it is pointed at the replacement first. Returns the number of uses changed."""
        coll = self.collection_of(entity)
        if coll is None:
            raise KeyError(f"{getattr(entity, 'name', entity)!r} is not in the project")
        old = entity.name
        if replacement is not None:
            if replacement == old:
                raise ValueError("the replacement is the object being deleted")
            if not any(getattr(e, "name", None) == replacement for e in getattr(self._api, coll).all()):
                raise ValueError(f"{replacement!r} is not a {coll[:-1] if coll.endswith('s') else coll} of this project")
        uses = self.dependents(entity) if replacement is not None else []
        with self._api.history.transaction(f"delete {old}"):
            for other, field in uses:
                self._api.set_property(other, field, self._swap(getattr(other, field), old, replacement))
            getattr(self._api, coll).remove(entity)
        return len(uses)
