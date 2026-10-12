"""Results viewer (``api.viewer``): open a run, switch results on/off, move in time, set colorbars, views, screenshots."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}


def _spec(name, description, props, required, handler):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=False)


def _summary(api):
    v = api.viewer
    lo, hi = v.time_range()
    return {"results": v.run.chid if v.run else None, "active": [n.id for n in v.active_leaves()],
            "time": v.time, "time_range": [lo, hi], "visualization": v.path, "unsaved": v.dirty}


def _open(api, source):
    v = api.viewer
    (v.open_visualization if str(source).endswith(".pyfdsv") else v.open_results)(source)
    return _summary(api)


def _tree(api, kind=None):
    return [{"id": n.id, "kind": n.kind, "quantity": n.quantity, "active": api.viewer.node_state(n.id) != "none"}
            for n in api.viewer.tree.leaves() if kind is None or n.kind == kind]


def _toggle(api, node, on=None):
    v = api.viewer
    if on is None:
        v.toggle(node)
    else:
        (v.activate if on else v.deactivate)(node)
    return _summary(api)


def _seek(api, time):
    api.viewer.set_time(time)
    return _summary(api)


def _colorbar(api, quantity, **fields):
    if not fields:
        bar = api.viewer.colorbar(quantity)
        return {"quantity": quantity, "min": bar.lo, "max": bar.hi}
    if "minimum" in fields and "maximum" in fields:
        fields["range_mode"] = "custom"
    p = api.viewer.set_colorbar(quantity, **fields)
    return {k: getattr(p, k) for k in fields}


TOOLS: List[ToolSpec] = [
    _spec("viewer_open", "Open a run's .smv (or a saved .pyfdsv) in the results viewer.", {"source": _STR}, ["source"], _open),
    _spec("viewer_summary", "What the results viewer has loaded, active, and the playback time.", {}, [], _summary),
    _spec("viewer_list", "Every result that can be shown (id, kind, quantity, active), optionally one kind such as slice2d, "
          "smoke3d, boundary, particles, isosurface.", {"kind": _STR}, [], _tree),
    _spec("viewer_show", "Switch a result on or off by its id (omit 'on' to toggle).",
          {"node": _STR, "on": {"type": "boolean"}}, ["node"], _toggle),
    _spec("viewer_seek", "Move the viewer to a time in seconds.", {"time": _NUM}, ["time"], _seek),
    _spec("viewer_colorbar", "Read a quantity's colorbar range, or change its properties (minimum, maximum, colormap...).",
          {"quantity": _STR, "minimum": _NUM, "maximum": _NUM, "colormap": _STR}, ["quantity"], _colorbar),
    _spec("viewer_view", "Switch the camera to top / front / side / isometric.",
          {"name": {"type": "string", "enum": ["top", "front", "side", "isometric"]}}, ["name"],
          lambda api, name: api.viewer.standard_view(name).__dict__),
    _spec("viewer_screenshot", "Save an image of the current scene (needs the results window or the CLI renderer).",
          {"path": _STR, "time": _NUM, "view": _STR}, ["path"],
          lambda api, path, time=None, view="<current view>": api.viewer.screenshot(path, time, view)),
    _spec("viewer_save", "Save the results visualization (.pyfdsv).", {"path": _STR}, [],
          lambda api, path=None: api.viewer.save(path)),
]
