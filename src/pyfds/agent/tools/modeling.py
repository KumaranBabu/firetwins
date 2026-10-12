"""Mesh, obstruction, vent, hole and surface tools."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_surface_presets
from .base import ToolSpec, _remove_from


TOOLS: List[ToolSpec] = [

    # ── Meshes ───────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_mesh",
        description="Add an FDS computational mesh (MESH namelist).",
        input_schema={
            "type": "object",
            "properties": {
                "ijk": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3,
                        "description": "Cell counts [nx, ny, nz]."},
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."},
                "name": {"type": "string"},
            },
            "required": ["ijk", "xb"],
        },
        handler=lambda api, ijk, xb, name=None: api.meshes.add_mesh(ijk=ijk, xb=xb, **({"name": name} if name else {})),
    ),
    ToolSpec(
        name="list_meshes",
        description="List all meshes in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.meshes.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_mesh",
        description="Remove a mesh by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.meshes, name),
    ),

    # ── Obstructions ─────────────────────────────────────────────────────────
    ToolSpec(
        name="add_obstruction",
        description="Add a solid obstruction (wall, block, fuel package) to the project.",
        input_schema={
            "type": "object",
            "properties": {
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."},
                "surf_id": {"type": "string", "description": "Name of an existing SURF, default INERT."},
                "name": {"type": "string"},
            },
            "required": ["xb"],
        },
        handler=lambda api, xb, surf_id="INERT", name=None: api.obstructions.add_obstruction(
            xb=xb, surf_id=surf_id, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="move_obstruction",
        description="Translate an existing obstruction by (dx, dy, dz), undo-able.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "dx": {"type": "number", "default": 0},
                "dy": {"type": "number", "default": 0},
                "dz": {"type": "number", "default": 0},
            },
            "required": ["name"],
        },
        handler=lambda api, name, dx=0, dy=0, dz=0: api.obstructions.move(name, dx=dx, dy=dy, dz=dz),
    ),
    ToolSpec(
        name="list_obstructions",
        description="List all obstructions in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.obstructions.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_obstruction",
        description="Remove an obstruction by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.obstructions, name),
    ),

    # ── Vents ────────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_vent",
        description="Add a vent (supply/exhaust/open/mirror boundary patch) to the project.",
        input_schema={
            "type": "object",
            "properties": {
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."},
                "surf_id": {"type": "string", "description": "Name of an existing SURF, or OPEN/MIRROR. Default OPEN."},
                "name": {"type": "string"},
            },
            "required": ["xb"],
        },
        handler=lambda api, xb, surf_id="OPEN", name=None: api.vents.add_vent(
            xb=xb, surf_id=surf_id, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_vents",
        description="List all vents in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.vents.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_vent",
        description="Remove a vent by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.vents, name),
    ),

    # ── Holes ────────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_hole",
        description="Cut a rectangular opening through obstructions in the project.",
        input_schema={
            "type": "object",
            "properties": {
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."},
                "name": {"type": "string"},
            },
            "required": ["xb"],
        },
        handler=lambda api, xb, name=None: api.holes.add_hole(
            xb=xb, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_holes",
        description="List all holes in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.holes.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_hole",
        description="Remove a hole by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.holes, name),
    ),

    # ── Surfaces ─────────────────────────────────────────────────────────────
    ToolSpec(
        name="add_burner",
        description="Add a fire-source SURF with a specified heat release rate per unit area.",
        input_schema={
            "type": "object",
            "properties": {
                "hrrpua": {"type": "number", "description": "Heat release rate per unit area, kW/m2."},
                "tau_q": {"type": "number", "default": 1.0, "description": "Ramp-up time constant, s."},
                "name": {"type": "string"},
            },
            "required": ["hrrpua"],
        },
        handler=lambda api, hrrpua, tau_q=1.0, name=None: api.surfaces.add_burner(
            hrrpua=hrrpua, tau_q=tau_q, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_surfaces",
        description="List all surfaces (SURF) in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.surfaces.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_surface",
        description="Remove a surface by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.surfaces, name),
    ),
    ToolSpec(
        name="add_surface_from_library",
        description="Add a multi-layer SURF assembly (with its Layer list) from the built-in preset library.",
        input_schema={
            "type": "object",
            "properties": {"preset_name": {"type": "string", "enum": list_surface_presets()}},
            "required": ["preset_name"],
        },
        handler=lambda api, preset_name: api.surfaces.add_from_library(preset_name),
    ),
]
