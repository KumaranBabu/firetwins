"""Clipboard, visibility, snapping and FDS number format (UX-03, UX-04, UX-08, FIO-01)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_OBJECTS = {"type": "array", "minItems": 1, "items": {
    "type": "object", "properties": {"collection": {**_STR, "description": "e.g. obstructions, vents, devices"},
                                     "name": _STR}, "required": ["collection", "name"]}}
_PT3 = {"type": "array", "items": _NUM, "minItems": 3, "maxItems": 3}


def _find(api, objects):
    out = []
    for o in objects:
        coll = getattr(api.project, o["collection"], None)
        if not isinstance(coll, list):
            raise KeyError(f"unknown collection {o['collection']!r}")
        hit = next((e for e in coll if e.name == o["name"]), None)
        if hit is None:
            raise KeyError(f"{o['collection']} has no {o['name']!r}")
        out.append(hit)
    return out


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _paste(api, text, offset=(0.0, 0.0, 0.0)):
    r = api.clipboard.paste_fds_text(text, offset)
    return {"added": [e.name for e in r["added"]], "renamed": r["renamed"], "skipped": r["skipped"]}


TOOLS: List[ToolSpec] = [
    _spec("copy_objects_as_fds", "Copy objects to the clipboard and return them as FDS text.",
          {"objects": _OBJECTS, "include_dependencies": {"type": "boolean"}}, ["objects"],
          lambda api, objects, include_dependencies=False:
              api.clipboard.copy(_find(api, objects), include_dependencies), mutates=False),
    _spec("paste_fds_text", "Add the objects in FDS text to the model, moved by an optional offset (one undo step).",
          {"text": _STR, "offset": _PT3}, ["text"], _paste),
    _spec("paste_clipboard", "Paste the clipboard, moved by an optional offset.", {"offset": _PT3}, [],
          lambda api, offset=(0.0, 0.0, 0.0): _paste(api, api.clipboard.text, offset)),
    _spec("hide_objects", "Hide objects in the views.", {"objects": _OBJECTS}, ["objects"],
          lambda api, objects: api.view.hide(_find(api, objects))),
    _spec("show_objects", "Show hidden objects.", {"objects": _OBJECTS}, ["objects"],
          lambda api, objects: api.view.show(_find(api, objects))),
    _spec("isolate_objects", "Hide everything except these objects.", {"objects": _OBJECTS}, ["objects"],
          lambda api, objects: api.view.isolate(_find(api, objects))),
    _spec("filter_objects", "Show only objects matching all criteria; hide the rest.",
          {"collection": _STR, "name_contains": _STR, "tag": _STR, "surface": _STR}, [],
          lambda api, **kw: api.view.filter(**kw)),
    _spec("show_all_objects", "Show every object and every type.", {}, [], lambda api: api.view.show_all()),
    _spec("set_type_visible", "Switch a whole type of object on or off in the views.",
          {"collection": _STR, "visible": {"type": "boolean"}}, ["collection", "visible"],
          lambda api, collection, visible: api.view.set_type_visible(collection, visible)),
    _spec("snap_point", "Where would the cursor point land with the current snap settings?",
          {"point": _PT3, "anchor": _PT3, "ortho": {"type": "boolean"}, "polar_step_deg": _NUM,
           "tolerance": _NUM, "grid_size": _NUM, "enabled": {"type": "boolean"}}, ["point"],
          lambda api, point, anchor=None, enabled=None, **kw: vars(api.snapping.snap(point, anchor, enabled=enabled, **kw)),
          mutates=False),
    _spec("set_fds_number_format", "How numbers are written into the FDS file: significant digits (1-15 or none) "
          "and style auto / decimal / scientific.",
          {"significant_digits": {"type": "integer"}, "style": {"type": "string", "enum": ["auto", "decimal", "scientific"]}}, [],
          lambda api, significant_digits=None, style="auto": api.fds_format.set_number_format(significant_digits, style)),
]


def _names(result):
    """One name for a single shape, a list of names when a file (IFC) held several."""
    return [g.name for g in result] if isinstance(result, (list, tuple)) else result.name


# -- imports and slice images (IMP-02, RES-04) ------------------------------------------------------
TOOLS.extend([
    _spec("import_geometry_file", "Import a CAD/BIM file (STL, OBJ, DXF 3DFACE, glTF/GLB, DAE, IFC) as GEOM(s); an IFC gives one per "
          "element. units: m, mm, cm, in, ft; up_axis Y for Y-up files. Returns the shape name (a list for an IFC).",
          {"path": _STR, "units": _STR, "up_axis": {"type": "string", "enum": ["Y", "Z"]}, "surf_id": _STR,
           "name": _STR, "scale": _NUM, "translate": _PT3}, ["path"],
          lambda api, path, **kw: _names(api.geom.import_file(path, **kw))),
    _spec("render_slice_image", "Render one frame of a slice file (.sf) to a PNG with a colour bar.",
          {"slice_file": _STR, "filepath": _STR, "frame": {"type": "integer"}, "mesh": _STR, "colormap": _STR,
           "vmin": _NUM, "vmax": _NUM, "levels": {"type": "integer"}, "colorbar": {"type": "boolean"},
           "bounds_from": {"type": "string", "enum": ["all", "frame"]}}, ["slice_file", "filepath"],
          lambda api, slice_file, filepath, frame=-1, mesh=None, **kw:
              api.slice_view.render(slice_file, filepath, frame, mesh, **kw), mutates=False),
])
