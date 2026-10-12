"""
PyFDS Property Schema System
=============================
Metadata registry that describes every FDS entity field so that:

- GUI property editors can render the right widget (slider, combo, text box)
- AI agents know valid value ranges and enum options without reading source
- CLI ``pyfds schema <type>`` can dump human-readable field specs
- Future validation rules can generate machine-checkable constraints

Design
------
``PropertyDescriptor``   — metadata for one field on one entity type
``EntitySchema``         — ordered collection of descriptors for one entity
``SchemaRegistry``       — singleton-style registry; pre-loaded with all FDS types

Usage::

    reg = get_schema_registry()
    schema = reg.for_entity(mesh)
    for prop in schema.properties:
        print(prop.display_name, prop.units, prop.min_val, prop.max_val)

    # AI agent introspection
    schema_dict = schema.to_dict()
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Type


# ---------------------------------------------------------------------------
# Field type taxonomy
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PropertyDescriptor
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# EntitySchema
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SchemaRegistry
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers for building descriptors concisely
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Built-in entity schemas
# ---------------------------------------------------------------------------

def _build_mesh_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Mesh",
        display_name="Mesh Region",
        fds_namelist="MESH",
        category="Mesh",
        description="Defines one rectangular FDS computation mesh block.",
        properties=[
            _p("name",        "ID",          FT.STRING,    required=True,  fds_param="ID",
               desc="Unique name for this mesh block."),
            _p("x_min",       "X min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",       "X max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",       "Y min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",       "Y max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",       "Z min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",       "Z max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("cell_count",  "IJK",         FT.VECTOR_IJK, required=True, fds_param="IJK", category="Mesh",
               desc="Cell count (I, J, K). Each value must satisfy the Poisson rule: 2^a·3^b·5^c."),
            _p("mpi_processor", "MPI Rank",  FT.INT,   min_val=0, fds_param="MPI_PROCESS", category="Mesh",
               desc="MPI process index (0-based). Leave blank for auto-assignment."),
            _p("cylindrical", "Cylindrical", FT.BOOL,  fds_param="CYLINDRICAL", category="Mesh",
               desc="Enable cylindrical coordinates for axisymmetric simulations.", advanced=True),
            _p("color",       "Color",       FT.COLOR_NAME, fds_param="COLOR", category="Display"),
        ],
    )


def _build_obstruction_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Obstruction",
        display_name="Obstruction",
        fds_namelist="OBST",
        category="Geometry",
        description="Solid rectangular block (OBST). The fundamental geometry primitive.",
        properties=[
            _p("name",       "ID",        FT.STRING,   required=True,  fds_param="ID"),
            _p("x_min",      "X min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",      "X max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",      "Y min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",      "Y max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",      "Z min",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",      "Z max",     FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("surface_id", "Surface",   FT.ENTITY_REF, required=True, fds_param="SURF_ID",
               ref_type="Surface", category="Material"),
            _p("color",      "Color",     FT.COLOR_NAME, fds_param="COLOR", category="Display"),
            _p("transparency","Transparency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="TRANSPARENCY", category="Display"),
            _p("thicken",    "Thicken",   FT.BOOL,  fds_param="THICKEN", category="Options",
               desc="Force the obstruction to be one cell thick even if it appears thinner.", advanced=True),
            _p("allow_vent", "Allow Vent",FT.BOOL,  fds_param="ALLOW_VENT", category="Options", advanced=True),
            _p("ctrl_id",    "Control",   FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("mult_id",    "Multiplier",FT.ENTITY_REF, fds_param="MULT_ID", ref_type="Mult", category="Options", advanced=True),
        ],
    )


def _build_surface_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Surface",
        display_name="Surface",
        fds_namelist="SURF",
        category="Materials",
        description="Defines boundary condition / material properties for faces.",
        properties=[
            _p("name",             "ID",           FT.STRING, required=True, fds_param="ID"),
            _p("heat_release_rate","HRRPUA",        FT.FLOAT, "kW/m²", min_val=0.0, fds_param="HRRPUA",
               category="Fire", desc="Heat release rate per unit area. Set >0 for a burning surface."),
            _p("tau_q",            "Ramp-up time", FT.FLOAT, "s", min_val=0.0, fds_param="TAU_Q", category="Fire"),
            _p("ramp_q",           "HRR Ramp",     FT.ENTITY_REF, fds_param="RAMP_Q", ref_type="Ramp", category="Fire"),
            _p("tmp_front",        "Temp (front)", FT.FLOAT, "°C", fds_param="TMP_FRONT", category="Thermal"),
            _p("vel",              "Velocity",     FT.FLOAT, "m/s", fds_param="VEL", category="Flow"),
            _p("volume_flow",      "Volume Flow",  FT.FLOAT, "m³/s", fds_param="VOLUME_FLOW", category="Flow"),
            _p("mass_flux",        "Mass Flux",    FT.FLOAT, "kg/(m²·s)", fds_param="MASS_FLUX", category="Flow"),
            _p("backing",          "Backing",      FT.ENUM,  fds_param="BACKING", category="Thermal",
               enum_values=["VOID", "INSULATED", "EXPOSED"], default="VOID"),
            _p("burn_away",        "Burn Away",    FT.BOOL,  fds_param="BURN_AWAY", category="Fire"),
            _p("matl_id",          "Material ID",  FT.ENTITY_REF, fds_param="MATL_ID", ref_type="Material", category="Layers"),
            _p("color",            "Color",        FT.COLOR_NAME, fds_param="COLOR", category="Display"),
            _p("transparency",     "Transparency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="TRANSPARENCY", category="Display"),
            _p("texture_map",      "Texture",      FT.FILE_PATH, fds_param="TEXTURE_MAP", category="Display", advanced=True),
        ],
    )


def _build_vent_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Vent",
        display_name="Vent",
        fds_namelist="VENT",
        category="Geometry",
        description="Planar boundary condition patch (VENT). Used for openings, inlets, and fire.",
        properties=[
            _p("name",            "ID",          FT.STRING,   required=True, fds_param="ID"),
            _p("x_min",           "X min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("x_max",           "X max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_min",           "Y min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("y_max",           "Y max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_min",           "Z min",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("z_max",           "Z max",       FT.FLOAT, "m", required=True, fds_param="XB", category="Geometry"),
            _p("surface_id",      "Surface",     FT.ENTITY_REF, required=True, fds_param="SURF_ID",
               ref_type="Surface", default="OPEN"),
            _p("ctrl_id",         "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("dynamic_pressure","Dyn. Pressure",FT.FLOAT, "Pa", fds_param="DYNAMIC_PRESSURE", category="Flow"),
            _p("color",           "Color",       FT.COLOR_NAME, fds_param="COLOR", category="Display"),
        ],
    )


def _build_device_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Device",
        display_name="Device / Sensor",
        fds_namelist="DEVC",
        category="Devices",
        description="Measurement device, sprinkler, or detector (DEVC).",
        properties=[
            _p("name",             "ID",          FT.STRING,   required=True, fds_param="ID"),
            _p("quantity",         "Quantity",    FT.STRING,   required=True, fds_param="QUANTITY",
               desc="FDS output quantity, e.g. TEMPERATURE, HEAT FLUX, VELOCITY."),
            _p("quantity2",        "Quantity 2",  FT.STRING,   fds_param="QUANTITY2", category="Output",
               desc="Optional second output quantity.", advanced=True),
            _p("x",                "X",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("y",                "Y",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("z",                "Z",           FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("orientation",      "Orientation", FT.VECTOR3,  fds_param="ORIENTATION", category="Location"),
            _p("prop_id",          "Property Set",FT.ENTITY_REF, fds_param="PROP_ID", ref_type="Prop", category="Sprinkler"),
            _p("ctrl_id",          "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control", category="Control"),
            _p("setpoint",         "Set Point",   FT.FLOAT,    fds_param="SETPOINT", category="Control"),
            _p("statistics",       "Statistics",  FT.ENUM,     fds_param="STATISTICS",
               enum_values=["", "MAX", "MIN", "MEAN", "RMS", "COV"], category="Output"),
            _p("latch",            "Latch",       FT.BOOL,     fds_param="LATCH", default=True, category="Control"),
            _p("time_averaged",    "Time-avg",    FT.BOOL,     fds_param="TIME_AVERAGED", category="Output", advanced=True),
            _p("duct_id",          "Duct ID",     FT.ENTITY_REF, fds_param="DUCT_ID", ref_type="HvacDuct", category="HVAC", advanced=True),
        ],
    )


def _build_material_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Material",
        display_name="Material",
        fds_namelist="MATL",
        category="Materials",
        description="Solid material thermal and pyrolysis properties (MATL).",
        properties=[
            _p("name",            "ID",            FT.STRING, required=True, fds_param="ID"),
            _p("density",         "Density",       FT.FLOAT, "kg/m³", required=True, min_val=0.01, fds_param="DENSITY"),
            _p("conductivity",    "Conductivity",  FT.FLOAT, "W/(m·K)", required=True, min_val=0.0, fds_param="CONDUCTIVITY"),
            _p("specific_heat",   "Specific Heat", FT.FLOAT, "kJ/(kg·K)", required=True, min_val=0.0, fds_param="SPECIFIC_HEAT"),
            _p("emissivity",      "Emissivity",    FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="EMISSIVITY"),
            _p("heat_of_reaction","Heat of Reaction",FT.FLOAT,"kJ/kg", min_val=0.0, fds_param="HEAT_OF_REACTION", category="Pyrolysis"),
            _p("reference_temperature","Ref. Temp",FT.FLOAT,"°C", fds_param="REFERENCE_TEMPERATURE", category="Pyrolysis"),
            _p("a",               "A (Arrhenius)", FT.FLOAT, "1/s", fds_param="A", category="Pyrolysis", advanced=True),
            _p("e",               "E (Activation)",FT.FLOAT, "J/mol", fds_param="E", category="Pyrolysis", advanced=True),
            _p("n_reactions",     "N Reactions",   FT.INT, min_val=1, fds_param="N_REACTIONS", category="Pyrolysis", advanced=True),
        ],
    )


def _build_reaction_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Reaction",
        display_name="Reaction",
        fds_namelist="REAC",
        category="Combustion",
        description="Gas-phase combustion reaction (REAC). Typically one per simulation.",
        properties=[
            _p("name",                  "ID",             FT.STRING, required=True, fds_param="ID"),
            _p("fuel",                  "Fuel Species",   FT.STRING, fds_param="FUEL"),
            _p("formula",               "Formula",        FT.STRING, fds_param="FORMULA", advanced=True),
            _p("heat_of_combustion",    "Heat of Comb.",  FT.FLOAT, "kJ/kg", min_val=0.0, fds_param="HEAT_OF_COMBUSTION"),
            _p("soot_yield",            "Soot Yield",     FT.FLOAT, "kg/kg", min_val=0.0, max_val=1.0, fds_param="SOOT_YIELD"),
            _p("co_yield",              "CO Yield",       FT.FLOAT, "kg/kg", min_val=0.0, max_val=1.0, fds_param="CO_YIELD"),
            _p("radiative_fraction",    "Rad. Fraction",  FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="RADIATIVE_FRACTION"),
            _p("lower_oxygen_limit",    "LOL",            FT.FLOAT, "vol fraction", min_val=0.0, max_val=0.3, fds_param="LOWER_OXYGEN_LIMIT", advanced=True),
            _p("auto_ignition_temperature","Auto-ignition",FT.FLOAT,"°C", fds_param="AUTO_IGNITION_TEMPERATURE", advanced=True),
            _p("fuel_radcal_id",        "RADCAL Fuel",    FT.STRING, fds_param="FUEL_RADCAL_ID", advanced=True),
        ],
    )


def _build_ramp_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Ramp",
        display_name="Ramp",
        fds_namelist="RAMP",
        category="Controls",
        description="Time-varying scalar function (RAMP). Each T/F pair is one namelist line.",
        properties=[
            _p("name",   "ID",     FT.STRING, required=True, fds_param="ID"),
            _p("times",  "Times",  FT.LIST_FLOAT, "s", required=True, fds_param="T",
               desc="Strictly increasing time values."),
            _p("values", "Values", FT.LIST_FLOAT, required=True, fds_param="F",
               desc="Function values at corresponding time points."),
        ],
    )


def _build_mesh_transform_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="MeshTransform",
        display_name="Mesh Transform (TRN)",
        fds_namelist="TRNX/TRNY/TRNZ",
        category="Mesh",
        description="Non-uniform mesh cell stretching control point.",
        properties=[
            _p("name",        "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("direction",   "Direction",   FT.ENUM, required=True, fds_param="",
               enum_values=["X", "Y", "Z"]),
            _p("mesh_number", "Mesh Number", FT.INT, min_val=1, fds_param="MESH_NUMBER"),
            _p("ideriv",      "IDERIV",      FT.INT, min_val=0, max_val=1, fds_param="IDERIV",
               enum_values=["0", "1"], desc="0=piecewise uniform, 1=stretching."),
            _p("cc",          "CC",          FT.FLOAT, "m", fds_param="CC",
               desc="Physical coordinate of the control point."),
            _p("pc",          "PC",          FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="PC",
               desc="Fractional position within the mesh (0..1)."),
        ],
    )


def _build_geom_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Geom",
        display_name="Geometry (GEOM)",
        fds_namelist="GEOM",
        category="Geometry",
        description="Complex geometry defined by a triangulated surface mesh or file.",
        properties=[
            _p("name",         "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("surf_id",      "Surface",     FT.ENTITY_REF, required=True, fds_param="SURF_ID", ref_type="Surface"),
            _p("binary_file",  "Binary File", FT.FILE_PATH, fds_param="BINARY_FILE",
               desc="Path to a binary geometry file (.bingeom)."),
            _p("is_terrain",   "Is Terrain",  FT.BOOL, fds_param="IS_TERRAIN"),
            _p("component_only","Component Only", FT.BOOL, fds_param="COMPONENT_ONLY", advanced=True),
            _p("move_id",      "Move ID",     FT.STRING, fds_param="MOVE_ID", advanced=True),
        ],
    )


def _build_control_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Control",
        display_name="Control Logic",
        fds_namelist="CTRL",
        category="Controls",
        description="Logic controller for activating/deactivating model components.",
        properties=[
            _p("name",             "ID",             FT.STRING, required=True, fds_param="ID"),
            _p("function_type",    "Function",       FT.ENUM, required=True, fds_param="FUNCTION_TYPE",
               enum_values=["CUSTOM", "ANY", "ALL", "ONLY", "AT_LEAST", "DEADBAND",
                            "TIME_DELAY", "PERCENTILE", "CYCLING"]),
            _p("input_id",         "Input ID",       FT.ENTITY_REF, fds_param="INPUT_ID"),
            _p("setpoint",         "Set Point",      FT.FLOAT, fds_param="SETPOINT"),
            _p("delay",            "Delay",          FT.FLOAT, "s", min_val=0.0, fds_param="DELAY"),
            _p("latch",            "Latch",          FT.BOOL, default=True, fds_param="LATCH"),
            _p("deadband",         "Dead Band",      FT.VECTOR2, fds_param="DEADBAND", advanced=True),
            _p("percentile_rank",  "Percentile Rank",FT.FLOAT, min_val=0.0, max_val=100.0,
               fds_param="PERCENTILE_RANK", advanced=True),
            _p("ramp_id",          "Ramp ID",        FT.ENTITY_REF, fds_param="RAMP_ID", ref_type="Ramp", advanced=True),
        ],
    )


def _build_hvac_node_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacNode",
        display_name="HVAC Node",
        fds_namelist="NODE",
        category="HVAC",
        description="Connection point in the HVAC duct network.",
        properties=[
            _p("name",    "ID",      FT.STRING, required=True, fds_param="ID"),
            _p("x",       "X",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("y",       "Y",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("z",       "Z",       FT.FLOAT, "m", fds_param="XYZ", category="Location"),
            _p("ambient", "Ambient", FT.BOOL, fds_param="AMBIENT",
               desc="If True this node connects the network to the ambient environment."),
            _p("vent_id", "Vent ID", FT.ENTITY_REF, fds_param="VENT_ID", ref_type="Vent"),
        ],
    )


def _build_hvac_duct_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacDuct",
        display_name="HVAC Duct",
        fds_namelist="DUCT",
        category="HVAC",
        description="Duct segment connecting two HVAC nodes.",
        properties=[
            _p("name",      "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("node_id_1", "Node 1",      FT.ENTITY_REF, required=True, fds_param="NODE_ID", ref_type="HvacNode"),
            _p("node_id_2", "Node 2",      FT.ENTITY_REF, required=True, fds_param="NODE_ID", ref_type="HvacNode"),
            _p("diameter",  "Diameter",    FT.FLOAT, "m", min_val=0.001, fds_param="DIAMETER"),
            _p("length",    "Length",      FT.FLOAT, "m", min_val=0.0, fds_param="LENGTH"),
            _p("roughness", "Roughness",   FT.FLOAT, "m", min_val=0.0, fds_param="ROUGHNESS"),
        ],
    )


def _build_slice_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Slice",
        display_name="Slice File",
        fds_namelist="SLCF",
        category="Output",
        description="Planar output file recording a field quantity at each time step.",
        properties=[
            _p("name",         "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("quantity",     "Quantity",    FT.STRING, required=True, fds_param="QUANTITY"),
            _p("plane",        "Plane",       FT.ENUM, required=True, fds_param="PBX/PBY/PBZ",
               enum_values=["X", "Y", "Z"]),
            _p("position",     "Position",    FT.FLOAT, "m", required=True, fds_param="PBX"),
            _p("quantity2",    "Quantity 2",  FT.STRING, fds_param="QUANTITY2", advanced=True),
            _p("vector",       "Vector",      FT.BOOL, fds_param="VECTOR"),
            _p("cell_centered","Cell-centred",FT.BOOL, fds_param="CELL_CENTERED", advanced=True),
        ],
    )


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

_registry_instance: Optional[SchemaRegistry] = None
_registry_lock = threading.Lock()


def get_schema_registry() -> SchemaRegistry:
    """Return (or lazily create and populate) the process-wide schema registry."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = _build_default_registry()
    return _registry_instance


