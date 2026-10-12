"""
PyFDS Meshing Base
==================
Abstract contracts, data types, and protocols shared by every meshing engine.

All meshing engines subclass ``MeshingEngineBase``.
All operations use the request/result types defined here.
This module has no external dependencies beyond numpy and stdlib.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

import numpy as np

from pyfds.domain.geometry import BoundingBox


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class LicenseType(str, Enum):
    OPEN_SOURCE = "open_source"
    DUAL        = "dual"        # free for non-commercial; paid for commercial use
    COMMERCIAL  = "commercial"  # paid license required


class ElementType(str, Enum):
    HEX8   = "hex8"    # structured hexahedra (FDS native)
    TET4   = "tet4"    # linear tetrahedra
    TRI3   = "tri3"    # triangular surface element
    QUAD4  = "quad4"   # quadrilateral surface element
    WEDGE6 = "wedge6"  # prism element (boundary layers)


# ---------------------------------------------------------------------------
# Engine capabilities
# ---------------------------------------------------------------------------

@dataclass
class EngineCapabilities:
    """Declares which operations an engine supports."""
    structured_mesh:   bool = False   # rectilinear FDS &MESH blocks
    surface_mesh:      bool = False   # triangulated surface meshing
    volume_mesh:       bool = False   # tet/hex volume meshing
    geometry_import:   bool = False   # CAD file import (STL, STEP, IGES …)
    mesh_refinement:   bool = False   # local size control / grading
    mesh_optimization: bool = False   # post-generation quality improvement
    boundary_layers:   bool = False   # prism layer insertion near walls
    parallel:          bool = False   # multi-core meshing
    formats_in:  List[str] = field(default_factory=list)  # accepted file types
    formats_out: List[str] = field(default_factory=list)  # produced file types


@dataclass
class EngineStatus:
    """Runtime detection result for one engine."""
    name:         str
    display_name: str
    available:    bool
    version:      Optional[str]
    priority:     int
    license_type: LicenseType
    capabilities: EngineCapabilities
    error:        Optional[str] = None

    @property
    def license_label(self) -> str:
        return self.license_type.value.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Geometry input types
# ---------------------------------------------------------------------------

@dataclass
class BoundingBoxGeometry:
    """Simple AABB — standard FDS domain input."""
    box: BoundingBox


@dataclass
class SurfaceMeshGeometry:
    """Triangulated surface specified as numpy arrays."""
    vertices:  np.ndarray   # (N, 3) float64
    triangles: np.ndarray   # (M, 3) int32


@dataclass
class FileGeometry:
    """Path to a CAD file (STL, STEP, IGES, GEO, MSH …)."""
    path:   str
    format: str = ""  # auto-detected from extension if empty


GeometryInput = Union[BoundingBoxGeometry, SurfaceMeshGeometry, FileGeometry]


# ---------------------------------------------------------------------------
# Mesh data
# ---------------------------------------------------------------------------

@dataclass
class MeshData:
    """Engine-agnostic raw mesh data returned alongside FDS parameters."""
    vertices:     np.ndarray    # (N, 3) float64
    elements:     np.ndarray    # (M, nodes_per_element) int32
    element_type: ElementType
    quality_min:  Optional[float] = None
    quality_max:  Optional[float] = None
    quality_mean: Optional[float] = None
    engine_name:  str = ""
    generation_time_s: float = 0.0


@dataclass
class FdsStructuredMesh:
    """Parameters for one FDS &MESH namelist block."""
    id:       str
    ijk:      Tuple[int, int, int]
    xb:       List[float]         # [x1, x2, y1, y2, z1, z2]
    mpi_rank: Optional[int] = None


@dataclass
class MeshResult:
    """Returned by every mesh-generation operation."""
    success:     bool
    engine_used: str
    fds_meshes:  List[FdsStructuredMesh]   # non-empty for structured workflows
    mesh_data:   Optional[MeshData] = None  # raw mesh for surface/volume workflows
    warnings:    List[str] = field(default_factory=list)
    errors:      List[str] = field(default_factory=list)
    stats:       Dict[str, Any] = field(default_factory=dict)
    elapsed_s:   float = 0.0

    @property
    def failed(self) -> bool:
        return not self.success

    @classmethod
    def failure(cls, engine: str, error: str) -> "MeshResult":
        return cls(success=False, engine_used=engine, fds_meshes=[], errors=[error])


@dataclass
class GeometryResult:
    """Returned by geometry import/repair operations."""
    success:      bool
    engine_used:  str
    surface_mesh: Optional[MeshData] = None
    bounding_box: Optional[BoundingBox] = None
    warnings:     List[str] = field(default_factory=list)
    errors:       List[str] = field(default_factory=list)
    elapsed_s:    float = 0.0

    @classmethod
    def failure(cls, engine: str, error: str) -> "GeometryResult":
        return cls(success=False, engine_used=engine, errors=[error])


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------

@dataclass
class StructuredMeshRequest:
    """Generate FDS-compatible structured hexahedral mesh blocks."""
    domain:             BoundingBox
    target_cell_size:   float
    n_mpi_ranks:        int = 1
    force_poisson:      bool = True
    aspect_ratio_limit: float = 4.0
    split_axis:         Optional[str] = None   # 'X', 'Y', 'Z', or None for auto
    preferred_engine:   Optional[str] = None
    mesh_id_prefix:     str = "MESH"


@dataclass
class SurfaceMeshRequest:
    """Generate a triangulated surface mesh."""
    geometry:           GeometryInput
    target_edge_length: float
    min_edge_length:    Optional[float] = None
    max_edge_length:    Optional[float] = None
    curvature_adapt:    bool = True
    preferred_engine:   Optional[str] = None


@dataclass
class VolumeMeshRequest:
    """Generate an unstructured volume mesh (for FireFOAM / OpenFOAM)."""
    geometry:          GeometryInput
    target_cell_size:  float
    element_type:      ElementType = ElementType.TET4
    boundary_layers:   bool = False
    n_boundary_layers: int = 3
    min_quality:       float = 0.2   # minimum acceptable cell quality [0–1]
    preferred_engine:  Optional[str] = None


@dataclass
class GeometryImportRequest:
    """Import and optionally repair a geometry file."""
    file_path:        str
    repair:           bool = True
    preferred_engine: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract base class for all engine adapters
# ---------------------------------------------------------------------------

class MeshingEngineBase(ABC):
    """
    Abstract base for every meshing engine adapter.

    Subclasses declare class-level attributes (name, priority, capabilities …)
    and implement only the operations their backend supports.  Unsupported
    operations raise ``NotImplementedError``; callers should check
    ``capabilities`` first or let the registry select a capable engine.

    Detection
    ---------
    ``EngineRegistry`` calls ``cls.is_available()`` before instantiating.
    This must never raise — return False on any import/probe error.
    """

    name:         ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    priority:     ClassVar[int] = 0
    license_type: ClassVar[LicenseType] = LicenseType.OPEN_SOURCE
    capabilities: ClassVar[EngineCapabilities]   # required on every subclass

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True if this engine can be used on the current system."""

    @classmethod
    def get_version(cls) -> Optional[str]:
        """Return a version string, or None if unavailable."""
        return None

    @classmethod
    def is_licensed(cls) -> bool:
        """True when a commercial license is active (override in commercial adapters)."""
        return cls.license_type == LicenseType.COMMERCIAL

    def generate_structured_mesh(self, request: StructuredMeshRequest) -> MeshResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support structured meshing"
        )

    def generate_surface_mesh(self, request: SurfaceMeshRequest) -> MeshResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support surface meshing"
        )

    def generate_volume_mesh(self, request: VolumeMeshRequest) -> MeshResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support volume meshing"
        )

    def import_geometry(self, request: GeometryImportRequest) -> GeometryResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support geometry import"
        )

    def __repr__(self) -> str:
        ver = self.__class__.get_version() or "?"
        return f"<{self.__class__.__name__} name={self.__class__.name!r} v={ver}>"


# ---------------------------------------------------------------------------
# Duck-typed Protocol (for plugin authors who prefer no inheritance)
# ---------------------------------------------------------------------------

@runtime_checkable
class MeshingEngine(Protocol):
    """
    Protocol equivalent of ``MeshingEngineBase``.

    Plugin authors may implement this via duck typing instead of subclassing.
    The ``EngineRegistry`` checks ``isinstance(obj, MeshingEngine)`` for
    runtime validation of externally-supplied engines.
    """
    name:         str
    display_name: str
    priority:     int
    license_type: LicenseType
    capabilities: EngineCapabilities

    @classmethod
    def is_available(cls) -> bool: ...
    @classmethod
    def get_version(cls) -> Optional[str]: ...
    def generate_structured_mesh(self, request: StructuredMeshRequest) -> MeshResult: ...
    def generate_surface_mesh(self, request: SurfaceMeshRequest) -> MeshResult: ...
    def generate_volume_mesh(self, request: VolumeMeshRequest) -> MeshResult: ...
    def import_geometry(self, request: GeometryImportRequest) -> GeometryResult: ...
