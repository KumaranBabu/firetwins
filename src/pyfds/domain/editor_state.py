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
from typing import Dict, Set

from .scenario import ScenarioStore


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


class EditorState:
    """Floors, groups and scenarios of one project."""

    def __init__(self) -> None:
        self.scenarios = ScenarioStore()
        self.floors: Dict[str, Floor] = {}
        self.floor_assignments: Dict[str, str] = {}     # entity_uid -> floor name
        self.groups: Dict[str, Group] = {}
        self.group_memberships: Dict[str, str] = {}     # entity_uid -> group name
        self.hidden: Set[str] = set()                   # entity uids hidden in the views
        self.hidden_types: Set[str] = set()             # collection names switched off ("vents", ...)

    def is_empty(self) -> bool:
        return not (self.scenarios.all() or self.floors or self.groups
                    or self.floor_assignments or self.group_memberships
                    or self.hidden or self.hidden_types)
