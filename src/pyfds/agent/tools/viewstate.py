"""Saved views, section box, selection/view history, find/replace and measuring (B7)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_PT = {"type": "array", "items": _NUM, "minItems": 3, "maxItems": 3}
_PTS = {"type": "array", "items": _PT}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _matches(ms):
    return [{"kind": m.collection, "name": getattr(m.entity, "name", ""), "field": m.field, "value": m.value} for m in ms]


def _box(api):
    b = api.views.section_box()
    return b.to_dict() if b else None


_FIND = {"text": _STR, "fields": {"type": "array", "items": {"type": "string", "enum": ["name", "tags", "description"]}},
         "kinds": {"type": "array", "items": _STR, "description": "Collection names, e.g. obstructions, surfaces."},
         "regex": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}, "whole_word": {"type": "boolean"}}

TOOLS: List[ToolSpec] = [
    _spec("save_view", "Save the current camera, section box and hidden types as a named view.",
          {"name": _STR, "description": _STR}, ["name"],
          lambda api, name, description="": api.views.save_viewpoint(name, description).name),
    _spec("go_to_view", "Apply a saved view (camera, section box, hidden types).", {"name": _STR}, ["name"],
          lambda api, name: api.views.reset_to(name).name),
    _spec("list_views", "Saved views and which one is active.", {}, [],
          lambda api: {"views": [v.name for v in api.views.all()], "active": api.views.active}, mutates=False),
    _spec("delete_view", "Delete a saved view.", {"name": _STR}, ["name"], lambda api, name: api.views.delete(name)),
    _spec("set_section_box", "Set the six-sided clipping box (metres); leave a side out to keep it open.",
          {k: _NUM for k in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")}, [],
          lambda api, **kw: api.views.set_section_box(**kw).to_dict()),
    _spec("fit_section_box", "Section box around the named objects, grown by a margin (m).",
          {"names": {"type": "array", "items": _STR}, "margin": _NUM}, ["names"],
          lambda api, names, margin=0.0: api.views.fit_section_box(
              [api.measure._resolve(n) for n in names], margin).to_dict()),
    _spec("reset_section_box", "Remove the section box.", {}, [], lambda api: api.views.reset_section_box()),
    _spec("get_section_box", "The current section box, or null.", {}, [], lambda api: _box(api), mutates=False),
    _spec("undo_selection_view", "Step back one selection/view change (the model's own undo is separate).", {}, [],
          lambda api: api.ui_history.undo()),
    _spec("redo_selection_view", "Redo one selection/view change.", {}, [], lambda api: api.ui_history.redo()),
    _spec("find_objects", "Find objects whose name, tags or description match text; optionally select them.",
          {**_FIND, "select": {"type": "boolean"}}, ["text"],
          lambda api, text, **kw: _matches(api.find.find(text, **kw)), mutates=False),
    _spec("replace_text", "Replace text in names, tags and/or descriptions as one undo step. Renaming a referenced "
          "object needs update_references. dry_run previews.",
          {**_FIND, "replacement": _STR, "update_references": {"type": "boolean"}, "dry_run": {"type": "boolean"}},
          ["text", "replacement"],
          lambda api, text, replacement, **kw: api.find.replace(text, replacement, **kw)),
    _spec("measure_distance", "Distance between two points with dx, dy, dz and the horizontal part.",
          {"p": _PT, "q": _PT}, ["p", "q"], lambda api, p, q: api.measure.distance(p, q), mutates=False),
    _spec("measure_angle", "Angle in degrees at the vertex between two points.", {"a": _PT, "vertex": _PT, "c": _PT},
          ["a", "vertex", "c"], lambda api, a, vertex, c: api.measure.angle(a, vertex, c), mutates=False),
    _spec("measure_path", "Length of a polyline.", {"points": _PTS}, ["points"],
          lambda api, points: api.measure.path_length(points), mutates=False),
    _spec("measure_area", "Area of a planar polygon.", {"points": _PTS}, ["points"],
          lambda api, points: api.measure.area(points), mutates=False),
    _spec("measure_between", "Gap and centre distance between two named objects with positions.",
          {"a": _STR, "b": _STR}, ["a", "b"], lambda api, a, b: api.measure.between(a, b), mutates=False),
]
