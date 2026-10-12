"""Views, camera tours and section boxes (phase V7).

A *view* stores a viewpoint **or** a tour (never both) and optionally a section box. Tours are keyframed
camera animations over playback time; the camera moves smoothly between keyframes unless a keyframe says
``stationary``. All functions work on the plain data classes in :mod:`.model`, so the same code serves the
window, scripts and tests.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Dict, List, Optional, Sequence, Tuple

from .model import (PLANES, Keyframe, ResultsVisualization, SectionBox, Tour, View, Viewpoint, from_plain, to_plain)


# -- viewpoint maths -------------------------------------------------------------------------------------
def _mix(a: Sequence[float], b: Sequence[float], u: float) -> Tuple[float, ...]:
    return tuple(float(x + (y - x) * u) for x, y in zip(a, b))


def blend(a: Viewpoint, b: Viewpoint, u: float, smooth: bool = True) -> Viewpoint:
    """Camera between two viewpoints (position, target, up, field of view, zoom)."""
    if smooth:
        u = u * u * (3.0 - 2.0 * u)
    return Viewpoint(position=_mix(a.position, b.position, u), target=_mix(a.target, b.target, u),      # type: ignore
                     up=_mix(a.up, b.up, u), fov_deg=a.fov_deg + (b.fov_deg - a.fov_deg) * u,           # type: ignore
                     zoom=a.zoom + (b.zoom - a.zoom) * u, projection=a.projection, navigation=a.navigation)


def camera_at(tour: Tour, t: float) -> Viewpoint:
    """The camera of *tour* at playback time *t* (before the first keyframe: the first viewpoint)."""
    ks = tour.keyframes
    if not ks:
        raise ValueError("the tour has no keyframes")
    first, last = ks[0].time, ks[-1].time
    if t <= first:
        return ks[0].viewpoint
    if t > last:
        if not tour.repeat:
            return ks[-1].viewpoint
        period = (last - first) + tour.repeat_delay
        if period <= 0:
            return ks[0].viewpoint
        t = first + ((t - first) % period)
        if t > last:                                                 # inside the delay: leave the last keyframe
            u = (t - last) / tour.repeat_delay if tour.repeat_delay > 0 else 1.0
            if ks[-1].transition == "stationary":
                return ks[-1].viewpoint
            return blend(ks[-1].viewpoint, ks[0].viewpoint, u)
    for a, b in zip(ks[:-1], ks[1:]):
        if a.time <= t <= b.time:
            if a.transition == "stationary" or b.time == a.time:
                return b.viewpoint if t >= b.time else a.viewpoint
            return blend(a.viewpoint, b.viewpoint, (t - a.time) / (b.time - a.time))
    return ks[-1].viewpoint


# -- keyframe editing --------------------------------------------------------------------------------------
def _sorted(tour: Tour) -> None:
    tour.keyframes.sort(key=lambda k: k.time)
    times = [k.time for k in tour.keyframes]
    if len(set(times)) != len(times):
        raise ValueError("two keyframes cannot have the same time")


def add_keyframe(tour: Tour, time: float, viewpoint: Viewpoint, transition: str = "move_to_next") -> Keyframe:
    if transition not in ("move_to_next", "stationary"):
        raise ValueError("transition must be move_to_next or stationary")
    if any(abs(k.time - time) < 1e-9 for k in tour.keyframes):
        raise ValueError(f"a keyframe already exists at t = {time:g} s")
    kf = Keyframe(float(time), copy.deepcopy(viewpoint), transition)
    tour.keyframes.append(kf)
    _sorted(tour)
    return kf


def remove_keyframes(tour: Tour, indices: Sequence[int]) -> None:
    bad = [i for i in indices if not 0 <= i < len(tour.keyframes)]
    if bad:
        raise IndexError(f"no keyframe {bad[0]}")
    for i in sorted(set(indices), reverse=True):
        del tour.keyframes[i]


def record_camera(tour: Tour, index: int, viewpoint: Viewpoint) -> None:
    """Right-click ▸ Record camera position: replace one keyframe's viewpoint."""
    tour.keyframes[index].viewpoint = copy.deepcopy(viewpoint)


