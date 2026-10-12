"""Entity add/remove/modify/rename/duplicate and simple model commands."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Command, CommandResult


class AddEntityCommand(Command):
    """
    Add an ``FdsEntity`` to the appropriate collection on *project*.

    Parameters
    ----------
    project : FdsProject
    entity : FdsEntity
        The entity to add (Mesh, Obstruction, Surface, etc.).
    """
    def __init__(self, project, entity) -> None:
        self._project = project
        self._entity  = entity
        self.description = f"add {type(entity).__name__} '{getattr(entity, 'name', '?')}'"

    def execute(self) -> CommandResult:
        try:
            self._project.add_entity(self._entity)
            return CommandResult.ok(f"Added {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._project.remove_entity_by_uid(self._entity.uid)
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class RemoveEntityCommand(Command):
    """
    Remove an ``FdsEntity`` from its collection on *project*.

    The entity is stored so the removal can be undone (re-added).
    """
    def __init__(self, project, entity) -> None:
        self._project = project
        self._entity  = entity
        self.description = f"remove {type(entity).__name__} '{getattr(entity, 'name', '?')}'"

    def execute(self) -> CommandResult:
        try:
            self._project.remove_entity_by_uid(self._entity.uid)
            return CommandResult.ok(f"Removed: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._project.add_entity(self._entity)
            return CommandResult.ok(f"Restored: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class ModifyPropertyCommand(Command):
    """
    Set one attribute on *obj* to *new_value*, storing the old value for undo.

    Parameters
    ----------
    obj : any object with ``getattr`` / ``setattr`` support
    attr : str
        Attribute name (may be dot-separated for nested: ``"params.t_end"``).
    new_value : Any
    """
    def __init__(self, obj: Any, attr: str, new_value: Any) -> None:
        self._obj        = obj
        self._attr       = attr
        self._new_value  = new_value
        self._old_value  = self._get(obj, attr)
        self.description = f"set {type(obj).__name__}.{attr} = {new_value!r}"
        self.merge_key   = ("modify", id(obj), attr)

    def merge_with(self, other: Command) -> bool:
        if not isinstance(other, ModifyPropertyCommand) or other.merge_key != self.merge_key:
            return False
        self._new_value  = other._new_value
        self.description = f"set {type(self._obj).__name__}.{self._attr} = {self._new_value!r}"
        return True

    # Dot-path helpers
    @staticmethod
    def _get(obj: Any, attr: str) -> Any:
        for part in attr.split("."):
            obj = getattr(obj, part)
        return obj

    @staticmethod
    def _set(obj: Any, attr: str, value: Any) -> None:
        parts = attr.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)

    def execute(self) -> CommandResult:
        try:
            self._set(self._obj, self._attr, self._new_value)
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._set(self._obj, self._attr, self._old_value)
            return CommandResult.ok(f"Restored {self._attr} = {self._old_value!r}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class RenameCommand(Command):
    """Rename a named entity (changes the ``id`` attribute)."""

    def __init__(self, entity: Any, new_name: str) -> None:
        self._entity   = entity
        self._new_name = new_name
        self._old_name = getattr(entity, "id", "")
        self.description = f"rename {type(entity).__name__} '{self._old_name}' → '{new_name}'"

    def execute(self) -> CommandResult:
        try:
            self._entity.id = self._new_name
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._entity.id = self._old_name
            return CommandResult.ok(f"Restored name: '{self._old_name}'")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class BatchPropertyCommand(Command):
    """
    Set multiple ``attr → value`` pairs atomically on a single object.

    All old values are captured before any change is applied; on undo
    they are all restored.  If any setter raises, the partial mutation is
    rolled back.

    Parameters
    ----------
    obj : any object
    properties : dict
        Mapping of attribute names (dot-path OK) → new values.
    """
    def __init__(self, obj: Any, properties: Dict[str, Any]) -> None:
        self._obj        = obj
        self._properties = properties
        self._old_values: Dict[str, Any] = {}
        for attr in properties:
            try:
                self._old_values[attr] = ModifyPropertyCommand._get(obj, attr)
            except AttributeError:
                self._old_values[attr] = None
        self.description = (f"batch set {len(properties)} props on "
                            f"{type(obj).__name__}")

    def execute(self) -> CommandResult:
        applied: List[str] = []
        try:
            for attr, value in self._properties.items():
                ModifyPropertyCommand._set(self._obj, attr, value)
                applied.append(attr)
            return CommandResult.ok(self.description)
        except Exception as exc:
            # Roll back already-applied changes
            for attr in applied:
                try:
                    ModifyPropertyCommand._set(self._obj, attr, self._old_values[attr])
                except Exception:
                    pass
            return CommandResult.fail(f"Batch set failed on '{attr}': {exc}")

    def undo(self) -> CommandResult:
        for attr, old_val in self._old_values.items():
            try:
                ModifyPropertyCommand._set(self._obj, attr, old_val)
            except Exception as exc:
                return CommandResult.fail(f"Batch undo failed on '{attr}': {exc}")
        return CommandResult.ok(f"Undone: {self.description}")


class SetHrrCommand(Command):
    """
    Change the HRRPUA (heat release rate per unit area) on a burning Surface.

    Optionally scales the value by a reference area so the caller can work
    in total HRR (kW) rather than HRRPUA (kW/m²).

    Parameters
    ----------
    surface : Surface
        The burning surface to modify.
    new_hrrpua : float
        New heat release rate per unit area in kW/m².
    area : float, optional
        If supplied, ``new_hrrpua = new_hrrpua / area`` (caller passes total HRR).
    """
    def __init__(self, surface: Any, new_hrrpua: float,
                 area: Optional[float] = None) -> None:
        self._surface    = surface
        self._area       = area
        self._new_hrrpua = new_hrrpua / area if area else new_hrrpua
        self._old_hrrpua = getattr(surface, "heat_release_rate", None)
        self.description = (
            f"set HRR on Surface '{getattr(surface, 'name', '?')}' "
            f"to {self._new_hrrpua:.1f} kW/m²"
        )

    def execute(self) -> CommandResult:
        try:
            self._surface.heat_release_rate = self._new_hrrpua
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._surface.heat_release_rate = self._old_hrrpua
            return CommandResult.ok(
                f"Restored HRR on '{getattr(self._surface, 'name', '?')}' "
                f"to {self._old_hrrpua}"
            )
        except Exception as exc:
            return CommandResult.fail(str(exc))


class DuplicateEntityCommand(Command):
    """
    Deep-copy an FDS entity and add the copy to the project under a new name.

    The copy is placed in the same collection as the original.

    Parameters
    ----------
    project : FdsProject
    entity : FdsEntity
        The entity to copy.
    new_name : str
        Name (ID) for the copy. Must be unique within the collection.
    """
    def __init__(self, project: Any, entity: Any, new_name: str) -> None:
        import copy as _copy
        self._project  = project
        self._original = entity
        self._copy     = _copy.deepcopy(entity)
        self._copy.name = new_name   # type: ignore[attr-defined]
        self.description = (
            f"duplicate {type(entity).__name__} "
            f"'{getattr(entity, 'name', '?')}' → '{new_name}'"
        )

    def execute(self) -> CommandResult:
        try:
            self._project.add_entity(self._copy)
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(
                EventType.ENTITY_DUPLICATED,
                {"original": self._original, "copy": self._copy},
                source="DuplicateEntityCommand",
            )
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._project.remove_entity_by_uid(self._copy.uid)
            return CommandResult.ok(f"Undone: {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))


class SetTimingCommand(Command):
    """Change the simulation time span on an FdsProject."""

    def __init__(self, project, t_end: float, t_begin: float = 0.0) -> None:
        self._project = project
        self._new_t_end   = t_end
        self._new_t_begin = t_begin
        self._old_t_end   = getattr(getattr(project, "params", project), "t_end",   0.0)
        self._old_t_begin = getattr(getattr(project, "params", project), "t_begin", 0.0)
        self.description  = f"set T_BEGIN={t_begin} T_END={t_end}"

    def execute(self) -> CommandResult:
        try:
            self._project.params.t_end   = self._new_t_end
            self._project.params.t_begin = self._new_t_begin
            return CommandResult.ok(self.description)
        except Exception as exc:
            return CommandResult.fail(str(exc))

    def undo(self) -> CommandResult:
        try:
            self._project.params.t_end   = self._old_t_end
            self._project.params.t_begin = self._old_t_begin
            return CommandResult.ok("Restored timing")
        except Exception as exc:
            return CommandResult.fail(str(exc))
