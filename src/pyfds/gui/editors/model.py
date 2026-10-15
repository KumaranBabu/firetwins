"""The logic behind the generic collection editor (plan step F5), free of Qt so it can be tested directly.

For one collection (``meshes``, ``surfaces`` ...) it lists the objects, describes each object's fields (from the
domain schema where there is one, plus every other simple field of the model), converts between the model's SI
values and the project's display units, applies edits as ONE undo step through the api, and builds the live FDS
record preview.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, get_args, get_origin

from pydantic import BaseModel


# Schema unit strings -> the unit layer's quantity kinds (only these are converted to English units).
UNIT_KINDS = {
    "m": "length", "m²": "area", "m2": "area", "m³": "volume", "m3": "volume", "°C": "temperature", "C": "temperature",
    "kW": "power", "kW/m²": "heat_flux", "kW/m2": "heat_flux", "Pa": "pressure", "m/s": "velocity",
    "kg/m³": "density", "kg/m3": "density", "kg": "mass", "kg/s": "mass_flow", "m³/s": "volume_flow",
    "kJ/kg/K": "specific_heat", "W/m/K": "conductivity",
}
# Collections whose "Add From Library" button exists, and the library category they draw from.
LIBRARY_CATEGORY = {"materials": "materials", "surfaces": "surfaces", "reactions": "reactions",
                    "species": "species", "particles": "particles"}
REF_COLLECTIONS = {"Surface": "surfaces", "Material": "materials", "Ramp": "ramps", "Reaction": "reactions",
                   "Species": "species", "Control": "controls", "Device": "devices", "Mesh": "meshes", "Prop": "props",
                   "Particle": "particles"}
_SKIP = {"fds_extra", "uid", "_uid"}


@dataclass
class FieldSpec:
    name: str
    label: str
    kind: str                       # float | int | str | bool | enum | vec | list_str | ref
    units: str = ""
    unit_kind: Optional[str] = None
    description: str = ""
    category: str = "General"
    advanced: bool = False
    enum_values: List[str] = field(default_factory=list)
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    length: int = 0                 # for vec
    int_vec: bool = False
    ref_collection: Optional[str] = None
    optional: bool = False
    row_class: Any = None                           # for rows: the sub-model class
    columns: List["FieldSpec"] = field(default_factory=list)


# Sub-model fields that name another object, and the collection to offer in a row's drop-down.
ROW_REFS = {"material_id": "materials", "surface_id": "surfaces", "ramp_id": "ramps", "spec_id": "species",
            "part_id": "particles"}


def _unwrap(annotation: Any) -> Tuple[Any, bool]:
    if get_origin(annotation) is typing.Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _kind_of(annotation: Any) -> Optional[Tuple[str, int, bool, bool]]:
    """(kind, vector length, int vector, optional) for a simple annotation, else None."""
    ann, optional = _unwrap(annotation)
    row = _row_class(ann)
    if row is not None:
        return "rows", 0, False, optional
    if ann is bool:
        return "bool", 0, False, optional
    if ann is int:
        return "int", 0, False, optional
    if ann is float:
        return "float", 0, False, optional
    if ann is str:
        return "str", 0, False, optional
    origin, args = get_origin(ann), get_args(ann)
    if origin is tuple and args and all(a in (int, float) for a in args) and Ellipsis not in args:
        return "vec", len(args), all(a is int for a in args), optional
    if origin in (list, typing.List) and args == (str,):
        return "list_str", 0, False, optional
    if origin in (list, typing.List) and args == (float,):
        return "list_float", 0, False, optional
    return None


def _row_class(ann: Any) -> Optional[type]:
    """The sub-model class of a ``List[SubModel]`` annotation whose fields are all simple, else None."""
    if get_origin(ann) in (list, typing.List):
        args = get_args(ann)
        if len(args) == 1 and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            if args[0].model_fields and all(_kind_of(i.annotation) is not None and _kind_of(i.annotation)[0] != "rows"
                                            for i in args[0].model_fields.values()):
                return args[0]
    return None


def _columns(row_class: type) -> List[FieldSpec]:
    cols = []
    for name, info in row_class.model_fields.items():
        kind, length, int_vec, optional = _kind_of(info.annotation)
        ref = ROW_REFS.get(name)
        cols.append(FieldSpec(name, name.replace("_", " ").capitalize(), "ref" if ref and kind == "str" else kind,
                              length=length, int_vec=int_vec, optional=optional or kind in ("list_str", "list_float"),
                              ref_collection=ref))
    return cols


class EntityEditorModel:
    def __init__(self, api: Any, attr: str) -> None:
        self.api = api
        self.attr = attr
        self.manager = getattr(api, attr)

    # -- the list ------------------------------------------------------------------------
    def entities(self) -> List[Any]:
        return list(self.manager.all())

    def names(self) -> List[str]:
        return [getattr(e, "name", "?") for e in self.entities()]

    def get(self, name: str) -> Optional[Any]:
        return next((e for e in self.entities() if getattr(e, "name", None) == name), None)

    def create(self, name: Optional[str] = None) -> Any:
        return self.manager.create_default(name)

    def rename(self, entity: Any, new_name: str) -> Any:
        if not new_name.strip():
            raise ValueError("a name cannot be empty")
        return self.manager.rename(entity, new_name)

    def delete(self, entity: Any) -> None:
        self.manager.remove(entity)

    def clone(self, entity: Any) -> Any:
        base = f"{entity.name}_copy"
        taken = set(self.names())
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}{n}"
        fields = {k: v for k, v in entity.model_dump().items() if k not in ("name", "uid", "_uid")}
        fresh = self.manager.create_default(name)
        try:
            self.manager.update(fresh, **{k: getattr(entity, k) for k in fields if k in type(entity).model_fields})
        except Exception:
            self.manager.remove(fresh)
            raise
        return fresh

    # -- describing the fields -----------------------------------------------------------------
    def fields(self, entity: Any) -> List[FieldSpec]:
        """Schema fields first (in schema order), then every other simple field as 'Other' (advanced)."""
        model_fields = type(entity).model_fields
        out: List[FieldSpec] = []
        seen = set()
        schema = self.api.schema.for_entity(entity)
        if schema is not None:
            for p in schema.properties:
                info = model_fields.get(p.name)
                if info is None or p.name in _SKIP:
                    continue
                k = _kind_of(info.annotation)
                if k is None:
                    continue
                kind, length, int_vec, optional = k
                if p.field_type.name == "ENUM" and kind == "str":
                    kind = "enum"
                elif p.field_type.name == "ENTITY_REF" and kind == "str":
                    kind = "ref"
                spec = FieldSpec(
                    p.name, p.display_name, kind, p.units, UNIT_KINDS.get(p.units), p.description, p.category,
                    p.advanced, list(p.enum_values), p.min_val, p.max_val, length, int_vec,
                    REF_COLLECTIONS.get(p.ref_type or ""), optional)
                self._rows_info(spec, info.annotation)
                out.append(spec)
                seen.add(p.name)
        for name, info in model_fields.items():
            if name in seen or name in _SKIP:
                continue
            k = _kind_of(info.annotation)
            if k is None:
                continue
            kind, length, int_vec, optional = k
            spec = FieldSpec(name, name.replace("_", " ").capitalize(), kind, category="Other", advanced=True,
                             length=length, int_vec=int_vec, optional=optional)
            self._rows_info(spec, info.annotation)
            out.append(spec)
        return out

    @staticmethod
    def _rows_info(spec: FieldSpec, annotation: Any) -> None:
        """A list of sub-objects (layers, pyrolysis reactions) gets its own tab and a column per field."""
        if spec.kind == "rows":
            spec.row_class = _row_class(_unwrap(annotation)[0])
            spec.columns = _columns(spec.row_class)
            spec.category, spec.advanced = spec.label, False

    def unsupported_fields(self, entity: Any) -> List[str]:
        """Fields the form cannot edit yet (lists of sub-objects such as layers or pyrolysis reactions)."""
        shown = {f.name for f in self.fields(entity)}
        return [n for n in type(entity).model_fields if n not in shown and n not in _SKIP]

    # -- values and units ---------------------------------------------------------------------
    def to_display(self, spec: FieldSpec, value: Any) -> Any:
        if spec.kind == "rows":
            return [r.model_dump() if isinstance(r, BaseModel) else dict(r) for r in (value or [])]
        if value is not None and spec.kind == "float" and spec.unit_kind:
            return self.api.units.to_display(value, spec.unit_kind)
        return value

    def from_display(self, spec: FieldSpec, value: Any) -> Any:
        """A value as the form holds it -> the model value (SI, right container type)."""
        if spec.kind == "float":
            if value is None:
                return None
            if spec.unit_kind:
                return self.api.units.from_display(value, spec.unit_kind)
            return float(value)
        if spec.kind == "int":
            return None if value is None else int(value)
        if spec.kind == "vec":
            if value is None:
                return None
            return tuple(int(v) if spec.int_vec else float(v) for v in value)
        if spec.kind == "list_str":
            items = [str(v) for v in (value or [])]
            return (items or None) if spec.optional else items
        if spec.kind == "list_float":
            items = [float(v) for v in (value or [])]
            return (items or None) if spec.optional else items
        if spec.kind == "rows":
            try:
                return [spec.row_class(**{k: v for k, v in dict(r).items() if v is not None}) for r in (value or [])]
            except Exception as exc:
                raise ValueError(f"{spec.label}: {exc}") from None
        if spec.kind in ("str", "enum", "ref"):
            text = "" if value is None else str(value)
            return (text or None) if spec.optional else text
        return bool(value)

    def unit_label(self, spec: FieldSpec) -> str:
        if spec.unit_kind:
            return self.api.units.label(spec.unit_kind)
        return spec.units

    def current(self, entity: Any, specs: Optional[List[FieldSpec]] = None) -> Dict[str, Any]:
        return {s.name: self.to_display(s, getattr(entity, s.name, None)) for s in (specs or self.fields(entity))}

    # -- editing ----------------------------------------------------------------------------------
    def changes(self, entity: Any, edited: Dict[str, Any]) -> Dict[str, Any]:
        """The model values that differ from the object's current ones (SI), ready for ``update``."""
        specs = {s.name: s for s in self.fields(entity)}
        out: Dict[str, Any] = {}
        for name, shown in edited.items():
            spec = specs.get(name)
            if spec is None:
                raise KeyError(f"{name!r} is not an editable field of {type(entity).__name__}")
            new = self.from_display(spec, shown)
            if new is None and not spec.optional and spec.kind in ("float", "int", "vec"):
                raise ValueError(f"{spec.label} needs a value")
            old = getattr(entity, name, None)
            if spec.kind == "bool":
                old = bool(old)                        # an unset flag and False are the same thing
            if isinstance(old, list) and isinstance(new, tuple):
                new = list(new)
            if not _same(_norm(old), _norm(new)):
                out[name] = new
        return out

    def apply(self, entity: Any, edited: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the edits as one undo step (a name change goes through ``rename``). Returns what changed."""
        changes = self.changes(entity, edited)
        new_name = changes.pop("name", None)
        with self.api.history.transaction(f"edit {getattr(entity, 'name', '')}"):
            if changes:
                self.manager.update(entity, **changes)
            if new_name is not None:
                self.rename(entity, new_name)
        if new_name is not None:
            changes["name"] = new_name
        return changes

    def extras(self, entity: Any) -> Dict[str, str]:
        return dict(getattr(entity, "fds_extra", None) or {})

    def set_extra(self, entity: Any, key: str, value: str) -> None:
        self.manager.set_extra(entity, key, value)

    def remove_extra(self, entity: Any, key: str) -> None:
        self.manager.remove_extra(entity, key)

    # -- record preview ---------------------------------------------------------------------------
    def probe(self, entity: Any, edited: Optional[Dict[str, Any]] = None) -> Any:
        """A throwaway copy of the object with the unsaved edits applied (the project is untouched)."""
        probe = entity.model_copy(deep=True)
        if edited:
            for name, value in self.changes(entity, edited).items():
                setattr(probe, name, value)
        return probe

    def validate(self, entity: Any, edited: Dict[str, Any]) -> None:
        """Raise ``ValueError`` if the edits cannot be saved as they are (checks beyond a field's own type)."""
        if self.attr != "materials":
            return
        p = self.probe(entity, edited)
        gases = p.nu_gases or []
        if len(gases) != len(p.spec_ids or []):
            raise ValueError("every by-product gas needs a species and a yield")
        if any(v < 0 for v in gases) or (p.nu_residue or 0) < 0:
            raise ValueError("by-product yields cannot be negative")
        total = sum(gases) + (p.nu_residue or 0.0)
        if total > 1.0 + 1e-6:
            raise ValueError(f"by-product yields add up to {total:.3f}; they cannot exceed 1")
        if p.nu_residue and not p.residue_id:
            raise ValueError("a residue yield needs a residue material")
        if p.residue_id and p.residue_id == p.name:
            raise ValueError("a material cannot be its own residue")
        if p.residue_id and p.residue_id not in {m.name for m in self.entities()}:
            raise ValueError(f"residue material {p.residue_id!r} does not exist")

    def record(self, entity: Any, edited: Optional[Dict[str, Any]] = None) -> str:
        """The FDS record(s) for the object, with unsaved edits applied to a throwaway copy."""
        probe = self.probe(entity, edited)
        try:
            return self.api.clipboard.to_fds_text([entity], substitute={id(entity): probe}).rstrip("\n")
        except Exception as exc:                       # a record the writer cannot make is not an editor failure
            return f"(no FDS record: {exc})"

    # -- libraries and read-only information ----------------------------------------------------------
    def library_names(self) -> List[str]:
        cat = LIBRARY_CATEGORY.get(self.attr)
        return self.api.library.names(cat) if cat else []

    def add_from_library(self, name: str) -> Any:
        cat = LIBRARY_CATEGORY.get(self.attr)
        if cat is None:
            raise ValueError("this collection has no library")
        return self.api.library.add_to_model(cat, name)

    def info(self, entity: Any) -> List[str]:
        """Read-only facts to show beside the form (derived values, the kind of surface ...)."""
        lines: List[str] = []
        try:
            if self.attr == "meshes":
                s = self.manager.stats(entity)
                lines += [f"{k.replace('_', ' ')}: {v}" for k, v in s.items()]
                lines.append(f"alignment test: {self.manager.alignment_test().get(entity.name)}")
            elif self.attr == "surfaces":
                lines.append(f"surface type: {self.manager.kind(entity.name)}")
        except Exception as exc:
            lines.append(f"({exc})")
        return lines


def _norm(v: Any) -> Any:
    """Sub-model rows compared as plain dicts."""
    if isinstance(v, list) and v and isinstance(v[0], BaseModel):
        return [r.model_dump() for r in v]
    return v


def _same(a: Any, b: Any) -> bool:
    if a in (None, [], ()) and b in (None, [], ()):
        return True                                    # "no value" is one state, however it is spelled
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b