def shift_keyframes(tour: Tour, indices: Sequence[int], new_time: Optional[float] = None,
                    offset: Optional[float] = None) -> None:
    """Move the selected keyframes together: to *new_time* for the first of them, or by *offset* seconds.
    They may only move inside the gap to the neighbouring unselected keyframes (anywhere when all selected)."""
    if (new_time is None) == (offset is None):
        raise ValueError("give new_time or offset")
    idx = sorted(set(indices))
    if not idx:
        raise ValueError("select at least one keyframe")
    ks = tour.keyframes
    d = (new_time - ks[idx[0]].time) if new_time is not None else offset
    lo = ks[idx[0] - 1].time if idx[0] > 0 and len(idx) < len(ks) else -math.inf
    hi = ks[idx[-1] + 1].time if idx[-1] < len(ks) - 1 and len(idx) < len(ks) else math.inf
    new_first, new_last = ks[idx[0]].time + d, ks[idx[-1]].time + d
    if new_first <= lo or new_last >= hi:
        raise ValueError("the keyframes can only be shifted within the time between their neighbours")
    for i in idx:
        ks[i].time += d


def duplicate_keyframes(tour: Tour, indices: Sequence[int], mode: str = "end_of_tour", at_time: Optional[float] = None,
                        last_delay: float = 0.0) -> List[Keyframe]:
    """Copy keyframes so that part of the tour plays again.

    ``end_of_tour``      copies go after the last keyframe, *last_delay* seconds later;
    ``at_time``          the first copy is at *at_time*; keyframes from there on move back to make room;
    ``after_selection``  copies take the time of the next unselected keyframe (which, and all after it, move back).
    Room means the gap between the last copy and the next keyframe equals the gap that followed the selection
    (10 s when the selection ends the tour). Holding a viewpoint = duplicating one keyframe this way."""
    idx = sorted(set(indices))
    if not idx:
        raise ValueError("select at least one keyframe")
    ks = tour.keyframes
    if idx[-1] >= len(ks) or idx[0] < 0:
        raise IndexError("keyframe index out of range")
    chosen = [copy.deepcopy(ks[i]) for i in idx]
    span = chosen[-1].time - chosen[0].time
    after = ks[idx[-1] + 1] if idx[-1] + 1 < len(ks) else None
    gap = (after.time - ks[idx[-1]].time) if after is not None else 10.0
    if mode == "end_of_tour":
        if last_delay <= 0:
            raise ValueError("last keyframe delay must be positive: the first copy cannot share the last keyframe's time")
        start, later = ks[-1].time + last_delay, []
    elif mode == "at_time":
        if at_time is None:
            raise ValueError("at_time mode needs a time")
        start = at_time
        later = [k for k in ks if k.time >= start - 1e-9]
    elif mode == "after_selection":
        start = after.time if after is not None else ks[idx[-1]].time + gap
        later = [k for k in ks[idx[-1] + 1:]]
    else:
        raise ValueError("mode must be end_of_tour, at_time or after_selection")
    shift = start - chosen[0].time
    for c in chosen:
        c.time += shift
    if later:
        push = (chosen[-1].time + gap) - min(k.time for k in later)
        if push > 0:
            for k in later:
                k.time += push
    ks.extend(chosen)
    _sorted(tour)
    return chosen


# -- section boxes ----------------------------------------------------------------------------------------------
def new_section_box(bounds: Sequence[float], enabled_planes: Sequence[str] = PLANES) -> SectionBox:
    """A box over *bounds* (xmin, xmax, ymin, ymax, zmin, zmax) with the named planes switched on."""
    if len(bounds) != 6:
        raise ValueError("bounds need six numbers")
    box = SectionBox()
    for i, name in enumerate(PLANES):
        box.planes[name] = (name in enabled_planes, float(bounds[i]))
    return box


def set_plane(box: SectionBox, plane: str, value: float, enabled: bool = True) -> None:
    if plane not in PLANES:
        raise KeyError(f"plane must be one of {', '.join(PLANES)}")
    box.planes[plane] = (bool(enabled), float(value))
    lo, hi = {"x": ("x_min", "x_max"), "y": ("y_min", "y_max"), "z": ("z_min", "z_max")}[plane[0]]
    a, b = box.planes.get(lo), box.planes.get(hi)
    if a and b and a[0] and b[0] and a[1] >= b[1]:
        raise ValueError(f"{lo} must be smaller than {hi}")


def clip_planes(box: Optional[SectionBox]) -> List[Tuple[str, float, str]]:
    """``[(axis, position, keep)]`` for the planes that clip: a minimum plane keeps what is above it."""
    if box is None:
        return []
    return [(p[0], v, "above" if p.endswith("min") else "below") for p, v in box.active().items()]


