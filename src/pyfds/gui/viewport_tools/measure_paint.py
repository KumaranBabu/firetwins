"""Measure, Pick (eyedropper) and Paint tools (plan step F2, APP-02)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import Hit, Point, Preview, Tool, normal_axis

#: Face order of ``Obstruction.surface_ids`` when it has six entries (FDS SURF_ID6).
FACES = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")


@dataclass
class Measurement:
    start: Point
    end: Point

    @property
    def delta(self) -> Point:
        return tuple(e - s for s, e in zip(self.start, self.end))     # type: ignore[return-value]

    @property
    def distance(self) -> float:
        return math.dist(self.start, self.end)

    def text(self) -> str:
        dx, dy, dz = self.delta
        return f"distance {self.distance:.4g} m   (dx {dx:.4g}, dy {dy:.4g}, dz {dz:.4g})"


class MeasureTool(Tool):
    name = "measure"
    label = "Measure"

    def cancel(self) -> None:
        self._a: Optional[Point] = None
        self._b: Optional[Point] = None

    def active(self) -> bool:
        return self._a is not None

    def __init__(self, ctx) -> None:
        self.last: Optional[Measurement] = None
        self.history: List[Measurement] = []
        super().__init__(ctx)

    @property
    def hint(self) -> str:                                     # type: ignore[override]
        return "Measure: click the first point" if self._a is None else "Measure: click the second point"

    def click(self, hit: Hit) -> Optional[Measurement]:
        p = self.ctx.snap(hit.point)
        if self._a is None:
            self._a = p
            return None
        m = Measurement(self._a, p)
        self.last = m
        self.history.append(m)
        self.ctx.say(m.text())
        self.cancel()
        return m

    def move(self, hit: Hit) -> None:
        if self._a is not None:
            self._b = self.ctx.snap(hit.point)

    def preview(self) -> Preview:
        if self._a is not None and self._b is not None:
            return Preview(polylines=[[self._a, self._b]], text="Measure: " + Measurement(self._a, self._b).text())
        return Preview(text=self.last.text() if self.last and self._a is None else self.hint)


# -- surfaces on faces ------------------------------------------------------------------------------------------
def face_index(normal: Optional[Point]) -> Optional[int]:
    """0..5 into :data:`FACES` for a face normal, or None when the normal is unknown."""
    if normal is None:
        return None
    a = normal_axis(normal)
    return 2 * a + (1 if normal[a] > 0 else 0)


def face_surfaces(entity: Any) -> List[str]:
    """The six face surfaces of an obstruction (expanding SURF_ID and the 3-entry top/sides/bottom form)."""
    ids = getattr(entity, "surface_ids", None)
    base = entity.surface_id
    if not ids:
        return [base] * 6
    if len(ids) == 3:                                  # top, sides, bottom
        top, sides, bottom = ids
        return [sides, sides, sides, sides, bottom, top]
    return list(ids) + [base] * (6 - len(ids))


def surface_at(entity: Any, normal: Optional[Point]) -> Optional[str]:
    """The surface on the clicked face of an obstruction, or the object's surface when the face is unknown."""
    if hasattr(entity, "surface_ids"):
        i = face_index(normal)
        return face_surfaces(entity)[i] if i is not None else entity.surface_id
    return getattr(entity, "surface_id", None)


def paint_fields(entity: Any, normal: Optional[Point], surface: str) -> Dict[str, Any]:
    """The field changes that put *surface* on one face (or on the whole object when the face is unknown)."""
    if not hasattr(entity, "surface_ids"):
        return {"surface_id": surface}
    i = face_index(normal)
    if i is None:
        return {"surface_id": surface, "surface_ids": None}
    faces = face_surfaces(entity)
    faces[i] = surface
    if len(set(faces)) == 1:
        return {"surface_id": faces[0], "surface_ids": None}
    return {"surface_ids": faces}


class PickTool(Tool):
    """Eyedropper: click a face to make its surface the one the Paint tool applies."""
    name = "pick"
    label = "Pick"
    hint = "Pick: click a face to take its surface"

    def click(self, hit: Hit) -> Optional[str]:
        if hit.entity is None:
            self.ctx.say("Pick: nothing under the cursor")
            return None
        surface = surface_at(hit.entity[1], hit.normal)
        if not surface:
            self.ctx.say("Pick: that object has no surface")
            return None
        self.ctx.props.paint_surface = surface
        self.ctx.props.remember(surface)
        self.ctx.say(f"Picked surface {surface}")
        return surface


class PaintTool(Tool):
    """Click a face to give it the paint surface (the whole object when the face is unknown)."""
    name = "paint"
    label = "Paint"

    @property
    def hint(self) -> str:                                     # type: ignore[override]
        s = self.ctx.props.paint_surface
        return f"Paint with {s}: click a face" if s else "Paint: choose a surface (or use Pick) first"

    def click(self, hit: Hit) -> Optional[Any]:
        surface = self.ctx.props.paint_surface
        if not surface:
            self.ctx.say(self.hint)
            return None
        if hit.entity is None:
            return None
        attr, entity = hit.entity
        if attr not in ("obstructions", "vents"):
            self.ctx.say("Paint: only obstructions and vents have surfaces")
            return None
        fields = paint_fields(entity, hit.normal if attr == "obstructions" else None, surface)
        getattr(self.ctx.api, attr).update(entity, **fields)
        self.ctx.props.remember(surface)
        return entity
