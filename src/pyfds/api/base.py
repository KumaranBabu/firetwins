"""Shared base class for the collection managers.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class _CollectionManager:
    """
    Generic CRUD manager for a list-valued attribute on ``FdsProject``.

    Wraps ``project.add()`` / ``project.remove()`` and fires events through
    the ``CommandPipeline``.
    """

    def __init__(self, api: "FdsApi", entity_class: Type) -> None:
        self._api  = api
        self._cls  = entity_class

    @property
    def _project(self):
        return self._api.project

    @property
    def _pipe(self):
        return self._api.history._pipe

    def add(self, entity) -> None:
        from pyfds.automation.commands import AddEntityCommand
        self._pipe.execute(AddEntityCommand(self._project, entity))

    def remove(self, entity) -> None:
        from pyfds.automation.commands import RemoveEntityCommand
        self._pipe.execute(RemoveEntityCommand(self._project, entity))

    def update(self, entity_or_name, **fields) -> Any:
        """Change several fields of one entity as ONE undoable step.

        *entity_or_name* is the entity or its ``name``. Unknown field names raise
        ``AttributeError`` (entities accept arbitrary extras, so a typo would
        otherwise be silently stored). Nothing is applied if any field is invalid.
        """
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        entity = entity_or_name
        if isinstance(entity_or_name, str):
            entity = self.get(entity_or_name)
            if entity is None:
                raise KeyError(f"{entity_or_name!r} not found")
        if not fields:
            return entity
        known = set(type(entity).model_fields)
        bad = sorted(k for k in fields if k not in known)
        if bad:
            raise AttributeError(f"{type(entity).__name__} has no field(s): {', '.join(bad)}")
        result = self._pipe.execute(GroupCommand(
            [ModifyPropertyCommand(entity, k, v) for k, v in fields.items()],
            label=f"edit {type(entity).__name__} ({', '.join(fields)})",
        ))
        if not result.success:
            raise ValueError(result.message)
        return entity

    def update_many(self, entities_or_names, **fields) -> List[Any]:
        """Set the same fields on several entities as ONE undo step (multi-edit, DEV-18).

        Entities are objects or names. Unknown fields raise ``AttributeError`` and a missing entity raises
        ``KeyError``; nothing is applied unless all are valid. ``name`` cannot be set this way."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        if not fields:
            raise ValueError("give at least one field to change")
        if "name" in fields:
            raise ValueError("names are unique; use rename() for one entity at a time")
        targets = [self._resolve(e) for e in entities_or_names]
        if not targets:
            raise ValueError("no entities given")
        bad = sorted(k for k in fields if any(k not in type(t).model_fields for t in targets))
        if bad:
            raise AttributeError(f"not a field of every selected entity: {', '.join(bad)}")
        result = self._pipe.execute(GroupCommand(
            [ModifyPropertyCommand(t, k, v) for t in targets for k, v in fields.items()],
            label=f"edit {len(targets)} {self._cls.__name__} ({', '.join(fields)})"))
        if not result.success:
            raise ValueError(result.message)
        return targets

    # -- raw "additional fields" (FDS keywords PyFDS has no typed field for) -------------
    _EXTRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]*(\(\s*\d+(:\d+)?(\s*,\s*\d+(:\d+)?)*\s*\))?$")

    def _resolve(self, entity_or_name) -> Any:
        if isinstance(entity_or_name, str):
            entity = self.get(entity_or_name)
            if entity is None:
                raise KeyError(f"{entity_or_name!r} not found")
            return entity
        return entity_or_name

    def extras(self, entity_or_name) -> Dict[str, str]:
        """The entity's additional FDS keywords as ``{KEY: raw text}`` (a copy)."""
        return dict(self._resolve(entity_or_name).fds_extra or {})

    def set_extra(self, entity_or_name, key: str, value: Any) -> Any:
        """Add or change one additional FDS keyword (one undoable step).

        *value* is written verbatim, so strings need their own quotes
        (``"'ABC'"``); numbers and booleans are formatted for you.
        """
        from pyfds.automation.commands import ModifyPropertyCommand
        entity = self._resolve(entity_or_name)
        key = key.strip().upper()
        if not self._EXTRA_KEY.match(key):
            raise ValueError(f"{key!r} is not a valid FDS keyword")
        base = key.split("(")[0].lower()
        if base in type(entity).model_fields and base not in ("fds_extra", "tags", "enabled"):
            raise ValueError(f"{key} is a typed field of {type(entity).__name__}; use update({base}=...)")
        if isinstance(value, bool):
            text = ".TRUE." if value else ".FALSE."
        elif isinstance(value, (list, tuple)):
            text = ",".join(str(v) for v in value)
        else:
            text = str(value).strip()
        if not text:
            raise ValueError("value must not be empty")
        merged = dict(entity.fds_extra or {})
        merged[key] = text
        self._pipe.execute(ModifyPropertyCommand(entity, "fds_extra", merged))
        return entity

    def remove_extra(self, entity_or_name, key: str) -> Any:
        """Delete one additional FDS keyword (one undoable step)."""
        from pyfds.automation.commands import ModifyPropertyCommand
        entity = self._resolve(entity_or_name)
        key = key.strip().upper()
        merged = dict(entity.fds_extra or {})
        if key not in merged:
            raise KeyError(f"{key} is not set on {getattr(entity, 'name', entity)!r}")
        del merged[key]
        self._pipe.execute(ModifyPropertyCommand(entity, "fds_extra", merged or None))
        return entity

    def rename(self, entity_or_name, new_name: str) -> Any:
        """Rename an entity (one undoable step); the new name must be unused."""
        if self.get(new_name) is not None:
            raise ValueError(f"{new_name!r} already exists")
        return self.update(entity_or_name, name=new_name)

    def all(self) -> List[Any]:
        collection = self._project._get_collection(self._cls)
        return list(collection) if collection is not None else []

    def get(self, entity_id: str) -> Optional[Any]:
        for item in self.all():
            if getattr(item, "name", None) == entity_id:
                return item
        return None

    def clear(self) -> None:
        for item in list(self.all()):
            self.remove(item)

    def count(self) -> int:
        return len(self.all())


class _UndoableStore:
    """
    Mixin for managers that keep their own state outside ``FdsProject``
    (scenarios, floors, groups). Subclasses provide ``_capture_state`` and
    ``_restore_state``; every mutator wraps its body in :meth:`_do`, which
    runs it as ONE undoable command on the active document's history.

    Nested calls (e.g. ``remove`` -> ``delete_floor``) run directly so a
    single user action never produces two history entries.
    """
    _api: "FdsApi"
    _in_action: bool = False

    def _capture_state(self) -> Any:        # pragma: no cover - interface
        raise NotImplementedError

    def _restore_state(self, state: Any) -> None:   # pragma: no cover
        raise NotImplementedError

    def _do(self, label: str, action):
        if self._in_action:
            return action()
        from pyfds.automation.commands import StateSwapCommand

        def guarded():
            self._in_action = True
            try:
                return action()
            finally:
                self._in_action = False

        cmd = StateSwapCommand(label, self._capture_state, self._restore_state, guarded)
        result = self._api.history.execute(cmd)
        if not result.success:
            raise cmd.error if cmd.error is not None else RuntimeError(result.message)
        return cmd.value