def inside(box: Optional[SectionBox], point: Sequence[float]) -> bool:
    return all((point["xyz".index(a)] >= v if keep == "above" else point["xyz".index(a)] <= v)
               for a, v, keep in clip_planes(box))


# -- the visualization's views ------------------------------------------------------------------------------------
def _unique(viz: ResultsVisualization, base: str) -> str:
    names = {v.name for v in viz.views} | {"Default"}
    if base not in names:
        return base
    i = 2
    while f"{base} {i}" in names:
        i += 1
    return f"{base} {i}"


def new_view(viz: ResultsVisualization, name: Optional[str] = None, viewpoint: Optional[Viewpoint] = None,
             section_box: Optional[SectionBox] = None) -> View:
    """View ▸ Views and Tours ▸ New View: the current camera and section box become a new, active view."""
    v = View(_unique(viz, name or "View"), "pyfds", copy.deepcopy(viewpoint or viz.camera), None,
             copy.deepcopy(section_box))
    viz.views.append(v)
    viz.active_view = v.name
    return v


def new_tour(viz: ResultsVisualization, name: Optional[str] = None, section_box: Optional[SectionBox] = None) -> View:
    v = View(_unique(viz, name or "Tour"), "pyfds", None, Tour(), copy.deepcopy(section_box))
    viz.views.append(v)
    viz.active_view = v.name
    return v


def activate(viz: ResultsVisualization, name: Optional[str]) -> Optional[View]:
    """Make a view active (None or ``"Default"`` = the Default view, which restores nothing)."""
    if name in (None, "Default"):
        viz.active_view = None
        return None
    v = viz.view(name)
    viz.active_view = v.name
    if v.viewpoint is not None:
        viz.camera = copy.deepcopy(v.viewpoint)
    return v


def save_viewpoint(viz: ResultsVisualization, name: str) -> None:
    v = viz.view(name)
    if v.origin != "pyfds":
        raise ValueError("views from FDS or Smokeview cannot be edited; duplicate the view first")
    if v.tour is not None:
        raise ValueError("this view holds a tour; a view has a viewpoint or a tour, not both")
    v.viewpoint = copy.deepcopy(viz.camera)


def delete_view(viz: ResultsVisualization, name: str) -> None:
    v = viz.view(name)
    viz.views.remove(v)
    if viz.active_view == name:
        viz.active_view = None


def duplicate_views(viz: ResultsVisualization, names: Sequence[str]) -> List[View]:
    out = []
    for n in names:
        src = viz.view(n)
        c = copy.deepcopy(src)
        c.name, c.origin = _unique(viz, src.name + " copy"), "pyfds"
        viz.views.append(c)
        out.append(c)
    return out


def set_section_box(viz: ResultsVisualization, name: Optional[str], box: Optional[SectionBox]) -> None:
    """Add, replace or (None) remove the section box of a view; ``name=None`` edits the active view."""
    n = name or viz.active_view
    if n is None:
        raise ValueError("the Default view cannot hold a section box; create a view first")
    v = viz.view(n)
    if v.origin != "pyfds":
        raise ValueError("views from FDS or Smokeview cannot be edited; duplicate the view first")
    v.section_box = copy.deepcopy(box)


def active_section(viz: ResultsVisualization) -> Optional[SectionBox]:
    return viz.view(viz.active_view).section_box if viz.active_view else None


def active_tour(viz: ResultsVisualization) -> Optional[Tour]:
    return viz.view(viz.active_view).tour if viz.active_view else None


def export_views(viz: ResultsVisualization) -> str:
    """The views as JSON text (a views file other visualizations can import)."""
    return json.dumps({"format": "pyfds-views", "version": 1, "views": to_plain(viz.views)}, indent=2)


def import_views(viz: ResultsVisualization, text: str, origin: str = "pyfds") -> List[View]:
    """File ▸ Import ▸ Import Views from a ``pyfds-views`` file (or a whole ``.pyfdsv``); names are kept unique."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from None
    if not isinstance(data, dict) or "views" not in data:
        raise ValueError("no views found in this file")
    added = []
    for raw in data["views"]:
        v = from_plain(View, raw)
        v.name, v.origin = _unique(viz, v.name), origin
        viz.views.append(v)
        added.append(v)
    return added
