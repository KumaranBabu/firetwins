"""HVAC network entities."""
from __future__ import annotations

from .base import FdsEntity


from typing import List, Optional, Tuple
from pydantic import Field


class Hvac(FdsEntity):
    """Legacy &HVAC convenience wrapper (basic duct)."""
    name: str = "DefaultHvac"
    vent_ids: List[str] = Field(default_factory=list)
    diameter: float = 0.5
    length: float = 1.0


class HvacNode(FdsEntity):
    """&NODE namelist."""
    name: str = "DefaultNode"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vent_id: Optional[str] = None
    duct_id: Optional[str] = None
    filter_id: Optional[str] = None
    ambient: bool = False


class HvacDuct(FdsEntity):
    """&DUCT namelist."""
    name: str = "DefaultDuct"
    node_id_1: str = ""
    node_id_2: str = ""
    diameter: float = 0.5
    length: Optional[float] = None
    area: Optional[float] = None
    roughness: float = 0.0001
    loss: Tuple[float, float] = (0.0, 0.0)
    perimeter: Optional[float] = None
    leakage_id: Optional[str] = None
    ctrl_id: Optional[str] = None


class Fan(FdsEntity):
    """&FAN namelist."""
    name: str = "DefaultFan"
    duct_id: str = ""
    #: further ducts driven by this same fan (FDS: several ducts with the same FAN_ID); one object, one set of values
    more_duct_ids: List[str] = Field(default_factory=list)
    ramp_id: Optional[str] = None
    volume_flow_rate: Optional[float] = None
    max_flow: Optional[float] = None
    max_pressure: Optional[float] = None
    ctrl_id: Optional[str] = None
    # Pump curve (pressure vs. flow arrays)
    volume_flow: Optional[List[float]] = None   # VOLUME_FLOW(N) — flow setpoints
    pressure: Optional[List[float]] = None      # PRESSURE(N) — corresponding pressures


class Damper(FdsEntity):
    """&DAMPER namelist."""
    name: str = "DefaultDamper"
    duct_id: str = ""
    ctrl_id: str = ""


class HvacFilter(FdsEntity):
    """&FILTER namelist — particulate filter in HVAC network."""
    name: str = "DefaultFilter"
    duct_id: str = ""
    efficiency: float = 0.9                     # filtration efficiency (0–1)
    loss: float = 0.0                           # pressure loss coefficient
    clean_loss: Optional[float] = None          # clean-filter loss coefficient
    ctrl_id: Optional[str] = None
    node_id: Optional[str] = None               # the node the filter sits at (it needs exactly two ducts)
    more_node_ids: List[str] = Field(default_factory=list)   # further nodes with this same FILTER_ID
    spec_id: Optional[str] = None               # SPEC_ID - the species the filter removes
    loading: Optional[float] = None             # LOADING (kg) the filter starts with
    loading_multiplier: Optional[float] = None  # LOADING_MULTIPLIER (1/kg) in the loss model
    ramp_id: Optional[str] = None               # RAMP_ID - loss vs loading table (instead of LOSS)


class HvacAircoil(FdsEntity):
    """&AIRCOIL namelist — heat exchanger on a duct (cooling/heating coil)."""
    name: str = "DefaultAircoil"
    duct_id: str = ""
    more_duct_ids: List[str] = Field(default_factory=list)   # further ducts with this same AIRCOIL_ID
    effectiveness: float = 0.8                   # heat-exchange effectiveness (0..1)
    coolant_temperature: Optional[float] = None  # COOLANT_TEMPERATURE (deg C)
    coolant_specific_heat: Optional[float] = None  # COOLANT_SPECIFIC_HEAT (kJ/kg/K)
    coolant_mass_flow: Optional[float] = None    # COOLANT_MASS_FLOW (kg/s)
    fixed_q: Optional[float] = None              # FIXED_Q (kW, negative removes heat) instead of the coolant model
    ctrl_id: Optional[str] = None


class HvacLeakage(FdsEntity):
    """&LEAK namelist — duct leakage path between pressure zones."""
    name: str = "DefaultLeakage"
    zone_id_1: str = ""                         # source pressure zone ID
    zone_id_2: str = ""                         # destination pressure zone ID
    area: float = 0.001                         # leakage area (m²)
    crack_id: Optional[str] = None
    vent_id: Optional[str] = None               # VENT_ID - first vent of an FDS leak path
    vent2_id: Optional[str] = None              # VENT2_ID - second vent
    ctrl_id: Optional[str] = None
