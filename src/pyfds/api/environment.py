"""Initial conditions and wind.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence, TYPE_CHECKING

from .base import _CollectionManager

if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class InitManager(_CollectionManager):
    """Manage initial-conditions regions (&INIT) — also used for
    volumetric particle clouds (set part_id + n_particles/n_particles_pua
    on the same entity; FDS has no separate namelist for that)."""
    def __init__(self, api):
        from pyfds.domain.model import Init
        super().__init__(api, Init)

    def add_init(self, xb: List[float], **kwargs) -> Any:
        from pyfds.domain.model import Init
        init = Init(
            x_min=float(xb[0]), x_max=float(xb[1]),
            y_min=float(xb[2]), y_max=float(xb[3]),
            z_min=float(xb[4]), z_max=float(xb[5]),
            **kwargs,
        )
        self.add(init)
        return init

    def add_particle_cloud(self, xb: List[float], part_id: str, n_particles: Optional[int] = None,
                           n_particles_pua: Optional[float] = None, **kwargs) -> Any:
        """Volumetric particle cloud: an INIT box with ``PART_ID`` and either a fixed particle
        count or a number per unit area (FDS needs exactly one of them)."""
        if (n_particles is None) == (n_particles_pua is None):
            raise ValueError("give exactly one of n_particles and n_particles_pua")
        if (n_particles or n_particles_pua) <= 0:
            raise ValueError("the particle count must be positive")
        if not any(p.name == part_id for p in self._project.particles):
            raise KeyError(f"particle class {part_id!r} not found")
        return self.add_init(xb, part_id=part_id, n_particles=n_particles,
                             n_particles_pua=n_particles_pua, **kwargs)


class WindManager:
    """
    Atmospheric wind profile tools.

    Accessible via ``api.wind``.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def log_law(self, z_ref: float, u_ref: float, z0: float, **kwargs) -> Any:
        """
        Build a log-law ABL profile and add ``WindProfile`` + ``Ramp`` to project.

        Returns the ``WindProfile`` entity.
        """
        from pyfds.domain.wind_tools import WindTools
        from pyfds.automation.commands import AddEntityCommand
        wind, ramps = WindTools.log_law_profile(z_ref, u_ref, z0, **kwargs)
        self._api.history.execute(AddEntityCommand(self._api.project, wind))
        for r in ramps:
            self._api.history.execute(AddEntityCommand(self._api.project, r))
        return wind

    def power_law(self, z_ref: float, u_ref: float, alpha: float, **kwargs) -> Any:
        """
        Build a power-law ABL profile and add entities to project.

        Returns the ``WindProfile`` entity.
        """
        from pyfds.domain.wind_tools import WindTools
        from pyfds.automation.commands import AddEntityCommand
        wind, ramps = WindTools.power_law_profile(z_ref, u_ref, alpha, **kwargs)
        self._api.history.execute(AddEntityCommand(self._api.project, wind))
        for r in ramps:
            self._api.history.execute(AddEntityCommand(self._api.project, r))
        return wind

    def gust_ramp(self, base_speed: float, gust_speed: float,
                  t_start: float, t_peak: float, t_end: float,
                  ramp_id: str = "WIND_GUST") -> Any:
        """Build a triangular gust ramp and add it to the project."""
        from pyfds.domain.wind_tools import WindTools
        from pyfds.automation.commands import AddEntityCommand
        r = WindTools.gust_ramp(base_speed, gust_speed, t_start, t_peak, t_end, ramp_id)
        self._api.history.execute(AddEntityCommand(self._api.project, r))
        return r


class EnvironmentManager:
    """Ambient conditions and gravity: ``api.environment`` (SIM-03).

    Every setter validates first and is ONE undo step."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    @property
    def _misc(self):
        return self._api.project.misc

    def get(self) -> dict:
        m = self._misc
        return {"temperature": m.tmpa, "pressure": m.p_inf, "humidity": m.humidity,
                "gravity": tuple(m.gvec), "gravity_ramps": (m.ramp_gx, m.ramp_gy, m.ramp_gz)}

    def _set(self, label: str, **fields) -> dict:
        from pyfds.automation.commands import ModifyPropertyCommand
        with self._api.history.transaction(label):
            for k, v in fields.items():
                if getattr(self._misc, k) != v:
                    self._api.history.execute(ModifyPropertyCommand(self._misc, k, v))
        return self.get()

    def set_ambient(self, temperature: Optional[float] = None, pressure: Optional[float] = None,
                    humidity: Optional[float] = None) -> dict:
        """Ambient temperature (deg C), pressure (Pa) and relative humidity (%)."""
        if temperature is not None and not -100 < temperature < 200:
            raise ValueError("temperature must be between -100 and 200 deg C")
        if pressure is not None and not 10_000 < pressure < 200_000:
            raise ValueError("pressure must be between 10 kPa and 200 kPa")
        if humidity is not None and not 0 <= humidity <= 100:
            raise ValueError("humidity must be 0-100 %")
        new = {k: v for k, v in (("tmpa", temperature), ("p_inf", pressure), ("humidity", humidity)) if v is not None}
        return self._set("set ambient conditions", **new)

    def set_gravity(self, vector: Optional[Sequence[float]] = None, ramp_x: Optional[str] = ...,
                    ramp_y: Optional[str] = ..., ramp_z: Optional[str] = ...) -> dict:
        """Gravity vector (m/s2) and/or per-axis time ramps. Pass a ramp id to set it, ``None`` to clear it,
        leave it out to keep it. Ramps must already exist."""
        new: dict = {}
        if vector is not None:
            if len(vector) != 3:
                raise ValueError("gravity needs three components")
            new["gvec"] = tuple(float(v) for v in vector)
        ids = {r.name for r in self._api.project.ramps}
        for key, val in (("ramp_gx", ramp_x), ("ramp_gy", ramp_y), ("ramp_gz", ramp_z)):
            if val is ...:
                continue
            if val is not None and val not in ids:
                raise KeyError(f"ramp {val!r} not found")
            new[key] = val
        return self._set("set gravity", **new)
