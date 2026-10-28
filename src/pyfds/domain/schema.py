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
from typing import Optional

from .schema_types import (  # noqa: F401  (re-exported)
    EntitySchema,
    FT,
    FieldType,
    PropertyDescriptor,
    SchemaRegistry,
    _p,
)
from .schema_physics import (  # noqa: F401  (re-exported)
    _build_control_schema,
    _build_material_schema,
    _build_ramp_schema,
    _build_reaction_schema,
    _build_surface_schema,
    _build_wind_profile_schema,
)
from .schema_devices import (  # noqa: F401  (re-exported)
    _build_device_schema,
    _build_hvac_duct_schema,
    _build_hvac_filter_schema,
    _build_hvac_leakage_schema,
    _build_hvac_node_schema,
    _build_slice_schema,
)
from .schema_geometry import (  # noqa: F401  (re-exported)
    _build_geom_schema,
    _build_mesh_schema,
    _build_mesh_transform_schema,
    _build_move_schema,
    _build_obstruction_schema,
    _build_vent_schema,
)



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
