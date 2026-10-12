"""Records produced by the .smv parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SmvGrid:
    """One FDS mesh as represented in the SMV file."""
    mesh_id: int                      # 1-based mesh index
    chid: str = ""
    n_cells: Tuple[int, int, int] = (0, 0, 0)   # (nx, ny, nz)
    extents: Tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # xlo,xhi,ylo,yhi,zlo,zhi
    x_coords: List[float] = field(default_factory=list)
    y_coords: List[float] = field(default_factory=list)
    z_coords: List[float] = field(default_factory=list)


@dataclass
class SmvSlice:
    """Reference to a ``*.sf`` slice file in the SMV."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str
    i1: int = 0; i2: int = 0
    j1: int = 0; j2: int = 0
    k1: int = 0; k2: int = 0
    cell_centred: bool = False

    @property
    def is_2d(self) -> bool:
        return (self.i1 == self.i2 or
                self.j1 == self.j2 or
                self.k1 == self.k2)


@dataclass
class SmvBoundary:
    """Reference to a ``*.bf`` boundary file in the SMV."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str


@dataclass
class SmvIsosurface:
    """Reference to a ``*.iso`` / ``*.ge1`` isosurface file."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str
    level: float = 0.0


@dataclass
class SmvPlot3D:
    """Reference to a ``*.q`` Plot3D file."""
    filepath: str
    mesh_id: int
    quantities: List[str] = field(default_factory=list)   # up to 5


@dataclass
class SmvSmoke3D:
    """Reference to a ``*.s3d`` smoke-3D file."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str


@dataclass
class SmvParticle:
    """Reference to a particle ``*.prt5`` file."""
    filepath: str
    mesh_id: int
    n_classes: int = 0


@dataclass
class SmvDevice:
    """A device/sensor recorded in the SMV."""
    name: str
    quantity: str = ""
    units: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    state: str = ""


@dataclass
class SmvViewpoint:
    """A named camera viewpoint read from the SMV file."""
    name: str
    eye: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    zoom: float = 1.0


@dataclass
class SmvSurface:
    """A surface display record from the SMV file."""
    surface_id: str
    rgb: Tuple[int, int, int] = (128, 128, 128)
    transparency: float = 0.0


@dataclass
class SmvMetadata:
    """All metadata extracted from a ``.smv`` file."""
    smv_filepath: str
    chid: str = ""
    fds_version: str = ""
    title: str = ""
    grids: List[SmvGrid] = field(default_factory=list)
    slices: List[SmvSlice] = field(default_factory=list)
    boundaries: List[SmvBoundary] = field(default_factory=list)
    isosurfaces: List[SmvIsosurface] = field(default_factory=list)
    plot3d: List[SmvPlot3D] = field(default_factory=list)
    smoke3d: List[SmvSmoke3D] = field(default_factory=list)
    particles: List[SmvParticle] = field(default_factory=list)
    devices: List[SmvDevice] = field(default_factory=list)
    viewpoints: List[SmvViewpoint] = field(default_factory=list)
    surfaces: List[SmvSurface] = field(default_factory=list)
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_sections: Dict[str, List[List[str]]] = field(default_factory=dict)

    def slice_quantities(self) -> List[str]:
        return list({s.quantity for s in self.slices})

    def boundary_quantities(self) -> List[str]:
        return list({b.quantity for b in self.boundaries})
