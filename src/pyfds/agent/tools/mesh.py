"""Mesh operations: refine, split, merge, transforms, refinement zones, stretching, open boundaries (B1)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NAME = {"type": "string"}
_AXIS = {"type": "string", "enum": ["X", "Y", "Z"]}
_XB = {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6,
       "description": "[x_min, x_max, y_min, y_max, z_min, z_max]."}


def _mesh_tool(name, description, props, required, handler):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": {"mesh": _NAME, **props},
                                  "required": ["mesh", *required]},
                    handler=handler)


TOOLS: List[ToolSpec] = [
    _mesh_tool("refine_mesh", "Divide every cell of a mesh by FACTOR in each direction (2 = one cell becomes eight).",
               {"factor": {"type": "integer", "default": 2}}, [],
               lambda api, mesh, factor=2: api.meshes.refine(mesh, factor)),
    _mesh_tool("split_mesh", "Cut a mesh in two on a plane perpendicular to AXIS (snapped to a cell boundary; default middle). Returns the new mesh.",
               {"axis": _AXIS, "at": {"type": "number"}, "new_name": _NAME}, ["axis"],
               lambda api, mesh, axis, at=None, new_name=None: api.meshes.split(mesh, axis, at, new_name)),
    ToolSpec(
        name="merge_meshes",
        description="Merge meshes that exactly tile one box and share a cell size into the first one.",
        input_schema={"type": "object", "properties": {
            "meshes": {"type": "array", "items": _NAME, "minItems": 2}, "new_name": _NAME},
            "required": ["meshes"]},
        handler=lambda api, meshes, new_name=None: api.meshes.merge(meshes, new_name),
    ),
    _mesh_tool("move_mesh", "Translate a mesh by dx, dy, dz.",
               {"dx": {"type": "number"}, "dy": {"type": "number"}, "dz": {"type": "number"}}, [],
               lambda api, mesh, dx=0.0, dy=0.0, dz=0.0: api.meshes.move(mesh, dx, dy, dz)),
    _mesh_tool("scale_mesh", "Scale a mesh about an origin (cell count kept, so cell size scales).",
               {"factor": {"type": "number"}, "origin": {"type": "array", "items": {"type": "number"},
                                                         "minItems": 3, "maxItems": 3}}, ["factor"],
               lambda api, mesh, factor, origin=(0.0, 0.0, 0.0): api.meshes.scale(mesh, factor, origin)),
    _mesh_tool("mirror_mesh", "Mirror a mesh across the plane AXIS = AT (copy=true adds the mirrored mesh).",
               {"axis": _AXIS, "at": {"type": "number"}, "copy": {"type": "boolean"}, "new_name": _NAME},
               ["axis", "at"],
               lambda api, mesh, axis, at, copy=False, new_name=None: api.meshes.mirror(mesh, axis, at, copy, new_name)),
    _mesh_tool("rotate_mesh", "Rotate a mesh about the vertical axis by a multiple of 90 degrees.",
               {"angle": {"type": "number"}, "origin": {"type": "array", "items": {"type": "number"},
                                                         "minItems": 2, "maxItems": 2},
                "copy": {"type": "boolean"}, "new_name": _NAME}, ["angle"],
               lambda api, mesh, angle, origin=(0.0, 0.0), copy=False, new_name=None:
                   api.meshes.rotate(mesh, angle, origin, copy, new_name)),
    _mesh_tool("apply_mesh_refinement", "Refine only a box of a mesh: it is cut into a refined sub-mesh plus coarse neighbours.",
               {"xb": _XB, "factor": {"type": "integer", "default": 2}}, ["xb"],
               lambda api, mesh, xb, factor=2: api.meshes.apply_refinement(mesh, xb, factor)),
    _mesh_tool("set_mesh_stretching", "Set non-uniform cell spacing on one axis from control points [[coordinate, fraction 0..1], ...]; [] restores uniform.",
               {"axis": _AXIS, "points": {"type": "array", "items": {"type": "array", "items": {"type": "number"},
                                                                       "minItems": 2, "maxItems": 2}}},
               ["axis", "points"],
               lambda api, mesh, axis, points: api.meshes.set_stretching(mesh, axis, [tuple(p) for p in points])),
    ToolSpec(
        name="open_mesh_boundaries",
        description="Add an OPEN vent on every mesh face not shared with another mesh (idempotent).",
        input_schema={"type": "object", "properties": {
            "surf_id": {"type": "string", "default": "OPEN"},
            "meshes": {"type": "array", "items": _NAME, "description": "Limit to these meshes."}}},
        handler=lambda api, surf_id="OPEN", meshes=None: api.meshes.open_boundaries(surf_id, meshes),
    ),
    ToolSpec(
        name="mesh_stats",
        description="Cell size, aspect ratio, cell counts and stretching per mesh, plus project totals.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: {"project": api.meshes.project_stats(),
                             "meshes": {m.name: api.meshes.stats(m) for m in api.meshes.all()}},
        mutates=False,
    ),
]
