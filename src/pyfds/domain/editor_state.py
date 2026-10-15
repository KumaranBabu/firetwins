"""
Per-project editor state
========================
Floors, groups and scenarios are *editor-side* data: they are never written
to the FDS file, but they belong to a document, so they live on the project
(``project.editor``) rather than on the API object. Each open document
therefore has its own, and they are saved in ``.pyfds`` archives.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

from .scenario import ScenarioStore
from .views import SavedView, SectionBox


@dataclass
class Floor:
    """A named elevation band used to organise entities by storey."""
    name: str
    z_min: float
    z_max: float
    description: str = ""


@dataclass
class Group:
    """A named, purely editor-side collection of entities — never written to
    the FDS file (same treatment as ``FdsEntity.tags``/``enabled``). Exists
    so Move/Rotate/Scale/Mirror Selected can transform several objects as
    one rigid unit by selecting just one of them."""
    name: str
    description: str = ""


@dataclass
class Background:
    """A floor-plan image or PDF page shown under the model (never written to the FDS file).

    The picture's lower-left corner sits at (*x*, *y*, *z*) and it is *width* metres wide; the height
    follows from the picture's aspect ratio.
    """
    name: str
    path: str
    kind: str = "image"          # "image" or "pdf"
    page: int = 0                # PDF page (0-based)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    width: float = 10.0
    opacity: float = 0.5
    visible: bool = True
    floor: str = ""


class EditorState:
    """Floors, groups and scenarios of one project."""

    def __init__(self) -> None:
        self.scenarios = ScenarioStore()
        self.floors: Dict[str, Floor] = {}
        self.floor_assignments: Dict[str, str] = {}     # entity_uid -> floor name
        self.groups: Dict[str, Group] = {}
        self.backgrounds: Dict[str, Background] = {}
        self.fire_items: Dict[str, dict] = {}           # saved HRR curves {name: {times, hrr, description, source}}
        self.group_memberships: Dict[str, str] = {}     # entity_uid -> group name
        self.hidden: Set[str] = set()                   # entity uids hidden in the views
        self.hidden_types: Set[str] = set()             # collection names switched off ("vents", ...)
        self.units: str = "SI"                          # display/entry unit system: "SI" or "EN"
        self.views: Dict[str, SavedView] = {}           # saved viewpoints
        self.active_view: Optional[str] = None
        self.section_box: Optional[SectionBox] = None   # current clipping box, None = no box

    def is_empty(self) -> bool:
        return not (self.scenarios.all() or self.floors or self.groups or self.backgrounds or self.fire_items
                    or self.floor_assignments or self.group_memberships
                    or self.hidden or self.hidden_types or self.units != "SI"
                    or self.views or self.section_box)
