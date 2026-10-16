"""Geometry of the 2D plan view (plan step F3), free of Qt: which objects the plan shows at a level, what a click
hits, and how coarse the sketch grid is at a zoom. The widget (``plan_view.py``) only draws these.

Coordinates are model metres, X right and Y up; the widget flips Y when it maps to the screen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence, Set, Tuple

from pyfds.core.viewport import VisibilityFlags

#: kind -> (drawing order, pick priority). Higher order is drawn on top; higher priority wins a click.
KINDS = {"mesh": (0, 1), "init": (1, 2), "obstruction": (2, 3), "hole": (3, 4), "vent": (4, 5), "device": (5, 6)}
_ATTR = {"mesh": "meshes", "init": "inits", "obstruction": "obstructions", "hole": "holes", "vent": "vents",
         "device": "devices"}
_FLAG = {"mesh": VisibilityFlags.MESHES, "init": VisibilityFlags.INIT_REGIONS,
         "obstruction": VisibilityFlags.OBSTRUCTIONS, "hole": VisibilityFlags.HOLES, "vent": VisibilityFlags.VENTS,
         "device": VisibilityFlags.DEVICES}


@dataclass
class PlanShape:
    kind: str
    attr: str
    entity: Any
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float = 0.0
    z1: float = 0.0
    color: str = "#9a9a9a"
    label: str = ""
    cells: Tuple[int, int] = (0, 0)           # meshes: cell counts along X and Y, for their grid lines
    below: bool = False                       # entirely below the level (drawn faint)

    @property
    def is_point(self) -> bool:
        return self.kind == "device"

    def rect(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


def _band_overlap(z0: float, z1: float, level: float, top: float) -> bool:
    """Does [z0, z1] reach into the slab [level, top]? A flat object exactly on a slab edge counts."""
    return z1 >= level - 1e-9 and z0 <= top + 1e-9


def plan_shapes(api: Any, level: float = 0.0, band: float = 3.0,
                visible: Optional[Set[str]] = None) -> List[PlanShape]:
    """Everything that shows in the plan of the slab ``[level, level + band]``, in drawing order.

    Meshes always show (their outline is the domain). Obstructions, holes, vents, initial regions and devices show when
    they reach into the slab; ``visible`` limits the kinds (default: follow ``api.viewport`` visibility flags)."""
    state = api.viewport.state
    top = level + band
    out: List[PlanShape] = []
    for kind, attr in _ATTR.items():
        if visible is not None:
            if kind not in visible:
                continue
        elif not state.is_visible(_FLAG[kind]):
            continue
        for e in getattr(api, attr).all():
            if not getattr(e, "enabled", True):
                continue
            if kind == "device":
                xyz = getattr(e, "xyz", None)
                if xyz is None or not _band_overlap(xyz[2], xyz[2], level, top):
                    continue
                out.append(PlanShape(kind, attr, e, xyz[0], xyz[1], xyz[0], xyz[1], xyz[2], xyz[2], "#d4ac0d",
                                     getattr(e, "name", "")))
                continue
            b = e.bbox() if hasattr(e, "bbox") else None
            if b is None:
                continue
            if kind != "mesh" and not _band_overlap(b[4], b[5], level, top):
                continue
            cells = tuple(e.cell_count[:2]) if kind == "mesh" else (0, 0)
            out.append(PlanShape(kind, attr, e, b[0], b[2], b[1], b[3], b[4], b[5], _color(kind, e),
                                 getattr(e, "name", ""), cells, below=b[5] < level - 1e-9))
    out.sort(key=lambda s: KINDS[s.kind][0])
    return out


_NAMED = {"RED": "#c0392b", "GREEN": "#2e8b57", "BLUE": "#3060c0", "YELLOW": "#d4ac0d", "ORANGE": "#d4720a",
          "WHITE": "#e8e8e8", "BLACK": "#222222", "BROWN": "#8b5a2b", "PURPLE": "#7d3c98", "GRAY": "#9a9a9a",
          "GREY": "#9a9a9a"}
_KIND_COLOR = {"mesh": "#4a90d9", "init": "#1abc9c", "hole": "#c0392b", "vent": "#2e8b57"}


def _color(kind: str, entity: Any) -> str:
    if kind == "obstruction":
        c = getattr(entity, "color", None)
        if isinstance(c, str) and c.startswith("#"):
            return c
        return _NAMED.get(str(c).upper(), "#9a9a9a")
    return _KIND_COLOR.get(kind, "#9a9a9a")


# -- picking -------------------------------------------------------------------------------------------------------
def _dist_to_rect_edge(x: float, y: float, s: PlanShape) -> float:
    dx = max(s.x0 - x, 0.0, x - s.x1)
    dy = max(s.y0 - y, 0.0, y - s.y1)
    if dx or dy:                                      # outside: distance to the rectangle
        return math.hypot(dx, dy)
    return min(x - s.x0, s.x1 - x, y - s.y0, s.y1 - y)    # inside: distance to the nearest edge


def pick_shape(shapes: Iterable[PlanShape], x: float, y: float, tol: float) -> Optional[PlanShape]:
    """The shape under model point (*x*, *y*), or None. *tol* is the click tolerance in metres (a few pixels).

    Devices hit within *tol*; vents and holes within *tol* of their rectangle; obstructions and initial regions
    anywhere inside; meshes only near their outline (so a click inside a domain reaches what is inside it). On equal
    priority the smaller shape wins, so a small box on a big one is selectable."""
    best: Optional[Tuple[Tuple[int, float], PlanShape]] = None
    for s in shapes:
        pri = KINDS[s.kind][1]
        if s.kind == "device":
            hit = math.hypot(x - s.x0, y - s.y0) <= tol
        elif s.kind == "mesh":
            hit = _dist_to_rect_edge(x, y, s) <= tol
        elif s.kind in ("vent", "hole"):
            hit = s.x0 - tol <= x <= s.x1 + tol and s.y0 - tol <= y <= s.y1 + tol
        else:
            hit = s.x0 <= x <= s.x1 and s.y0 <= y <= s.y1
        if not hit:
            continue
        key = (pri, -(s.x1 - s.x0) * (s.y1 - s.y0))
        if best is None or key > best[0]:
            best = (key, s)
    return best[1] if best else None


# -- sketch grid ---------------------------------------------------------------------------------------------------
def grid_spacing(base: float, px_per_m: float, min_px: float = 12.0) -> float:
    """The grid spacing to draw: the snap grid *base*, doubled/quintupled/decupled ... until lines are at least
    *min_px* apart on screen (1, 2, 5, 10 ...)."""
    if base <= 0 or px_per_m <= 0:
        return 1.0
    step = base
    for _decade in range(12):
        for mult in (1, 2, 5):
            if step * mult * px_per_m >= min_px:
                return step * mult
        step *= 10
    return step


def grid_lines(lo: float, hi: float, spacing: float, limit: int = 2000) -> List[float]:
    """Multiples of *spacing* in [lo, hi] (capped so a bad zoom cannot ask for millions of lines)."""
    if spacing <= 0 or hi < lo:
        return []
    k0 = math.ceil(lo / spacing - 1e-9)
    k1 = math.floor(hi / spacing + 1e-9)
    if k1 - k0 > limit:
        return []
    return [k * spacing for k in range(k0, k1 + 1)]


def extent(shapes: Sequence[PlanShape]) -> Optional[Tuple[float, float, float, float]]:
    """(xmin, ymin, xmax, ymax) of everything shown, or None when empty."""
    if not shapes:
        return None
    return (min(s.x0 for s in shapes), min(s.y0 for s in shapes), max(s.x1 for s in shapes), max(s.y1 for s in shapes))
