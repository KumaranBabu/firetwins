"""Results scene: layers, playback position, clip planes, probing, saved views (C2)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_PT3 = {"type": "array", "items": _NUM, "minItems": 3, "maxItems": 3}


def _spec(name, description, props, required, handler, mutates=False):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _names(layers):
    return [l.name for l in layers]


def _seek(api, time=None, progress=None, step=None):
    pb = api.scene.playback
    if time is not None:
        pb.seek_time(time)
    elif progress is not None:
        pb.seek_progress(progress)
    elif step is not None:
        pb.step(step)
    return {"index": pb.index, "time": pb.time, "frames": pb.n_frames}


TOOLS: List[ToolSpec] = [
    _spec("scene_open_results", "Index a results directory or .smv file for the in-app results scene.",
          {"source": _STR}, ["source"], lambda api, source: api.scene.open_results(source).summary()),
    _spec("scene_add_slices", "Add the indexed slice files (optionally one quantity) as scene layers.",
          {"quantity": _STR, "planar_only": {"type": "boolean"}}, [],
          lambda api, **kw: _names(api.scene.add_slices(**kw))),
    _spec("scene_add_boundary", "Add boundary files (optionally one quantity) as scene layers.",
          {"quantity": _STR}, [], lambda api, **kw: _names(api.scene.add_boundary(**kw))),
    _spec("scene_add_particles", "Add particle classes as scene layers.",
          {"class_name": _STR, "quantity": _STR, "diameter": _NUM}, [],
          lambda api, **kw: _names(api.scene.add_particles(**kw))),
    _spec("scene_add_volume_from_plot3d", "Add smoke (soot density), fire (HRRPUV) or a scalar volume from a Plot3D quantity.",
          {"quantity": _STR, "kind": {"type": "string", "enum": ["scalar", "smoke", "fire"]}, "path": _STR, "mesh": _STR,
           "opacity": _NUM}, ["quantity"],
          lambda api, **kw: api.scene.add_volume_from_plot3d(**kw).name),
    _spec("scene_layers", "List the scene's layers.", {}, [], lambda api: api.scene.layers()),
    _spec("scene_summary", "Layers, timeline and clip planes of the results scene.", {}, [], lambda api: api.scene.summary()),
    _spec("scene_set_layer", "Show/hide a layer or change its opacity.",
          {"name": _STR, "visible": {"type": "boolean"}, "opacity": _NUM, "remove": {"type": "boolean"}}, ["name"],
          lambda api, name, visible=None, opacity=None, remove=False: _set_layer(api, name, visible, opacity, remove)),
    _spec("scene_seek", "Move the playback position: by time, by 0-1 progress or by frame steps.",
          {"time": _NUM, "progress": _NUM, "step": {"type": "integer"}}, [], _seek),
    _spec("scene_add_clip", "Cut the scene at an axis-aligned plane (clear=true removes all clip planes).",
          {"axis": {"type": "string", "enum": ["x", "y", "z"]}, "position": _NUM,
           "keep": {"type": "string", "enum": ["above", "below"]}, "clear": {"type": "boolean"}}, [],
          lambda api, axis=None, position=None, keep="above", clear=False: _clip(api, axis, position, keep, clear)),
    _spec("scene_probe", "Values of every visible layer at a point (at the playback time unless time is given).",
          {"point": _PT3, "time": _NUM, "tolerance": _NUM}, ["point"],
          lambda api, point, time=None, tolerance=None: api.scene.probe(point, time, tolerance)),
    _spec("scene_save_view", "Save the current viewport camera under a name.", {"name": _STR, "overwrite": {"type": "boolean"}},
          ["name"], lambda api, name, overwrite=False: api.scene.save_view(name, None, overwrite), mutates=True),
]


def _clip(api, axis, position, keep, clear):
    if clear:
        api.scene.clear_clips()
    else:
        if axis is None or position is None:
            raise ValueError("give axis and position (or clear=true)")
        api.scene.add_clip(axis, position, keep)
    return len(api.scene.scene.clips)


def _set_layer(api, name, visible, opacity, remove):
    if remove:
        api.scene.remove(name)
        return None
    if visible is not None:
        api.scene.set_visible(name, visible)
    if opacity is not None:
        api.scene.set_opacity(name, opacity)
    return None
