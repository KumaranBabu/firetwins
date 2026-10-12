"""
Builds a ``SchemaFormDialog``-compatible JSON-Schema for editing an
EXISTING entity's fields.

Reuses the exact same dialog class the "Add..." actions use
(``entity_dialogs.SchemaFormDialog``) — just with a schema introspected
from the live Pydantic model instead of a hand-written ``ToolSpec``, and
field defaults patched to the entity's *current* values instead of generic
add-new-entity starting points.

Scope: only "simple" field types are exposed for editing — float / int /
str / bool, and fixed-length tuples of numbers (``xyz``, ``rgb``,
``orientation``, ...). List-of-model fields (``Surface.layers``,
``Material.reactions``) and free-form variable-length lists
(``Ramp.times``, ``spec_ids``) need a dedicated sub-editor and are
deliberately out of scope here — editing those still requires code, same
as before this module existed.
"""
from __future__ import annotations

import dataclasses
import typing
from typing import Any, Dict, Optional, get_args, get_origin


def _unwrap_optional(annotation: Any) -> Any:
    """``Optional[X]`` (i.e. ``Union[X, None]``) -> ``X``; anything else unchanged."""
    if get_origin(annotation) is typing.Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _field_schema(annotation: Any, current_value: Any) -> Optional[Dict[str, Any]]:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if annotation is float:
        return {"type": "number", "default": current_value if current_value is not None else 0.0}
    if annotation is int:
        return {"type": "integer", "default": current_value if current_value is not None else 0}
    if annotation is bool:
        return {"type": "boolean", "default": bool(current_value) if current_value is not None else False}
    if annotation is str:
        return {"type": "string", "default": current_value if current_value is not None else ""}

    if origin is tuple:
        args = get_args(annotation)
        if args and all(a in (float, int) for a in args):
            item_type = "integer" if all(a is int for a in args) else "number"
            n = len(args)
            schema: Dict[str, Any] = {
                "type": "array",
                "items": {"type": item_type},
                "minItems": n, "maxItems": n,
            }
            if current_value is not None:
                schema["default"] = list(current_value)
            return schema

    return None  # unsupported type (List[...], nested models, Enum, ...) — skip for v1


def _fields_of(entity: Any):
    """Yield ``(field_name, annotation)`` for pydantic models *and* plain
    dataclasses (``Scenario``, ``Floor`` — not ``FdsEntity`` subclasses, so
    they carry no ``model_fields``)."""
    model_fields = getattr(type(entity), "model_fields", None)
    if model_fields is not None:
        for name, info in model_fields.items():
            yield name, info.annotation
        return
    if dataclasses.is_dataclass(entity):
        # Dataclass modules commonly use `from __future__ import annotations`,
        # which turns every annotation into an unresolved string — resolve
        # forward refs properly instead of trusting field.type directly.
        hints = typing.get_type_hints(type(entity))
        for f in dataclasses.fields(entity):
            yield f.name, hints.get(f.name, f.type)


def build_edit_schema(entity: Any) -> Dict[str, Any]:
    """One editable property per simple-typed field, defaulted to the
    entity's current value. Nothing is marked required — editing an
    already-valid entity, unlike creating a new one, has no "incomplete"
    state to guard against.

    ``name`` is excluded for plain-dataclass entities (Scenario, Floor):
    both are stored internally in dicts keyed by name, so a raw
    ``setattr(entity, "name", ...)`` here would desync the entity from its
    own dict key — those two types get a dedicated, dict-aware rename path
    instead (or, for now, no rename at all)."""
    properties: Dict[str, Any] = {}
    skip = {"tags"}  # list-of-str GUI metadata — no simple editor for it yet
    if dataclasses.is_dataclass(entity):
        skip = skip | {"name"}
    for field_name, annotation in _fields_of(entity):
        if field_name in skip:
            continue
        current_value = getattr(entity, field_name, None)
        prop = _field_schema(annotation, current_value)
        if prop is not None:
            properties[field_name] = prop
    return {"type": "object", "properties": properties, "required": []}


def apply_edits(api: Any, entity: Any, values: Dict[str, Any]) -> int:
    """Apply each changed field via the undo-able ``ModifyPropertyCommand``
    (one command per changed field, same pattern as the Simulation
    Parameters dialog). Returns the number of fields actually changed —
    fields left equal to their current value are skipped, not re-applied."""
    changed = 0
    for key, value in values.items():
        current = getattr(entity, key, None)
        if isinstance(current, tuple) and isinstance(value, list):
            value = tuple(value)
        if current == value:
            continue
        api.set_property(entity, key, value)
        changed += 1
    return changed
