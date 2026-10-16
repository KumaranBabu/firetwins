"""The tool framework (plan step F2): a *Tool* is a small state machine fed with picked points.

The viewport widget turns mouse and key events into ``Hit`` objects and calls ``click`` / ``move`` / ``finish`` /
``cancel`` on the active tool; the tool answers with what to preview and, when a drawing is complete, creates the
object through ``api`` (so every result is an ordinary undo step). Nothing here knows about Qt or VTK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .snap import Point, snap_point

Box = Tuple[float, float, float, float, float, float]


@dataclass
class Hit:
    """Where the mouse ray met the model: a point, the face normal there (None = unknown / open floor), and the
    ``(manager_attr, entity)`` it hit (None over empty space)."""
    point: Point
    normal: Optional[Point] = None
    entity: Optional[Tuple[str, Any]] = None


@dataclass
class Preview:
    """What to draw while a tool is working: translucent boxes, polylines, and a line of text for the status bar."""
    boxes: List[Box] = field(default_factory=list)
    polylines: List[List[Point]] = field(default_factory=list)
    text: str = ""


@dataclass
class ToolProps:
    """The 'Tool Properties' shared by the drawing tools (PyroSim's tool-properties panel)."""
    height: float = 3.0                  # obstruction / hole / mesh / wall height (m)
    z_base: Optional[float] = None       # None = start on the surface that was clicked
    surface_id: Optional[str] = None     # surface for new obstructions and vents (None = the tool's default)
    cell_size: float = 0.1               # for drawn meshes (m)
    wall_thickness: float = 0.2          # (m)
    paint_surface: Optional[str] = None  # the surface the Paint tool applies
    recent_surfaces: List[str] = field(default_factory=list)

    def remember(self, surface: str, limit: int = 8) -> None:
        if surface in self.recent_surfaces:
            self.recent_surfaces.remove(surface)
        self.recent_surfaces.insert(0, surface)
        del self.recent_surfaces[limit:]


class ToolContext:
    """What a tool may use: the api, the properties, snapping, and a way to report progress."""

    def __init__(self, api: Any, props: Optional[ToolProps] = None) -> None:
        self.api = api
        self.props = props or ToolProps()
        self.messages: List[str] = []

    def snap(self, point: Sequence[float], anchor: Optional[Sequence[float]] = None) -> Point:
        objects = self.api.obstructions.all() + self.api.vents.all() + self.api.holes.all() + self.api.meshes.all()
        return snap_point(point, self.api.viewport.state.snap, self.api.meshes.all(), objects, anchor)

    def say(self, text: str) -> None:
        self.messages.append(text)


class Tool:
    name = "tool"
    label = "Tool"
    hint = ""                            # what the next click does, for the status bar

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx
        self.created: List[Any] = []     # everything this tool made since it was activated
        self.cancel()

    def click(self, hit: Hit) -> Optional[Any]:
        """A left click. Returns what was created when this click completed a drawing, else None."""
        return None

    def move(self, hit: Hit) -> None:
        """The mouse moved (for the rubber-band preview)."""

    def finish(self) -> List[Any]:
        """Enter / double-click: complete a multi-point drawing. Returns what was created."""
        return []

    def cancel(self) -> None:
        """Escape: drop any half-finished drawing."""

    def preview(self) -> Preview:
        return Preview(text=self.hint)

    def active(self) -> bool:
        """True while a drawing is half done (the widget then keeps the tool on Escape instead of leaving it)."""
        return False


def box_from_points(a: Sequence[float], b: Sequence[float]) -> Box:
    return (min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]), min(a[2], b[2]), max(a[2], b[2]))


def normal_axis(normal: Optional[Sequence[float]]) -> int:
    """Index of the dominant axis of a face normal (2 = Z when unknown)."""
    if normal is None:
        return 2
    return max(range(3), key=lambda i: abs(normal[i]))