def _build_wind_profile_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="WindProfile",
        display_name="Wind Profile",
        fds_namelist="WIND",
        category="Atmosphere",
        description="Atmospheric boundary layer wind profile for outdoor fire modelling.",
        properties=[
            _p("name",      "ID",        FT.STRING, required=True, fds_param="ID"),
            _p("speed",     "Speed",     FT.FLOAT, "m/s", min_val=0.0, fds_param="SPEED"),
            _p("direction", "Direction", FT.FLOAT, "°", min_val=0.0, max_val=360.0, fds_param="DIRECTION",
               desc="Wind direction in degrees from North (270 = westerly)."),
            _p("z_ref",     "Ref Height",FT.FLOAT, "m", min_val=0.001, fds_param="Z_REF"),
            _p("z0",        "Roughness Length", FT.FLOAT, "m", min_val=0.0, fds_param="Z0", advanced=True),
            _p("l",         "Obukhov Length",   FT.FLOAT, "m", fds_param="L", advanced=True),
            _p("ustar",     "Friction Velocity", FT.FLOAT, "m/s", min_val=0.0, fds_param="USTAR", advanced=True),
            _p("latitude",  "Latitude",  FT.FLOAT, "°", fds_param="LATITUDE", advanced=True),
            _p("l_inf",     "Mixing Height", FT.FLOAT, "m", min_val=0.0, fds_param="L_INF", advanced=True),
            _p("ramp_id",   "Speed Ramp",    FT.ENTITY_REF, fds_param="RAMP_ID", ref_type="Ramp"),
        ],
    )


