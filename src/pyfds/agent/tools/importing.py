"""BIM, geometry repair/export and floor-plan background tools (B3)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_STRS = {"type": "array", "items": _STR}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _bg(b):
    return {"name": b.name, "path": b.path, "kind": b.kind, "page": b.page, "x": b.x, "y": b.y, "z": b.z,
            "width": b.width, "opacity": b.opacity, "visible": b.visible, "floor": b.floor}


TOOLS: List[ToolSpec] = [
    _spec("list_bim_types", "IFC classes of the imported BIM shapes with counts.", {}, [],
          lambda api: api.geom.bim_types(), mutates=False),
    _spec("generate_model_from_bim",
          "Convert imported BIM shapes into grid-aligned obstructions on the first mesh. types: IFC classes "
          "(default all); storey; surface_map {IfcWall: SURF_ID}.",
          {"types": _STRS, "storey": _STR, "surface_map": {"type": "object", "additionalProperties": _STR},
           "default_surf": _STR, "mode": {"type": "string", "enum": ["solid", "surface"]}, "remove_geom": _BOOL}, [],
          lambda api, types=(), **kw: [o.name for o in api.geom.generate_from_bim(types=types, **kw)]),
    _spec("check_geometry", "Report degenerate/duplicate triangles, open edges and volume of a GEOM.",
          {"name": _STR}, ["name"], lambda api, name: api.geom.check_geometry(name), mutates=False),
    _spec("repair_geometry", "Weld vertices, drop bad triangles and fix the winding of a GEOM.",
          {"name": _STR, "weld_tol": _NUM, "orient": _BOOL, "outward": _BOOL}, ["name"],
          lambda api, name, **kw: api.geom.repair(name, **kw)),
    _spec("rescale_geometry", "Multiply a GEOM's size by a factor (fix a wrong-units import).",
          {"name": _STR, "factor": _NUM}, ["name", "factor"],
          lambda api, name, factor: api.geom.rescale(name, factor).name),
    _spec("export_geometry", "Write GEOMs (default all) and optionally obstructions to .stl or .obj.",
          {"path": _STR, "geoms": _STRS, "include_obstructions": _BOOL, "units": _STR,
           "up_axis": {"type": "string", "enum": ["Y", "Z"]}, "ascii_stl": _BOOL}, ["path"],
          lambda api, path, **kw: api.geom.export_geometry(path, **kw), mutates=False),
    _spec("add_background", "Place a floor-plan image or PDF page under the model. width = real width in metres.",
          {"path": _STR, "name": _STR, "width": _NUM, "x": _NUM, "y": _NUM, "z": _NUM, "page": {"type": "integer"},
           "opacity": _NUM, "floor": _STR}, ["path"],
          lambda api, path, **kw: _bg(api.backgrounds.add(path, **kw))),
    _spec("list_backgrounds", "All floor-plan backgrounds.", {}, [],
          lambda api: [_bg(b) for b in api.backgrounds.all()], mutates=False),
    _spec("update_background", "Move, resize, fade, hide a background or assign it to a floor.",
          {"name": _STR, "x": _NUM, "y": _NUM, "z": _NUM, "width": _NUM, "opacity": _NUM, "visible": _BOOL,
           "floor": _STR, "page": {"type": "integer"}}, ["name"],
          lambda api, name, **kw: _bg(api.backgrounds.update(name, **kw))),
    _spec("remove_background", "Delete a floor-plan background.", {"name": _STR}, ["name"],
          lambda api, name: api.backgrounds.remove(name)),
    _spec("trace_background", "Make wall obstructions from the dark lines of a background plan.",
          {"name": _STR, "height": _NUM, "cell": _NUM, "surf_id": _STR, "threshold": {"type": "integer"},
           "min_fill": _NUM, "max_boxes": {"type": "integer"}, "prefix": _STR}, ["name"],
          lambda api, name, **kw: [o.name for o in api.backgrounds.trace(name, **kw)]),
]
