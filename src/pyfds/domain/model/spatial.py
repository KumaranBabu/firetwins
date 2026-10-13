"""Spatial entities: meshes, obstructions, vents, holes, zones, GEOM and transforms."""
from __future__ import annotations

from .base import FdsEntity


from typing import List, Optional, Tuple
from pydantic import field_validator


class Mesh(FdsEntity):
    """&MESH namelist."""
    name: str = "DefaultMesh"
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0
    z_min: float = 0.0
    z_max: float = 1.0
    cell_count: Tuple[int, int, int] = (10, 10, 10)
    mpi_processor: Optional[int] = None
    color: Optional[str] = None
    cylindrical: bool = False   # CYLINDRICAL=.TRUE. for axisymmetric meshes
    #: Position in the written file (ascending). FDS gives an earlier mesh priority where
    #: meshes overlap, so this is PyroSim's mesh *order*. ``None`` = keep project order.
    priority: Optional[int] = None
    description: str = ""       # free text for the user; never written to FDS

    @field_validator("x_max")
    @classmethod
    def check_x_bounds(cls, v, info):
        xmin = info.data.get("x_min", float("-inf"))
        if v <= xmin:
            raise ValueError(f"x_max ({v}) must be > x_min ({xmin})")
        return v


class Obstruction(FdsEntity):
    """&OBST namelist."""
    name: str = "DefaultObst"
    x_min: float = 0.0; x_max: float = 1.0
    y_min: float = 0.0; y_max: float = 1.0
    z_min: float = 0.0; z_max: float = 1.0
    surface_id: str = "INERT"
    #: 3 entries = (top, sides, bottom) -> SURF_IDS; 6 entries = one per face -> SURF_ID6 (FDS order)
    surface_ids: Optional[List[str]] = None
    color: str = "GRAY"
    allow_vent: bool = False
    thicken: bool = False
    transparency: float = 0.0
    texture_origin: Optional[Tuple[float, float, float]] = None
    mult_id: Optional[str] = None
    ctrl_id: Optional[str] = None
    devc_id: Optional[str] = None
    rgb: Optional[Tuple[int, int, int]] = None
    # FDS flags that default to .TRUE. / unset; ``None`` = not specified (not written)
    permit_hole: Optional[bool] = None   # PERMIT_HOLE
    removable: Optional[bool] = None     # REMOVABLE
    bulk_density: Optional[float] = None # BULK_DENSITY, kg/m3 (burn-away mass)


class Hole(FdsEntity):
    """&HOLE namelist — cuts a rectangular opening in obstructions."""
    name: str = "DefaultHole"
    x_min: float = 0.0; x_max: float = 1.0
    y_min: float = 0.0; y_max: float = 1.0
    z_min: float = 0.0; z_max: float = 1.0
    ctrl_id: Optional[str] = None


class Mult(FdsEntity):
    """&MULT namelist — multiplier for array copies of an obstruction."""
    name: str = "DefaultMult"
    dx: float = 0.0; dy: float = 0.0; dz: float = 0.0
    dx0: float = 0.0; dy0: float = 0.0; dz0: float = 0.0
    i_lower: int = 0; i_upper: int = 0
    j_lower: int = 0; j_upper: int = 0
    k_lower: int = 0; k_upper: int = 0


class Vent(FdsEntity):
    """&VENT namelist."""
    name: str = "DefaultVent"
    x_min: float = 0.0; x_max: float = 1.0
    y_min: float = 0.0; y_max: float = 1.0
    z_min: float = 0.0; z_max: float = 1.0
    surface_id: str = "OPEN"
    color: Optional[str] = None
    rgb: Optional[Tuple[int, int, int]] = None
    ctrl_id: Optional[str] = None
    devc_id: Optional[str] = None
    dynamic_pressure: Optional[float] = None
    transparency: float = 0.0
    # Extended VENT fields (PyroSim parity)
    ior: Optional[int] = None                          # IOR ±1/±2/±3 — oriented normal for mesh-interior vents
    uvw: Optional[Tuple[float, float, float]] = None   # UVW — velocity vector for HVAC inlet
    spread_rate: Optional[float] = None                # SPREAD_RATE (m/s) — fire spread across vent
    tmp_exterior: Optional[float] = None               # TMP_EXTERIOR (°C) — outdoor temperature for exterior BC


class Zone(FdsEntity):
    """&ZONE namelist — pressure zone definition.

    FDS requires a single interior XYZ point (not a bounding box) to identify
    the zone.  The x_min/x_max/... fields are kept for backwards compatibility
    with existing code but ``xyz`` takes precedence in the writer when set.
    """
    name: str = "DefaultZone"
    x_min: float = 0.0; x_max: float = 1.0
    y_min: float = 0.0; y_max: float = 1.0
    z_min: float = 0.0; z_max: float = 1.0
    # Preferred: single interior point required by FDS &ZONE XYZ=
    xyz: Optional[Tuple[float, float, float]] = None
    leak_areas: Optional[List[float]] = None   # LEAK_AREAS array (pairs per zone boundary)


class Geom(FdsEntity):
    """&GEOM namelist — complex geometry defined by vertices, faces, or file."""
    name: str = "DefaultGeom"
    surf_id: str = "INERT"
    surf_ids: Optional[List[str]] = None
    verts: Optional[List[Tuple[float, float, float]]] = None
    faces: Optional[List[Tuple[int, int, int]]] = None
    is_terrain: bool = False
    binary_file: Optional[str] = None
    read_binary: bool = False
    move_id: Optional[str] = None
    component_only: bool = False
    #: Where the shape came from (CAD/BIM import). Editor data, never written to the FDS file.
    bim_type: Optional[str] = None      # e.g. "IfcWall"
    bim_name: Optional[str] = None      # the element's name in the source file
    bim_storey: Optional[str] = None    # building storey it belongs to
    source_file: Optional[str] = None

    def bbox(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        # Base FdsEntity.bbox() only understands x_min../xyz-style entities —
        # a Geom's extent lives in its vertex cloud instead.
        if not self.verts:
            return None
        xs = [v[0] for v in self.verts]
        ys = [v[1] for v in self.verts]
        zs = [v[2] for v in self.verts]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


class MeshTransform(FdsEntity):
    """&TRNX/TRNY/TRNZ namelist — non-uniform mesh cell stretching control point."""
    name: str = "DefaultTrn"
    direction: str = "X"     # 'X', 'Y', or 'Z' — determines which TRN namelist is written
    mesh_number: int = 1
    ideriv: int = 0           # 0=piecewise uniform, 1=stretching function
    cc: float = 0.0           # physical coordinate value
    pc: float = 0.5           # fractional position within the mesh (0..1)


class Move(FdsEntity):
    """&MOVE namelist — rigid body motion applied to &GEOM or &OBST objects."""
    name: str = "DefaultMove"
    # Translation
    x0: float = 0.0; y0: float = 0.0; z0: float = 0.0  # rotation origin
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)  # rotation axis
    omega: float = 0.0                          # angular velocity (rad/s)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # translational velocity (m/s)
    # Static transformation (applied at t=0)
    rotation_angle: Optional[float] = None      # one-time rotation angle (degrees)
    dx: float = 0.0; dy: float = 0.0; dz: float = 0.0  # one-time translation offset
    scale: float = 1.0                          # uniform scale factor