def _build_move_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="Move",
        display_name="Rigid Body Motion",
        fds_namelist="MOVE",
        category="Geometry",
        description="Applies rigid-body translation or rotation to a GEOM or OBST entity.",
        properties=[
            _p("name",           "ID",            FT.STRING, required=True, fds_param="ID"),
            _p("omega",          "Angular Velocity", FT.FLOAT, "rad/s", fds_param="OMEGA"),
            _p("rotation_angle", "Rotation Angle",   FT.FLOAT, "°", fds_param="ROTATION_ANGLE"),
            _p("dx",  "ΔX", FT.FLOAT, "m", fds_param="DX"),
            _p("dy",  "ΔY", FT.FLOAT, "m", fds_param="DY"),
            _p("dz",  "ΔZ", FT.FLOAT, "m", fds_param="DZ"),
            _p("scale", "Scale", FT.FLOAT, min_val=0.001, fds_param="SCALE"),
            _p("x0", "Origin X", FT.FLOAT, "m", fds_param="X0", advanced=True),
            _p("y0", "Origin Y", FT.FLOAT, "m", fds_param="Y0", advanced=True),
            _p("z0", "Origin Z", FT.FLOAT, "m", fds_param="Z0", advanced=True),
        ],
    )


def _build_hvac_filter_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacFilter",
        display_name="HVAC Filter",
        fds_namelist="FILTER",
        category="HVAC",
        description="Particulate filter in an HVAC duct network.",
        properties=[
            _p("name",       "ID",         FT.STRING, required=True, fds_param="ID"),
            _p("duct_id",    "Duct",       FT.ENTITY_REF, required=True, fds_param="DUCT_ID", ref_type="HvacDuct"),
            _p("efficiency", "Efficiency", FT.FLOAT, min_val=0.0, max_val=1.0, fds_param="EFFICIENCY"),
            _p("loss",       "Loss",       FT.FLOAT, min_val=0.0, fds_param="LOSS"),
            _p("clean_loss", "Clean Loss", FT.FLOAT, min_val=0.0, fds_param="CLEAN_LOSS", advanced=True),
            _p("ctrl_id",    "Control",    FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control"),
        ],
    )


