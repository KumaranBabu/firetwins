"""Init regions, particle clouds/classes and profile tools."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_quantities
from .base import ToolSpec, _remove_from


TOOLS: List[ToolSpec] = [

    # ── Init regions / particle clouds / particle classes / profiles ───────
    ToolSpec(
        name="add_init",
        description=(
            "Add an initial-conditions region (&INIT) — sets starting temperature/species in a "
            "volume, or (set part_id + n_particles) a volumetric particle cloud pre-filled at t=0."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."},
                "temperature": {"type": "number", "description": "Initial temperature, C."},
                "part_id": {"type": "string", "description": "Particle class (from add_particle_class) for a particle cloud."},
                "n_particles": {"type": "integer", "description": "Number of particles to seed for a particle cloud."},
                "name": {"type": "string"},
            },
            "required": ["xb"],
        },
        handler=lambda api, xb, temperature=None, part_id=None, n_particles=None, name=None: api.inits.add_init(
            xb=xb,
            **({"temperature": temperature} if temperature is not None else {}),
            **({"part_id": part_id} if part_id else {}),
            **({"n_particles": n_particles} if n_particles is not None else {}),
            **({"name": name} if name else {}),
        ),
    ),
    ToolSpec(
        name="list_inits",
        description="List all initial-conditions regions (including particle clouds) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.inits.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_init",
        description="Remove an initial-conditions region by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.inits, name),
    ),
    ToolSpec(
        name="add_particle_class",
        description="Add a Lagrangian particle class (&PART) — reference its name from add_init's part_id (a particle cloud) or a device's prop_id.",
        input_schema={
            "type": "object",
            "properties": {
                "diameter": {"type": "number", "default": 500.0, "description": "Particle diameter, microns."},
                "name": {"type": "string"},
            },
            "required": [],
        },
        handler=lambda api, diameter=500.0, name=None: api.particles.add_particle_class(
            diameter=diameter, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_particle_classes",
        description="List all particle classes in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.particles.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_particle_class",
        description="Remove a particle class by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.particles, name),
    ),
    ToolSpec(
        name="add_profile",
        description="Add an in-depth/vertical profile output request (&PROF) at a point.",
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("PROF")},
                "xyz": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "name": {"type": "string"},
            },
            "required": ["quantity", "xyz"],
        },
        handler=lambda api, quantity, xyz, name=None: api.profs.add_profile(
            quantity=quantity, xyz=xyz, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_profiles",
        description="List all profile output requests in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.profs.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_profile",
        description="Remove a profile output request by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.profs, name),
    ),
]
