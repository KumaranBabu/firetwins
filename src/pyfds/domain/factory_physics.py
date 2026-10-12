"""EntityFactory: reactions, ramps, HRR curves, wind profiles."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class EntityFactoryPhysicsMixin:
    def create_reaction(
        self,
        name: str,
        fuel: str,
        heat_of_combustion: float,
        *,
        soot_yield: float = 0.0,
        co_yield: float = 0.0,
        radiative_fraction: float = 0.35,
    ) -> Any:
        from pyfds.domain.model import Reaction
        return Reaction(
            name=name, fuel=fuel,
            heat_of_combustion=heat_of_combustion,
            soot_yield=soot_yield,
            co_yield=co_yield,
            radiative_fraction=radiative_fraction,
        )

    def create_ramp(
        self,
        name: str,
        times: List[float],
        values: List[float],
    ) -> Any:
        from pyfds.domain.model import Ramp
        return Ramp(name=name, times=times, values=values)

    def create_t_squared_ramp(
        self,
        name: str,
        t_end: float,
        alpha: float = 0.0117,
        n_points: int = 20,
    ) -> Any:
        """Create a t² fire growth ramp (HRR = alpha * t²)."""
        import math
        from pyfds.domain.model import Ramp
        dt = t_end / (n_points - 1)
        times  = [i * dt for i in range(n_points)]
        peak   = alpha * t_end * t_end
        values = [alpha * t * t / peak for t in times]
        return Ramp(name=name, times=times, values=values)

    def create_hrr_curve(
        self,
        name: str,
        hrrpua: float,
        fire_area: float,
        *,
        growth: str = "medium",
        t_growth: Optional[float] = None,
        t_steady: float = 300.0,
        t_decay: float = 120.0,
        n_points: int = 30,
    ) -> Any:
        """
        Build a normalised HRR-vs-time Ramp covering growth → steady → decay.

        The ramp is normalised to peak = 1.0; multiply by HRRPUA on the SURF.

        Parameters
        ----------
        name:
            Ramp ID (referenced by SURF RAMP_Q).
        hrrpua:
            Peak HRRPUA (kW/m²) — informational; used to derive alpha when
            *t_growth* is None.
        fire_area:
            Estimated fire area (m²) — used to scale alpha.
        growth:
            Named t² growth category: 'slow' | 'medium' | 'fast' | 'ultrafast'.
            Ignored when *t_growth* is given explicitly.
        t_growth:
            Override growth phase duration (s).  When provided, *growth* is
            ignored and the curve reaches peak at this time.
        t_steady:
            Duration of the steady-burning phase (s).
        t_decay:
            Duration of the decay phase (s).
        n_points:
            Number of Ramp data points.
        """
        from pyfds.domain.model import Ramp

        _ALPHA = {"slow": 0.00293, "medium": 0.01172, "fast": 0.04689, "ultrafast": 0.18758}
        alpha = _ALPHA.get(growth.lower(), _ALPHA["medium"])
        q_peak = hrrpua * fire_area  # kW

        if t_growth is not None:
            tg = float(t_growth)
        elif q_peak > 0:
            import math
            tg = math.sqrt(q_peak / alpha)
        else:
            tg = 300.0

        t_total = tg + t_steady + t_decay
        dt = t_total / (n_points - 1)
        times: List[float] = []
        values: List[float] = []

        for i in range(n_points):
            t = i * dt
            if t <= tg:
                v = (t / tg) ** 2 if tg > 0 else 0.0
            elif t <= tg + t_steady:
                v = 1.0
            else:
                frac = (t - tg - t_steady) / t_decay if t_decay > 0 else 1.0
                v = max(0.0, 1.0 - frac)
            times.append(round(t, 3))
            values.append(round(v, 6))

        return Ramp(name=name, times=times, values=values)

    def create_wind_profile(
        self,
        name: str,
        *,
        heights: Optional[List[float]] = None,
        speeds: Optional[List[float]] = None,
        direction: float = 0.0,
        speed: Optional[float] = None,
        z0: Optional[float] = None,
    ) -> Any:
        """Create a WIND namelist entity describing an atmospheric wind profile."""
        from pyfds.domain.model import WindProfile
        kw: Dict[str, Any] = dict(name=name, direction=direction)
        if heights is not None:
            kw["heights"] = heights
        if speeds is not None:
            kw["speeds"] = speeds
        if speed is not None:
            kw["speed"] = speed
        if z0 is not None:
            kw["z0"] = z0
        return WindProfile(**kw)