def _build_hvac_leakage_schema() -> EntitySchema:
    return EntitySchema(
        entity_class_name="HvacLeakage",
        display_name="Duct Leakage",
        fds_namelist="LEAK",
        category="HVAC",
        description="Leakage path between two pressure zones.",
        properties=[
            _p("name",      "ID",          FT.STRING, required=True, fds_param="ID"),
            _p("zone_id_1", "Zone 1",      FT.ENTITY_REF, required=True, fds_param="ZONE_ID(1)", ref_type="Zone"),
            _p("zone_id_2", "Zone 2",      FT.ENTITY_REF, required=True, fds_param="ZONE_ID(2)", ref_type="Zone"),
            _p("area",      "Leakage Area",FT.FLOAT, "m²", min_val=0.0, fds_param="AREA"),
            _p("crack_id",  "Crack ID",    FT.STRING, fds_param="CRACK_ID", advanced=True),
            _p("ctrl_id",   "Control",     FT.ENTITY_REF, fds_param="CTRL_ID", ref_type="Control"),
        ],
    )


def _build_default_registry() -> SchemaRegistry:
    reg = SchemaRegistry()
    for builder in [
        _build_mesh_schema,
        _build_obstruction_schema,
        _build_surface_schema,
        _build_vent_schema,
        _build_device_schema,
        _build_material_schema,
        _build_reaction_schema,
        _build_ramp_schema,
        _build_mesh_transform_schema,
        _build_geom_schema,
        _build_control_schema,
        _build_hvac_node_schema,
        _build_hvac_duct_schema,
        _build_slice_schema,
        # Gap-fill additions
        _build_wind_profile_schema,
        _build_move_schema,
        _build_hvac_filter_schema,
        _build_hvac_leakage_schema,
    ]:
        reg.register(builder())
    return reg
