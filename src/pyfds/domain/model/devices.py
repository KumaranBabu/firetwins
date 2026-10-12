"""Devices, controls, properties, output requests and raw text."""
from __future__ import annotations

from .base import FdsEntity


from typing import List, Optional, Tuple
from pydantic import model_validator


class Device(FdsEntity):
    """&DEVC namelist."""
    name: str = "DefaultDevice"
    quantity: str = "TEMPERATURE"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    xyz: Optional[Tuple[float, float, float]] = None  # alternative input

    @model_validator(mode="after")
    def _xyz_sets_xyz(self) -> "Device":
        """``Device(xyz=[...])`` is an accepted way to place a device; the writer and everything else read
        x, y, z, so copy it over (otherwise the device silently ends up at the origin)."""
        if self.xyz is not None and (self.x, self.y, self.z) == (0.0, 0.0, 0.0):
            self.x, self.y, self.z = (float(v) for v in self.xyz)
        return self
    orientation: Optional[Tuple[float, float, float]] = None
    prop_id: Optional[str] = None
    ctrl_id: Optional[str] = None
    setpoint: Optional[float] = None
    initial_state: bool = False
    latch: bool = True
    trip_direction: int = 1
    statistics: Optional[str] = None     # MAX, MIN, MEAN, etc.
    points: Optional[int] = None          # for line sensors
    time_averaged: bool = False
    spatial_statistic: Optional[str] = None
    vd_to_vd: bool = False
    # Phase 1 additions
    quantity2: Optional[str] = None       # second output quantity
    duct_id: Optional[str] = None         # HVAC duct sensor attachment
    # Extended DEVC fields (PyroSim parity)
    xb: Optional[Tuple[float, float, float, float, float, float]] = None  # XB for spatial statistics
    ior: Optional[int] = None             # IOR ±1..±3 — face-normal for wall-mounted device
    surf_id: Optional[str] = None         # SURF_ID — surface the device is mounted on
    conversion_factor: Optional[float] = None  # CONVERSION_FACTOR — output scaling multiplier
    smoothed_data: bool = False           # SMOOTHED_DATA — time-average output
    hide_coordinates: bool = False        # HIDE_COORDINATES — suppress XYZ columns in CSV
    pipe_index: Optional[int] = None      # PIPE_INDEX — water supply network index


class Prop(FdsEntity):
    """&PROP namelist — detector / sprinkler property set."""
    name: str = "DefaultProp"
    quantity: Optional[str] = None
    part_id: Optional[str] = None
    smokeview_id: Optional[str] = None
    smokeview_parameters: Optional[List[float]] = None
    # Sprinkler-specific
    rti: float = 50.0
    c_factor: float = 0.7
    operating_pressure: Optional[float] = None
    spray_angle: Optional[Tuple[float, float]] = None
    flow_rate: Optional[float] = None
    particle_velocity: Optional[float] = None
    offset: float = 0.1
    # Detector-specific
    activation_obscuration: Optional[float] = None
    activation_temperature: Optional[float] = None   # ACTIVATION_TEMPERATURE, C (heat detector / sprinkler link)
    initial_temperature: Optional[float] = None      # INITIAL_TEMPERATURE, C
    length: Optional[float] = None
    characteristic_velocity: Optional[float] = None


class Control(FdsEntity):
    """&CTRL namelist — logic control block."""
    name: str = "DefaultCtrl"
    function_type: str = "CUSTOM"
    input_id: Optional[str] = None
    input_ids: Optional[List[str]] = None
    setpoint: Optional[float] = None
    delay: float = 0.0
    latch: bool = True
    initial_state: bool = False
    on_bound: str = "LOWER"
    n: Optional[int] = None              # for ANY/ALL logic (number required)
    constant: Optional[float] = None
    # Phase 1 additions
    deadband: Optional[Tuple[float, float]] = None  # DEADBAND(1:2) for thermostat logic
    percentile_rank: Optional[float] = None          # PERCENTILE_RANK
    ramp_id: Optional[str] = None                    # RAMP_ID reference


class Slice(FdsEntity):
    """&SLCF namelist."""
    name: str = "DefaultSlice"
    quantity: str = "TEMPERATURE"
    quantity2: Optional[str] = None
    plane: str = "X"
    position: float = 0.0
    vector: bool = False
    cell_centered: bool = False
    # 3D volumetric slice: when set, XB replaces PBX/PBY/PBZ
    xb: Optional[Tuple[float, float, float, float, float, float]] = None


class Smoke3D(FdsEntity):
    """&SM3D namelist — 3-D smoke output (Smokeview smoke / fire rendering)."""
    name: str = "Smoke3D"
    quantity: str = "DENSITY"
    spec_id: Optional[str] = None


class BoundaryFile(FdsEntity):
    """&BNDF namelist."""
    name: str = "DefaultBNDF"
    quantity: str = "WALL TEMPERATURE"
    cell_centered: bool = False


class IsoSurface(FdsEntity):
    """&ISOF namelist."""
    name: str = "DefaultIso"
    quantity: str = "TEMPERATURE"
    value: float = 100.0
    quantity2: Optional[str] = None
    value2: Optional[float] = None


class Text(FdsEntity):
    """Raw text block inserted verbatim into the FDS output."""
    content: str = ""


class Prof(FdsEntity):
    """&PROF namelist — vertical profile output."""
    name: str = "DefaultProf"
    quantity: str = "TEMPERATURE"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    direction: str = "Z"


class Plot3D(FdsEntity):
    """&PL3D namelist — Plot3D output quantity configuration (FDS 5 style)."""
    name: str = "DefaultPL3D"
    quantity: str = "TEMPERATURE"
    velo_index: Optional[int] = None
    spec_id: Optional[str] = None
