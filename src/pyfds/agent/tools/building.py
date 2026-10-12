"""Building generators, boolean operations, block conversion, particle clouds (B2)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_PT = {"type": "array", "items": _NUM, "minItems": 2, "maxItems": 3}
_PATH = {"type": "array", "items": _PT, "minItems": 2, "description": "[[x, y], ...]"}
_XB4 = {"type": "array", "items": _NUM, "minItems": 4, "description": "[x_min, x_max, y_min, y_max]"}
_XB6 = {"type": "array", "items": _NUM, "minItems": 6, "maxItems": 6,
        "description": "[x_min, x_max, y_min, y_max, z_min, z_max]"}
_COMMON = {"surf_id": _STR, "name": _STR, "res": {**_NUM, "description": "stair-step size; default = smallest cell of the first mesh"},
           "color": _STR}


def _ids(items):
    return [o.name for o in items]


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _room(api, **kw):
    r = api.geom.add_room(**kw)
    return {"walls": _ids(r["walls"]), "holes": _ids(r["holes"]), "interior": r["interior"]}


TOOLS: List[ToolSpec] = [
    _spec("add_wall", "Wall along a polyline with thickness and height (align L/C/R of the path). Diagonal runs are stair-stepped.",
          {"path": _PATH, "thickness": _NUM, "height": _NUM, "z": _NUM, "align": {"type": "string", "enum": ["L", "C", "R"]},
           "closed": {"type": "boolean"}, **_COMMON}, ["path", "thickness", "height"],
          lambda api, **kw: _ids(api.geom.add_wall(**kw))),
    _spec("add_curved_wall", "Wall along a circular arc (degrees, counter-clockwise from +X; 360 = ring).",
          {"center": _PT, "radius": _NUM, "start_deg": _NUM, "end_deg": _NUM, "thickness": _NUM, "height": _NUM,
           "z": _NUM, "align": {"type": "string", "enum": ["L", "C", "R"]}, **_COMMON},
          ["center", "radius", "start_deg", "end_deg", "thickness", "height"],
          lambda api, **kw: _ids(api.geom.add_curved_wall(**kw))),
    _spec("add_slab", "Floor/ceiling slab: polygon extruded down from z_top by thickness.",
          {"polygon": _PATH, "z_top": _NUM, "thickness": _NUM, **_COMMON}, ["polygon", "z_top", "thickness"],
          lambda api, **kw: _ids(api.geom.add_slab(**kw))),
    _spec("add_room", "Four walls round a rectangle with optional floor, ceiling and door/window openings (holes).",
          {"xb": _XB4, "height": _NUM, "wall_thickness": _NUM, "z": _NUM,
           "position": {"type": "string", "enum": ["inside", "centre", "outside"]},
           "floor_thickness": _NUM, "ceiling_thickness": _NUM,
           "openings": {"type": "array", "items": {"type": "object", "properties": {
               "side": {"type": "string", "enum": ["S", "E", "N", "W"]}, "centre": _NUM, "width": _NUM,
               "height": _NUM, "sill": _NUM}, "required": ["side", "centre", "width", "height"]}},
           "surf_id": _STR, "name": _STR, "color": _STR}, ["xb", "height"],
          _room),
    _spec("add_stairs", "Straight flight of solid steps climbing from (x, y) towards +X, -X, +Y or -Y.",
          {"x": _NUM, "y": _NUM, "z": _NUM, "direction": {"type": "string", "enum": ["+X", "-X", "+Y", "-Y"]},
           "width": _NUM, "steps": {"type": "integer"}, "riser": _NUM, "tread": _NUM, "landing": _NUM,
           "surf_id": _STR, "name": _STR, "color": _STR}, ["x", "y", "z", "direction", "width", "steps"],
          lambda api, **kw: _ids(api.geom.add_stairs(**kw))),
    _spec("add_roof", "Pitched roof (gable or shed) over a rectangle, built as stepped strips.",
          {"xb": _XB4, "z_eave": _NUM, "pitch_deg": _NUM, "thickness": _NUM,
           "kind": {"type": "string", "enum": ["gable", "shed"]}, "ridge_axis": {"type": "string", "enum": ["X", "Y"]},
           "overhang": _NUM, **_COMMON}, ["xb", "z_eave", "pitch_deg"],
          lambda api, **kw: _ids(api.geom.add_roof(**kw))),
    _spec("add_truss", "Planar Warren truss (flat bottom chord, peaked top chord, zig-zag web).",
          {"x": _NUM, "y": _NUM, "z": _NUM, "span": _NUM, "rise": _NUM, "panels": {"type": "integer"},
           "member": _NUM, "depth": _NUM, "along": {"type": "string", "enum": ["X", "Y"]}, **_COMMON},
          ["x", "y", "z", "span", "rise"],
          lambda api, **kw: _ids(api.geom.add_truss(**kw))),
    _spec("geometry_boolean", "Union / difference (a minus b) / intersection of two closed GEOM surfaces.",
          {"op": {"type": "string", "enum": ["union", "difference", "intersection"]}, "a": _STR, "b": _STR,
           "name": _STR, "remove_inputs": {"type": "boolean"}}, ["op", "a", "b"],
          lambda api, **kw: api.geom.boolean(**kw).name),
    _spec("preview_blocks", "Show the grid-aligned obstructions a GEOM would become, without changing the project.",
          {"geom": _STR, "mesh": _STR, "mode": {"type": "string", "enum": ["surface", "solid"]}}, ["geom"],
          lambda api, geom, mesh=None, mode="surface": api.geom.preview_blocks(
              geom, api.meshes.get(mesh) if mesh else None, mode), mutates=False),
    _spec("convert_to_blocks", "Replace a GEOM with grid-aligned obstructions (FDS stair-step blocks).",
          {"geom": _STR, "mesh": _STR, "mode": {"type": "string", "enum": ["surface", "solid"]},
           "surf_id": _STR, "remove_geom": {"type": "boolean"}}, ["geom"],
          lambda api, geom, mesh=None, **kw: _ids(api.geom.convert_to_blocks(
              geom, api.meshes.get(mesh) if mesh else None, **kw))),
    _spec("add_particle_cloud", "Particle cloud: an INIT box releasing PART_ID particles (a count or a number per unit area).",
          {"xb": _XB6, "part_id": _STR, "n_particles": {"type": "integer"}, "n_particles_pua": _NUM, "name": _STR},
          ["xb", "part_id"],
          lambda api, **kw: api.inits.add_particle_cloud(**kw).name),
]
