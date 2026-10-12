"""Initial conditions and wind profiles."""
from __future__ import annotations

from .base import FdsEntity


from typing import List, Optional, Tuple


class Init(FdsEntity):
    """&INIT namelist — initial conditions in a region."""
    name: str = "DefaultInit"
    x_min: float = 0.0; x_max: float = 1.0
    y_min: float = 0.0; y_max: float = 1.0
    z_min: float = 0.0; z_max: float = 1.0
    temperature: Optional[float] = None
    density: Optional[float] = None
    spec_id: Optional[str] = None
    mass_fraction: Optional[float] = None
    part_id: Optional[str] = None
    n_particles: Optional[int] = None
    n_particles_pua: Optional[float] = None
    # Phase 1 additions
    shape: str = "BLOCK"                                        # BLOCK, SPHERE, CONE, RING
    radius: Optional[float] = None                              # sphere/cone/ring radius
    xyz_center: Optional[Tuple[float, float, float]] = None     # center for SPHERE/RING shape
    # Multi-species initial conditions (parallel lists; FDS SPEC_ID(N), MASS_FRACTION(N))
    spec_ids: Optional[List[str]] = None
    mass_fractions: Optional[List[float]] = None


class WindProfile(FdsEntity):
    """&WIND namelist — atmospheric boundary layer wind profile for outdoor fire modeling."""
    name: str = "DefaultWind"
    speed: float = 0.0                          # reference wind speed (m/s)
    direction: float = 270.0                    # wind direction (degrees from North, 270=Westerly)
    z_ref: float = 10.0                         # reference height (m)
    z0: Optional[float] = None                  # aerodynamic roughness length (m)
    l: Optional[float] = None                   # Obukhov length (m, stability parameter)
    ustar: Optional[float] = None               # friction velocity (m/s)
    ramp_id: Optional[str] = None               # time-varying speed via RAMP
    latitude: Optional[float] = None            # latitude for Coriolis effects
    l_inf: Optional[float] = None               # mixing-layer height (m)
