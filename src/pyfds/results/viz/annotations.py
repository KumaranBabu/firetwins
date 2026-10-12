"""Dimensions and labels (phase V9): the geometry behind the Dimension tool and the Label tool."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .model import Dimension, Label, ResultsVisualization

Vec = Tuple[float, float, float]
MODES = ("feature", "along_x", "along_y", "along_z")


@dataclass
class DimensionGeometry:
    """What to draw: the dimension line, the two extension lines, where the text goes and what it says."""
    start: Vec
    end: Vec
    extension: List[Tuple[Vec, Vec]]
    text_at: Vec
    value: float
    text: str


def format_value(value: float, precision: int = 3) -> str:
    return f"{value:.{max(precision, 0)}f} m"


def dimension_geometry(d: Dimension, precision: int = 3) -> DimensionGeometry:
    """Length (along the feature or projected on one axis) and the line to draw, offset by ``d.offset``."""
    p1, p2 = np.array(d.p1, dtype=float), np.array(d.p2, dtype=float)
    if d.mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    delta = p2 - p1
    if d.mode == "feature":
        length = float(np.linalg.norm(delta))
        if length == 0:
            raise ValueError("the two points are the same")
        u = delta / length
        n = np.cross(u, [0.0, 0.0, 1.0])
        if np.linalg.norm(n) < 1e-9:
            n = np.cross(u, [1.0, 0.0, 0.0])
        n = n / np.linalg.norm(n)
        a, b = p1 + n * d.offset, p2 + n * d.offset
        value = length
    else:
        axis = "xyz".index(d.mode[-1])
        value = abs(float(delta[axis]))
        if value == 0:
            raise ValueError(f"the points have the same {d.mode[-1].upper()}: nothing to measure along that axis")
        e = np.zeros(3)
        e[axis] = 1.0
        other = [i for i in range(3) if i != axis]
        n = np.zeros(3)
        n[other[0] if abs(delta[other[0]]) >= abs(delta[other[1]]) else other[1]] = 1.0 if d.offset >= 0 else -1.0
        a = p1 + n * abs(d.offset)
        b = a + e * delta[axis]
    mid = (a + b) / 2
    return DimensionGeometry(tuple(a), tuple(b), [(tuple(p1), tuple(a)), (tuple(p2), tuple(b))], tuple(mid), value,
                             format_value(value, precision))                                  # type: ignore[arg-type]


def add_dimension(viz: ResultsVisualization, p1: Sequence[float], p2: Sequence[float], mode: str = "feature",
                  offset: float = 0.0) -> Dimension:
    d = Dimension(tuple(float(v) for v in p1), tuple(float(v) for v in p2), mode, float(offset))   # type: ignore
    dimension_geometry(d)                                                                          # validates
    viz.dimensions.append(d)
    return d


def add_label(viz: ResultsVisualization, text: str, anchor: Sequence[float], position: Optional[Sequence[float]] = None) -> Label:
    if not text.strip():
        raise ValueError("a label needs text")
    lab = Label(text, tuple(float(v) for v in anchor),                                              # type: ignore
                tuple(float(v) for v in position) if position is not None else None)               # type: ignore
    viz.labels.append(lab)
    return lab


def remove_annotation(viz: ResultsVisualization, kind: str, index: int) -> None:
    items = {"dimension": viz.dimensions, "label": viz.labels}.get(kind)
    if items is None:
        raise ValueError("kind must be dimension or label")
    del items[index]


def rename_label(viz: ResultsVisualization, index: int, text: str) -> None:
    if not text.strip():
        raise ValueError("a label needs text")
    viz.labels[index].text = text
