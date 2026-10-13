"""Turn a dark-on-light floor-plan raster into wall boxes (IMP-04, "create geometry from image / PDF").

Pure numpy. The picture is cut into square cells of *cell* metres; a cell is solid when enough of its
pixels are dark, and runs of solid cells are merged into the fewest rectangles that a greedy
row-by-row sweep finds.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

Rect = Tuple[float, float, float, float]       # x_min, x_max, y_min, y_max


def solid_cells(gray: np.ndarray, px_per_m: float, cell: float, threshold: int = 128,
                min_fill: float = 0.3) -> np.ndarray:
    """Boolean grid (rows = +Y upward, columns = +X) of cells holding enough dark pixels."""
    if gray.ndim != 2:
        raise ValueError("gray must be a 2-D array")
    if px_per_m <= 0 or cell <= 0:
        raise ValueError("px_per_m and cell must be positive")
    step = max(1, int(round(cell * px_per_m)))
    h, w = gray.shape
    rows, cols = -(-h // step), -(-w // step)
    pad = np.full((rows * step, cols * step), 255, dtype=float)
    pad[:h, :w] = gray
    dark = (pad < threshold).reshape(rows, step, cols, step).mean(axis=(1, 3))
    return dark[::-1] >= min_fill                       # image row 0 is the top; flip to Y-up


def merge_rects(grid: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Greedy rectangles ``(col0, col1, row0, row1)`` (end-exclusive) covering every True cell once."""
    grid = grid.copy()
    out = []
    rows, cols = grid.shape
    for r in range(rows):
        c = 0
        while c < cols:
            if not grid[r, c]:
                c += 1
                continue
            c1 = c
            while c1 < cols and grid[r, c1]:
                c1 += 1
            r1 = r + 1
            while r1 < rows and grid[r1, c:c1].all():
                r1 += 1
            grid[r:r1, c:c1] = False
            out.append((c, c1, r, r1))
            c = c1
    return out


def trace(gray: np.ndarray, *, width_m: float, origin=(0.0, 0.0), cell: float = 0.1, threshold: int = 128,
          min_fill: float = 0.3, max_boxes: int = 5000) -> List[Rect]:
    """Wall rectangles in metres for a picture that is *width_m* wide with its lower-left at *origin*."""
    if width_m <= 0:
        raise ValueError("width_m must be positive")
    px_per_m = gray.shape[1] / width_m
    grid = solid_cells(gray, px_per_m, cell, threshold, min_fill)
    step = max(1, int(round(cell * px_per_m))) / px_per_m
    rects = merge_rects(grid)
    if len(rects) > max_boxes:
        raise ValueError(f"the plan would make {len(rects)} boxes (limit {max_boxes}); use a larger cell, "
                         "a lower threshold, or clean up the picture")
    ox, oy = origin
    return [(ox + c0 * step, ox + c1 * step, oy + r0 * step, oy + r1 * step) for c0, c1, r0, r1 in rects]
