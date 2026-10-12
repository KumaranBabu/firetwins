"""PyFDS Domain Layer — FDS entity models, geometry helpers, material library, presets."""
from .model import (
    FdsProject,
    SimulationParams, DumpParams, MiscParams, PresParams, RadiParams,
    FdsEntity,
    Mesh, Obstruction, Hole, Mult, Surface, Vent, Device,
    Material, Reaction, Layer, Ramp, Slice, BoundaryFile, IsoSurface,
    Particle, Prop, Control, Species, Init, Hvac, HvacNode, HvacDuct,
    Fan, Damper, Text, Zone, Prof,
)
from .geometry import BoundingBox, GeometryHelper
from .materials import MaterialLibrary, MaterialPreset, MATERIAL_LIBRARY
from .presets import PresetEngine, ScenarioTemplate, list_presets, apply_preset
from .quantities import (
    FdsQuantity, QUANTITY_DB,
    list_quantities, get_quantity, quantities_for_context, validate_quantity,
)
from .material_presets import (
    MATERIAL_PRESETS, SURFACE_PRESETS,
    list_material_presets, list_surface_presets,
    get_material_preset, get_surface_preset,
    make_material as make_material_preset,
    make_surface as make_surface_preset,
)
from .reactions import FUEL_LIBRARY, list_fuels, get_fuel, make_reaction

__all__ = [
    "FdsProject",
    "SimulationParams", "DumpParams", "MiscParams", "PresParams", "RadiParams",
    "FdsEntity",
    "Mesh", "Obstruction", "Hole", "Mult", "Surface", "Vent", "Device",
    "Material", "Reaction", "Layer", "Ramp", "Slice", "BoundaryFile", "IsoSurface",
    "Particle", "Prop", "Control", "Species", "Init", "Hvac", "HvacNode", "HvacDuct",
    "Fan", "Damper", "Text", "Zone", "Prof",
    "BoundingBox", "GeometryHelper",
    "MaterialLibrary", "MaterialPreset", "MATERIAL_LIBRARY",
    "PresetEngine", "ScenarioTemplate", "list_presets", "apply_preset",
    # Quantity library
    "FdsQuantity", "QUANTITY_DB",
    "list_quantities", "get_quantity", "quantities_for_context", "validate_quantity",
    # Material presets
    "MATERIAL_PRESETS", "SURFACE_PRESETS",
    "list_material_presets", "list_surface_presets",
    "get_material_preset", "get_surface_preset",
    "make_material_preset", "make_surface_preset",
    # Reaction library
    "FUEL_LIBRARY", "list_fuels", "get_fuel", "make_reaction",
]
