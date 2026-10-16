"""Drawable shapes that exist only in the results viewer (the common ones live in ``results.scene_data``)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ..scene_data import GridSurface, PointCloud, TriMesh, VolumeGrid      # re-exported for the viewer

XB = Tuple[float, float, float, float, float, float]


@dataclass
class GeometryBoxes:
    """Obstructions and vents as boxes (the "FDS Actual" / "FDS Requested" geometry sets)."""
    name: str
    boxes: List[XB]
    labels: List[str] = field(default_factory=list)
    colors: List[Tuple[float, float, float]] = field(default_factory=list)
    kind: str = "obstruction"                  # obstruction | vent | mesh


@dataclass
class DevicePoints:
    """Devices at one moment: where each is, its recorded value and whether it has been activated."""
    name: str
    names: List[str]
    points: np.ndarray                         # (n, 3)
    values: np.ndarray                         # (n,) NaN where the run recorded nothing for the device
    units: List[str]
    quantities: List[str]
    active: List[bool]
    radius: float = 0.05                       # drawing size in metres, scaled to the model

    def label(self, i: int) -> str:
        v = self.values[i]
        text = "" if v != v else f" {v:.4g} {self.units[i]}".rstrip()
        return f"{self.names[i]}{text}" + (" (activated)" if self.active[i] else "")


@dataclass
class VectorField:
    """Arrows on a slice: where they start, which way they point, and the value that colours them."""
    name: str
    quantity: str
    units: str
    points: np.ndarray                         # (n, 3)
    vectors: np.ndarray                        # (n, 3) velocity
    values: Optional[np.ndarray] = None        # (n,) colour quantity (speed when None)


@dataclass
class ErrorBoxes:
    """Cells with the largest numerical error at the current time (red boxes)."""
    name: str
    boxes: List[XB]
    values: List[float] = field(default_factory=list)


@dataclass
class RectilinearVolume:
    """Node values on a (possibly stretched) rectilinear grid: ``values[i, j, k]`` at ``(x[i], y[j], z[k])``."""
    name: str
    quantity: str
    units: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    kind: str = "scalar"                       # scalar | smoke | fire
    extinction: Optional[np.ndarray] = None    # smoke: 1/m per node (the viewer scales it by opacity and step length)

    def cell_size(self) -> float:
        return float(np.mean([np.diff(a).mean() for a in (self.x, self.y, self.z) if len(a) > 1]))

    def bounds(self) -> XB:
        return (float(self.x[0]), float(self.x[-1]), float(self.y[0]), float(self.y[-1]), float(self.z[0]),
                float(self.z[-1]))
