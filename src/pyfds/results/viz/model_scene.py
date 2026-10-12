"""Visualization model: views, tours, sections, annotations, units."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# -- views, tours, sections --------------------------------------------------------------------------------
@dataclass
class Viewpoint:
    position: Tuple[float, float, float] = (10.0, -10.0, 8.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    fov_deg: float = 45.0
    zoom: float = 1.0
    projection: str = "perspective"               # perspective | orthogonal
    navigation: str = "orbit"


@dataclass
class Keyframe:
    time: float
    viewpoint: Viewpoint = field(default_factory=Viewpoint)
    transition: str = "move_to_next"              # move_to_next | stationary


@dataclass
class Tour:
    timeline: str = "fds"
    repeat: bool = False
    repeat_delay: float = 0.0
    keyframes: List[Keyframe] = field(default_factory=list)

    @property
    def time_range(self) -> Optional[Tuple[float, float]]:
        if not self.keyframes:
            return None
        return self.keyframes[0].time, self.keyframes[-1].time


PLANES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


@dataclass
class SectionBox:
    """Up to six planes; a plane clips only when enabled. Everything outside the box is hidden."""
    planes: Dict[str, Tuple[bool, float]] = field(default_factory=dict)
    enabled: bool = True

    def active(self) -> Dict[str, float]:
        return {k: v[1] for k, v in self.planes.items() if v[0]} if self.enabled else {}


@dataclass
class View:
    name: str
    origin: str = "pyfds"                         # "fds" for views read from FDS / Smokeview files (read-only)
    viewpoint: Optional[Viewpoint] = None
    tour: Optional[Tour] = None
    section_box: Optional[SectionBox] = None


# -- annotations, floors, skybox, time, units -----------------------------------------------------------------
@dataclass
class Dimension:
    p1: Tuple[float, float, float]
    p2: Tuple[float, float, float]
    mode: str = "feature"                         # feature | along_x | along_y | along_z
    offset: float = 0.0


@dataclass
class Label:
    text: str
    anchor: Tuple[float, float, float]
    position: Optional[Tuple[float, float, float]] = None   # None = label sits on the anchor (no leader line)


@dataclass
class FloorSettings:
    floors: List[float] = field(default_factory=list)      # Z of each floor, ascending
    layout: str = "vertical"                      # vertical | horizontal
    separation: float = 0.0
    clip_walls: bool = False
    wall_height: float = 2.0
    visible: Optional[List[int]] = None           # indices of visible floors; None = all


@dataclass
class Skybox:
    kind: str = "none"                            # none | predefined | image360 | cubemap | split_cubemap
    files: List[str] = field(default_factory=list)
    z_rotation: float = 0.0
    show: bool = True
    compress_textures: bool = False


@dataclass
class Timelines:
    reference_time: str = "2000-01-01T00:00:00"
    display_format: str = "regional"              # regional | iso8601
    fds_offset: float = 0.0
    view_timeline: str = "automatic"              # automatic | custom
    begin: float = 0.0
    end: float = 0.0


@dataclass
class Units:
    temperature: str = "C"                        # C | F
    concentration: str = "mol/mol"                # mol/mol | ppm
    mass_fraction: str = "kg/kg"                  # kg/kg | ppm

    def problems(self) -> List[str]:
        out = []
        if self.temperature not in ("C", "F"):
            out.append("temperature unit must be C or F")
        if self.concentration not in ("mol/mol", "ppm"):
            out.append("concentration unit must be mol/mol or ppm")
        if self.mass_fraction not in ("kg/kg", "ppm"):
            out.append("mass fraction unit must be kg/kg or ppm")
        return out


@dataclass
class CsvFileRef:
    path: str
    csv_type: str = "custom"
    time_column: int = 1
    header_rows: int = 2
    description_row: int = 2
    quantity_row: Optional[int] = None
    unit_row: Optional[int] = 1


@dataclass
class Data3DPoint:
    id: str
    group: str                                    # node id of the Data3D group it was made from
    quantity: str
    xyz: Tuple[float, float, float]


@dataclass
class Data3DSlice:
    id: str
    group: str
    quantity: str
    origin: Tuple[float, float, float]
    normal: Tuple[float, float, float]


@dataclass
class Data3DIso:
    id: str
    group: str
    quantity: str
    value: float
