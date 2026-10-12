"""Output-request tools (SLCF / BNDF / ISOF / PL3D)."""
from __future__ import annotations

from typing import List

from pyfds.api.catalog import list_quantities
from .base import ToolSpec, _remove_from


TOOLS: List[ToolSpec] = [

    # ── Output requests (SLCF/BNDF/ISOF/PL3D) ───────────────────────────────
    ToolSpec(
        name="add_slice",
        description="Add a slice-file output request (&SLCF) — a 2D plane, or a 3D volume if xb is given.",
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("SLCF")},
                "plane": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"},
                "position": {"type": "number", "default": 0.0},
                "xb": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
                       "description": "Optional: makes this a 3D volumetric slice instead of a 2D plane."},
                "name": {"type": "string"},
            },
            "required": ["quantity"],
        },
        handler=lambda api, quantity, plane="X", position=0.0, xb=None, name=None: api.slices.add_slice(
            quantity=quantity, plane=plane, position=position,
            **({"xb": xb} if xb else {}), **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_slices",
        description="List all slice-file output requests in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.slices.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_slice",
        description="Remove a slice-file output request by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.slices, name),
    ),
    ToolSpec(
        name="add_boundary_file",
        description="Add a boundary-quantity output request (&BNDF), e.g. wall temperature or heat flux.",
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("BNDF")},
                "name": {"type": "string"},
            },
            "required": ["quantity"],
        },
        handler=lambda api, quantity, name=None: api.bndfs.add_boundary_file(
            quantity=quantity, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_boundary_files",
        description="List all boundary-quantity output requests in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.bndfs.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_boundary_file",
        description="Remove a boundary-quantity output request by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.bndfs, name),
    ),
    ToolSpec(
        name="add_isosurface",
        description="Add an isosurface output request (&ISOF) at a fixed quantity value, e.g. a 60C temperature shell.",
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("ISOF")},
                "value": {"type": "number"},
                "name": {"type": "string"},
            },
            "required": ["quantity", "value"],
        },
        handler=lambda api, quantity, value, name=None: api.isofs.add_isosurface(
            quantity=quantity, value=value, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_isosurfaces",
        description="List all isosurface output requests in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.isofs.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_isosurface",
        description="Remove an isosurface output request by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.isofs, name),
    ),
    ToolSpec(
        name="add_plot3d",
        description="Add a Plot3D output-channel configuration (&PL3D).",
        input_schema={
            "type": "object",
            "properties": {
                "quantity": {"type": "string", "enum": list_quantities("PL3D")},
                "name": {"type": "string"},
            },
            "required": ["quantity"],
        },
        handler=lambda api, quantity, name=None: api.plot3ds.add_plot3d(
            quantity=quantity, **({"name": name} if name else {})
        ),
    ),
    ToolSpec(
        name="list_plot3ds",
        description="List all Plot3D output-channel configurations in the active project.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.plot3ds.all(),
        mutates=False,
    ),
    ToolSpec(
        name="remove_plot3d",
        description="Remove a Plot3D output-channel configuration by name.",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=lambda api, name: _remove_from(api.plot3ds, name),
    ),
]
