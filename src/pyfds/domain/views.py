"""Saved views and the section box (UX-06, UX-07). Pure data, no project or Qt."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

AXES = ("x", "y", "z")


@dataclass
class SectionBox:
    """A six-sided clipping box. A side left as ``None`` is open (no clipping on that side)."""
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    enabled: bool = True      # clipping applied
    visible: bool = True      # box outline / handles drawn

    def bounds(self) -> Tuple[Optional[float], ...]:
        return (self.x_min, self.x_max, self.y_min, self.y_max, self.z_min, self.z_max)

    def validate(self) -> None:
        for lo, hi, ax in ((self.x_min, self.x_max, "x"), (self.y_min, self.y_max, "y"), (self.z_min, self.z_max, "z")):
            if lo is not None and hi is not None and lo >= hi:
                raise ValueError(f"section box {ax}_min must be less than {ax}_max")

    def contains(self, point: Sequence[float]) -> bool:
        """Is the point inside the box (open sides always pass)? A disabled box contains everything."""
        if not self.enabled:
            return True
        for v, lo, hi in zip(point, self.bounds()[0::2], self.bounds()[1::2]):
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                return False
        return True

    def intersects(self, xb: Sequence[float]) -> bool:
        """Does the box [x0,x1,y0,y1,z0,z1] overlap the section box (so it stays at least partly visible)?"""
        if not self.enabled:
            return True
        for i, (lo, hi) in enumerate(zip(self.bounds()[0::2], self.bounds()[1::2])):
            b0, b1 = xb[2 * i], xb[2 * i + 1]
            if (lo is not None and b1 < lo) or (hi is not None and b0 > hi):
                return False
        return True

    def clip_planes(self) -> List[Tuple[str, float, str]]:
        """``(axis, value, keep)`` per closed side; ``keep`` is the side that stays ('above' or 'below')."""
        out = []
        for ax, lo, hi in zip(AXES, self.bounds()[0::2], self.bounds()[1::2]):
            if lo is not None:
                out.append((ax, lo, "above"))
            if hi is not None:
                out.append((ax, hi, "below"))
        return out if self.enabled else []

    def to_dict(self) -> Dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionBox":
        keys = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in keys})


@dataclass
class SavedView:
    """A named viewpoint: camera, section box and which entity types are shown."""
    name: str
    description: str = ""
    camera: Dict[str, Any] = field(default_factory=dict)
    section_box: Optional[Dict[str, Any]] = None
    hidden_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "camera": dict(self.camera),
                "section_box": dict(self.section_box) if self.section_box else None,
                "hidden_types": list(self.hidden_types)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SavedView":
        return cls(name=data["name"], description=data.get("description", ""),
                   camera=dict(data.get("camera") or {}),
                   section_box=dict(data["section_box"]) if data.get("section_box") else None,
                   hidden_types=list(data.get("hidden_types") or []))
