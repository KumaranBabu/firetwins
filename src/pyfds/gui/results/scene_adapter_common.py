"""Scene adapter constants and mesh helpers."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyvista as pv


BACKGROUND = "#1c1e22"


def _lut(bar, name: str = "q") -> pv.LookupTable:
    tab = (bar.table() * 255).astype(np.uint8)
    lut = pv.LookupTable(values=tab, scalar_range=(bar.lo, bar.hi), n_values=len(tab))
    lut.below_range_color = None
    lut.above_range_color = None
    return lut


def _box_mesh(boxes) -> Optional[pv.PolyData]:
    parts = [pv.Box(bounds=b) for b in boxes if b[1] >= b[0] and b[3] >= b[2] and b[5] >= b[4]]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else parts[0].merge(parts[1:], merge_points=False)
