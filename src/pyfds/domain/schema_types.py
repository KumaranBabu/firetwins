"""Schema types: field types, property descriptors, entity schemas and the registry."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class FieldType(Enum):
    FLOAT       = auto()   # single float
    INT         = auto()   # single integer
    STRING      = auto()   # free text
    BOOL        = auto()   # True/False
    ENUM        = auto()   # one of a fixed set of strings
    VECTOR2     = auto()   # (x, y)
    VECTOR3     = auto()   # (x, y, z)
    VECTOR6     = auto()   # XB = (xmin,xmax,ymin,ymax,zmin,zmax)
    VECTOR_IJK  = auto()   # (i, j, k) integer triple
    LIST_FLOAT  = auto()   # variable-length float list
    LIST_INT    = auto()   # variable-length int list
    LIST_STRING = auto()   # variable-length string list
    COLOR_RGB   = auto()   # (r, g, b) 0..255
    COLOR_NAME  = auto()   # FDS named colour string
    ENTITY_REF  = auto()   # ID reference to another entity
    FILE_PATH   = auto()   # filesystem path string


@dataclass
class PropertyDescriptor:
    """
    Describes one field on an FDS entity.

    Parameters
    ----------
    name : str
        Python attribute name (matches the dataclass / Pydantic field).
    display_name : str
        Human-readable label for GUI panels.
    field_type : FieldType
        Controls which GUI widget is shown.
    units : str
        Physical unit string, e.g. "kW/m²", "m", "°C", "s". Empty if dimensionless.
    description : str
        One-sentence description for tooltips and ``pyfds schema`` output.
    required : bool
        If True the field must be set for a valid FDS input.
    min_val : float, optional
        Minimum allowed value (FLOAT / INT / VECTOR fields).
    max_val : float, optional
        Maximum allowed value.
    enum_values : list[str], optional
        Legal string choices (ENUM fields).
    default : Any
        Default value used when creating a new entity of this type.
    fds_param : str
        Corresponding FDS namelist parameter name (uppercase).
    category : str
        Grouping for multi-section property editors (e.g. "Geometry", "Fire").
    advanced : bool
        If True the field is hidden in simplified GUI views.
    ref_type : str, optional
        For ENTITY_REF fields: the entity class name being referenced.
    """
    name:         str
    display_name: str
    field_type:   FieldType
    units:        str         = ""
    description:  str         = ""
    required:     bool        = False
    min_val:      Optional[float] = None
    max_val:      Optional[float] = None
    enum_values:  List[str]   = field(default_factory=list)
    default:      Any         = None
    fds_param:    str         = ""
    category:     str         = "General"
    advanced:     bool        = False
    ref_type:     Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":         self.name,
            "display_name": self.display_name,
            "field_type":   self.field_type.name,
            "units":        self.units,
            "description":  self.description,
            "required":     self.required,
            "min_val":      self.min_val,
            "max_val":      self.max_val,
            "enum_values":  list(self.enum_values),
            "default":      self.default,
            "fds_param":    self.fds_param,
            "category":     self.category,
            "advanced":     self.advanced,
            "ref_type":     self.ref_type,
        }


@dataclass
class EntitySchema:
    """
    Ordered collection of ``PropertyDescriptor`` objects for one entity type.

    Parameters
    ----------
    entity_class_name : str
        Python class name, e.g. ``"Mesh"``, ``"Obstruction"``.
    display_name : str
        Human-readable name shown in GUI dialogs.
    fds_namelist : str
        FDS namelist keyword, e.g. ``"MESH"``, ``"OBST"``.
    category : str
        Top-level grouping in the GUI ribbon / model tree.
    description : str
        One-sentence summary.
    properties : list[PropertyDescriptor]
        Ordered list of property descriptors (determines panel order).
    """
    entity_class_name: str
    display_name:      str
    fds_namelist:      str
    category:          str         = "Geometry"
    description:       str         = ""
    properties:        List[PropertyDescriptor] = field(default_factory=list)

    def get(self, name: str) -> Optional[PropertyDescriptor]:
        """Return the descriptor for *name*, or None."""
        for p in self.properties:
            if p.name == name:
                return p
        return None

    def required_properties(self) -> List[PropertyDescriptor]:
        return [p for p in self.properties if p.required]

    def by_category(self) -> Dict[str, List[PropertyDescriptor]]:
        cats: Dict[str, List[PropertyDescriptor]] = {}
        for p in self.properties:
            cats.setdefault(p.category, []).append(p)
        return cats

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_class_name": self.entity_class_name,
            "display_name":      self.display_name,
            "fds_namelist":      self.fds_namelist,
            "category":          self.category,
            "description":       self.description,
            "properties": [p.to_dict() for p in self.properties],
        }


class SchemaRegistry:
    """
    Thread-safe registry mapping entity class names to ``EntitySchema`` objects.

    Usage::

        reg = get_schema_registry()
        schema = reg.get("Mesh")              # by class name
        schema = reg.for_entity(my_mesh)      # auto-detect from instance
        names  = reg.entity_names             # all registered names
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._schemas: Dict[str, EntitySchema] = {}

    def register(self, schema: EntitySchema) -> None:
        with self._lock:
            self._schemas[schema.entity_class_name] = schema
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.SCHEMA_REGISTERED, schema,
                                  source="SchemaRegistry")
        except Exception:
            pass

    def get(self, class_name: str) -> Optional[EntitySchema]:
        with self._lock:
            return self._schemas.get(class_name)

    def for_entity(self, entity: Any) -> Optional[EntitySchema]:
        return self.get(type(entity).__name__)

    @property
    def entity_names(self) -> List[str]:
        with self._lock:
            return sorted(self._schemas.keys())

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._schemas.items()}

    def __repr__(self) -> str:
        return f"<SchemaRegistry entities={len(self._schemas)}>"


def _p(name: str, display: str, ft: FieldType, units: str = "", desc: str = "",
       required: bool = False, min_val=None, max_val=None,
       enum_values=None, default=None, fds_param: str = "",
       category: str = "General", advanced: bool = False,
       ref_type: str = None) -> PropertyDescriptor:
    return PropertyDescriptor(
        name=name, display_name=display, field_type=ft,
        units=units, description=desc, required=required,
        min_val=min_val, max_val=max_val,
        enum_values=enum_values or [],
        default=default, fds_param=fds_param or name.upper(),
        category=category, advanced=advanced, ref_type=ref_type,
    )


FT = FieldType  # shorthand
