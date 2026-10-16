"""Drawing tools (plan step F2): boxes (obstruction, hole, vent, mesh) and walls. Each creates its objects through
``api`` so every drawing is one undo step, and stays active so several can be drawn in a row."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from pyfds.gui.editors.mesh_tools import nearest_poisson

from .base import Box, Hit, Point, Preview, Tool, ToolContext, box_from_points, normal_axis

_EPS = 1e-9
_AXIS_NAMES = "XYZ"


class BoxTool(Tool):
    """Two clicks: opposite corners of the footprint. The height comes from the tool properties, so nothing is asked
    in a dialog. A vent is flat: it lies in the plane of the face of the first click (the floor when none)."""

    LABELS = {"obstruction": "Obstruction", "hole": "Hole", "vent": "Vent", "mesh": "Mesh"}

    def __init__(self, ctx: ToolContext, kind: str = "obstruction") -> None:
        if kind not in self.LABELS:
            raise ValueError(f"unknown box tool {kind!r}")
        self.kind = kind
        self.name = kind
        self.label = self.LABELS[kind]
        super().__init__(ctx)

    def cancel(self) -> None:
        self._a: Optional[Point] = None
        self._b: Optional[Point] = None
        self._axis = 2

    def active(self) -> bool:
        return self._a is not None

    @property
    def hint(self) -> str:                                     # type: ignore[override]
        return (f"{self.label}: click the first corner" if self._a is None
                else f"{self.label}: click the opposite corner (Esc cancels)")

    # -- geometry ------------------------------------------------------------------------------------
    def _first(self, hit: Hit) -> Point:
        x, y, z = self.ctx.snap(hit.point)
        if self.kind != "vent" and self.ctx.props.z_base is not None:
            z = self.ctx.props.z_base
        return (x, y, z)

    def xb(self, a: Point, b: Point) -> Optional[Box]:
        """The box for corners *a* and *b* (None when it would be flat in a direction that must have size)."""
        if self.kind == "vent":
            k = self._axis
            u, v = [i for i in range(3) if i != k]
            if abs(a[u] - b[u]) < _EPS or abs(a[v] - b[v]) < _EPS:
                return None
            lo, hi = [0.0] * 3, [0.0] * 3
            lo[k] = hi[k] = a[k]
            lo[u], hi[u] = sorted((a[u], b[u]))
            lo[v], hi[v] = sorted((a[v], b[v]))
            return (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
        if abs(a[0] - b[0]) < _EPS or abs(a[1] - b[1]) < _EPS or self.ctx.props.height <= 0:
            return None
        flat = box_from_points((a[0], a[1], a[2]), (b[0], b[1], a[2] + self.ctx.props.height))
        return flat

    # -- events ---------------------------------------------------------------------------------------
    def click(self, hit: Hit) -> Optional[Any]:
        if self._a is None:
            self._a = self._first(hit)
            self._axis = normal_axis(hit.normal) if self.kind == "vent" else 2
            return None
        b = self.ctx.snap(hit.point, anchor=self._a)
        box = self.xb(self._a, b)
        if box is None:
            self.ctx.say(f"{self.label} too small: move the mouse further from the first corner")
            return None
        entity = self._create(box)
        self.created.append(entity)
        self.cancel()
        return entity

    def move(self, hit: Hit) -> None:
        if self._a is not None:
            self._b = self.ctx.snap(hit.point, anchor=self._a)

    def preview(self) -> Preview:
        if self._a is None or self._b is None:
            return Preview(text=self.hint)
        box = self.xb(self._a, self._b)
        if box is None:
            return Preview(text=self.hint)
        size = " x ".join(f"{box[2 * i + 1] - box[2 * i]:.3g}" for i in range(3) if box[2 * i + 1] - box[2 * i] > _EPS)
        return Preview(boxes=[box], text=f"{self.label}: {size} m")

    def _create(self, box: Box) -> Any:
        api, props = self.ctx.api, self.ctx.props
        if self.kind == "obstruction":
            return api.obstructions.add_obstruction(list(box), surf_id=props.surface_id or "INERT")
        if self.kind == "vent":
            return api.vents.add_vent(list(box), surf_id=props.surface_id or "OPEN")
        if self.kind == "hole":
            return api.holes.add_hole(list(box))
        size = [box[2 * i + 1] - box[2 * i] for i in range(3)]
        ijk = [nearest_poisson(max(1, round(s / props.cell_size))) for s in size]
        return api.meshes.add_mesh(ijk, list(box))


class WallTool(Tool):
    """Click the corners of a wall run; Enter finishes (``close()`` joins the last point to the first). Segments are
    kept axis-aligned, each is an obstruction of the tool's thickness and height, and the whole run is one undo step."""

    name = "wall"
    label = "Wall"

    def cancel(self) -> None:
        self._pts: List[Point] = []
        self._cursor: Optional[Point] = None

    def active(self) -> bool:
        return bool(self._pts)

    @property
    def hint(self) -> str:                                     # type: ignore[override]
        return ("Wall: click the start of the wall" if not self._pts
                else "Wall: click the next corner, Enter to finish, Esc to cancel")

    def _next(self, hit: Hit) -> Point:
        if not self._pts:
            x, y, z = self.ctx.snap(hit.point)
            return (x, y, self.ctx.props.z_base if self.ctx.props.z_base is not None else z)
        last = self._pts[-1]
        x, y, _z = self.ctx.snap(hit.point, anchor=last)
        if abs(x - last[0]) >= abs(y - last[1]):             # walls run along X or along Y
            y = last[1]
        else:
            x = last[0]
        return (x, y, last[2])

    def click(self, hit: Hit) -> Optional[Any]:
        p = self._next(hit)
        if self._pts and abs(p[0] - self._pts[-1][0]) < _EPS and abs(p[1] - self._pts[-1][1]) < _EPS:
            return None                                      # a repeated click adds no segment
        self._pts.append(p)
        return None

    def move(self, hit: Hit) -> None:
        if self._pts:
            self._cursor = self._next(hit)

    def segments(self, points: Optional[List[Point]] = None) -> List[Box]:
        pts = points if points is not None else self._pts
        t, h = self.ctx.props.wall_thickness / 2.0, self.ctx.props.height
        out: List[Box] = []
        for a, b in zip(pts, pts[1:]):
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            if x1 - x0 >= y1 - y0:                           # along X: grow the ends so corners close
                x0, x1, y0, y1 = x0 - t, x1 + t, y0 - t, y0 + t
            else:
                x0, x1, y0, y1 = x0 - t, x0 + t, y0 - t, y1 + t
            out.append((x0, x1, y0, y1, a[2], a[2] + h))
        return out

    def preview(self) -> Preview:
        pts = list(self._pts) + ([self._cursor] if self._cursor and self._pts else [])
        return Preview(boxes=self.segments(pts), polylines=[pts] if len(pts) > 1 else [], text=self.hint)

    def close(self) -> List[Any]:
        """Join the last point back to the first and finish."""
        if len(self._pts) >= 3:
            self._pts.append(self._pts[0])
        return self.finish()

    def finish(self) -> List[Any]:
        boxes = self.segments()
        made: List[Any] = []
        if boxes:
            api, props = self.ctx.api, self.ctx.props
            with api.history.transaction("draw wall"):
                for box in boxes:
                    made.append(api.obstructions.add_obstruction(list(box), surf_id=props.surface_id or "INERT"))
        self.created.extend(made)
        self.cancel()
        return made
