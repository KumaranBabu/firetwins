"""Multi-floor viewing (phase V8): split a model into floors and lay them out so each can be seen.

Floors are given by the Z of their floor level. Everything below the second floor level belongs to the
bottom floor, everything from the top level up belongs to the top floor, the rest by the level at or below.
``vertical`` stacks the floors with a gap between them; ``horizontal`` lays them flat on a square grid, the
lowest floor at the upper left. ``clip_walls`` hides anything higher than the floor level plus *wall_height*.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .model import FloorSettings


def floor_index(floors: Sequence[float], z: float) -> int:
    """Index of the floor a height belongs to (0 = bottom)."""
    if not floors:
        return 0
    return max(int(np.searchsorted(np.asarray(floors, dtype=float), z + 1e-9, side="right")) - 1, 0)


def set_floors(settings: FloorSettings, levels: Sequence[float]) -> None:
    lv = sorted(float(z) for z in levels)
    if len(set(lv)) != len(lv):
        raise ValueError("two floors cannot be at the same level")
    settings.floors = lv
    if settings.visible is not None:
        settings.visible = [i for i in settings.visible if i < len(lv)]


def validate(settings: FloorSettings) -> List[str]:
    out = []
    if settings.layout not in ("vertical", "horizontal"):
        out.append("layout must be vertical or horizontal")
    if settings.separation < 0:
        out.append("separation must not be negative")
    if settings.clip_walls and settings.wall_height <= 0:
        out.append("wall_height must be positive")
    return out


def set_visible(settings: FloorSettings, floors: Optional[Sequence[int]]) -> None:
    """Show only these floors (``None`` = all)."""
    if floors is None:
        settings.visible = None
        return
    bad = [i for i in floors if not 0 <= i < max(len(settings.floors), 1)]
    if bad:
        raise IndexError(f"no floor {bad[0]}")
    settings.visible = sorted(set(floors))


def floors_for_selection(settings: FloorSettings, z_min: float, z_max: float) -> List[int]:
    """Show Floors for Selection: the floors the selected objects' Z extent touches."""
    return list(range(floor_index(settings.floors, z_min), floor_index(settings.floors, z_max) + 1))


class FloorLayout:
    """Moves points to where their floor is drawn, and says which points are visible."""

    def __init__(self, settings: FloorSettings, bounds: Sequence[float]) -> None:
        bad = validate(settings)
        if bad:
            raise ValueError("; ".join(bad))
        self.s = settings
        self.bounds = tuple(bounds)
        self.n = max(len(settings.floors), 1)
        self.cols = max(int(math.ceil(math.sqrt(self.n))), 1)
        self.width = bounds[1] - bounds[0]
        self.depth = bounds[3] - bounds[2]

    @property
    def active(self) -> bool:
        return len(self.s.floors) > 1

    def offset(self, i: int) -> Tuple[float, float, float]:
        s = self.s
        if not self.active:
            return (0.0, 0.0, 0.0)
        if s.layout == "vertical":
            return (0.0, 0.0, i * s.separation)
        r, c = divmod(i, self.cols)
        level = s.floors[i] if i < len(s.floors) else 0.0
        return (c * (self.width + s.separation), -r * (self.depth + s.separation), -level)

    def is_visible(self, i: int) -> bool:
        return self.s.visible is None or i in self.s.visible

    def apply(self, points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """``(moved points, keep mask)``: points on hidden floors or above the clipped wall height are not kept."""
        p = np.asarray(points, dtype=float).reshape(-1, 3)
        if not self.active:
            return p.copy(), np.ones(len(p), dtype=bool)
        idx = np.array([floor_index(self.s.floors, z) for z in p[:, 2]])
        off = np.array([self.offset(i) for i in range(self.n)])
        moved = p + off[idx]
        keep = np.array([self.is_visible(int(i)) for i in idx])
        if self.s.clip_walls:
            levels = np.array(self.s.floors)[idx]
            keep &= p[:, 2] <= levels + self.s.wall_height + 1e-9
        return moved, keep

    def labels(self) -> List[Tuple[str, Tuple[float, float, float]]]:
        """Floor names with a position above each floor (shown in the horizontal layout)."""
        out = []
        for i in range(len(self.s.floors)):
            ox, oy, oz = self.offset(i)
            out.append((f"Floor {i + 1}", (self.bounds[0] + ox, self.bounds[3] + oy, self.s.floors[i] + oz)))
        return out
