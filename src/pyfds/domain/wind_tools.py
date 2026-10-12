"""
PyFDS Atmospheric Wind Profile Tools
======================================
Generate FDS ``&WIND`` + ``&RAMP`` namelist data for atmospheric boundary
layer (ABL) wind profiles using the log-law and power-law models.

FDS requires the vertical wind speed profile to be specified as a ``RAMP``
referenced from the ``&WIND`` namelist via ``RAMP_SPEED`` / ``RAMP_DIRECTION``.
These helpers build the ``WindProfile`` and the matching ``Ramp`` in one call.

Usage::

    from pyfds.domain.wind_tools import WindTools

    wind, ramps = WindTools.log_law_profile(
        z_ref=10.0, u_ref=8.0, z0=0.03,
        z_min=0.5, z_max=200.0, n_points=25,
        ramp_id="ABL_SPEED",
        wind_direction=270.0,
    )
    project.add_entity(wind)
    for r in ramps:
        project.add_entity(r)
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class WindTools:
    """
    Factory methods that produce ``(WindProfile, [Ramp, ...])`` pairs
    ready for direct insertion into an ``FdsProject``.
    """

    # ── Log-law ───────────────────────────────────────────────────────────────

    @staticmethod
    def log_law_profile(
        z_ref: float,
        u_ref: float,
        z0: float,
        *,
        z_min: float = 0.5,
        z_max: float = 200.0,
        n_points: int = 20,
        ramp_id: str = "WIND_SPEED",
        wind_direction: float = 270.0,
        wind_name: str = "ABL_Wind",
    ) -> Tuple["WindProfile", List["Ramp"]]:  # noqa: F821
        """
        Logarithmic (neutral stability) ABL wind-speed profile.

        The log-law:  U(z) = U_ref × ln(z/z₀) / ln(z_ref/z₀)

        Parameters
        ----------
        z_ref : float
            Reference height (m) where *u_ref* is measured.
        u_ref : float
            Wind speed at *z_ref* (m/s).
        z0 : float
            Aerodynamic roughness length (m).  Typical values:
            water≈0.0002, open country≈0.03, suburbs≈0.3, city≈1.0.
        z_min : float
            Lowest profile sample height (m).
        z_max : float
            Highest profile sample height (m).
        n_points : int
            Number of sample heights (logarithmically spaced).
        ramp_id : str
            ID for the generated ``&RAMP``.  FDS uses this in ``RAMP_SPEED``.
        wind_direction : float
            Wind direction in degrees from North (270 = westerly).
        wind_name : str
            Name for the ``WindProfile`` entity.

        Returns
        -------
        (WindProfile, [Ramp])
        """
        from pyfds.domain.model import WindProfile, Ramp

        if z0 <= 0:
            raise ValueError(f"z0 must be > 0 (got {z0})")
        if z_ref <= z0:
            raise ValueError(f"z_ref ({z_ref}) must be > z0 ({z0})")
        if u_ref <= 0:
            raise ValueError(f"u_ref must be > 0 (got {u_ref})")

        ln_ref = math.log(max(z_ref, z0 * 1.001) / z0)

        heights = _log_spaced(z_min, z_max, n_points)
        speeds = [u_ref * math.log(max(z, z0 * 1.001) / z0) / ln_ref for z in heights]

        # FDS RAMP for &WIND uses F (speed factor, dimensionless) vs T (height in m)
        # In FDS ≥6.7, RAMP_SPEED references a RAMP where T=height, F=speed (m/s)
        ramp = Ramp(
            name=ramp_id,
            times=heights,
            values=speeds,
        )

        wind = WindProfile(
            name=wind_name,
            speed=u_ref,
            direction=wind_direction,
            z_ref=z_ref,
            z0=z0,
            ramp_id=ramp_id,
        )

        logger.info(
            "WindTools.log_law_profile: z0=%.4f, z_ref=%.1f, u_ref=%.2f m/s, "
            "%d sample heights", z0, z_ref, u_ref, n_points
        )
        return wind, [ramp]

    # ── Power-law ─────────────────────────────────────────────────────────────

    @staticmethod
    def power_law_profile(
        z_ref: float,
        u_ref: float,
        alpha: float,
        *,
        z_min: float = 0.5,
        z_max: float = 200.0,
        n_points: int = 20,
        ramp_id: str = "WIND_SPEED",
        wind_direction: float = 270.0,
        wind_name: str = "ABL_Wind",
    ) -> Tuple["WindProfile", List["Ramp"]]:  # noqa: F821
        """
        Power-law ABL wind-speed profile.

        U(z) = U_ref × (z / z_ref) ^ α

        Common *alpha* values:
          0.11 — open water/flat terrain (neutral, Pasquill A–B)
          0.14 — open country (Pasquill C–D)
          0.22 — suburban/wooded
          0.33 — city centre

        Parameters
        ----------
        z_ref : float
            Reference height (m).
        u_ref : float
            Wind speed at *z_ref* (m/s).
        alpha : float
            Power-law exponent (dimensionless).
        z_min : float
            Lowest profile sample height (m).
        z_max : float
            Highest profile sample height (m).
        n_points : int
            Number of sample heights.
        ramp_id : str
            ID for the generated ``&RAMP``.
        wind_direction : float
            Wind direction in degrees from North.
        wind_name : str
            Name for the ``WindProfile`` entity.

        Returns
        -------
        (WindProfile, [Ramp])
        """
        from pyfds.domain.model import WindProfile, Ramp

        if z_ref <= 0:
            raise ValueError(f"z_ref must be > 0 (got {z_ref})")
        if u_ref <= 0:
            raise ValueError(f"u_ref must be > 0 (got {u_ref})")
        if alpha <= 0:
            raise ValueError(f"alpha must be > 0 (got {alpha})")

        heights = _log_spaced(z_min, z_max, n_points)
        speeds = [u_ref * (z / z_ref) ** alpha for z in heights]

        ramp = Ramp(
            name=ramp_id,
            times=heights,
            values=speeds,
        )

        wind = WindProfile(
            name=wind_name,
            speed=u_ref,
            direction=wind_direction,
            z_ref=z_ref,
            ramp_id=ramp_id,
        )

        logger.info(
            "WindTools.power_law_profile: alpha=%.3f, z_ref=%.1f, u_ref=%.2f m/s, "
            "%d sample heights", alpha, z_ref, u_ref, n_points
        )
        return wind, [ramp]

    # ── Time-varying wind (gust) ──────────────────────────────────────────────

    @staticmethod
    def gust_ramp(
        base_speed: float,
        gust_speed: float,
        t_start: float,
        t_peak: float,
        t_end: float,
        ramp_id: str = "WIND_GUST",
    ) -> "Ramp":  # noqa: F821
        """
        Build a triangular gust ramp: base → peak → base over time.

        Parameters
        ----------
        base_speed : float
            Steady wind speed before and after gust (m/s).
        gust_speed : float
            Peak gust speed (m/s).
        t_start : float
            Simulation time when gust begins (s).
        t_peak : float
            Time of peak gust (s).
        t_end : float
            Time when wind returns to base speed (s).
        ramp_id : str
            Ramp identifier.

        Returns
        -------
        Ramp
        """
        from pyfds.domain.model import Ramp

        if not (t_start < t_peak < t_end):
            raise ValueError(
                f"gust times must satisfy t_start < t_peak < t_end "
                f"(got t_start={t_start}, t_peak={t_peak}, t_end={t_end})"
            )
        times  = [0.0, t_start, t_peak, t_end]
        values = [base_speed, base_speed, gust_speed, base_speed]
        return Ramp(name=ramp_id, times=times, values=values)

    # ── Convenience: profile summary ──────────────────────────────────────────

    @staticmethod
    def profile_summary(ramp: "Ramp", *, n_rows: int = 10) -> str:  # noqa: F821
        """
        Return a human-readable table of (height, speed) pairs from a ramp.
        """
        times  = ramp.times or []
        values = ramp.values or []
        n = min(len(times), len(values))
        if n == 0:
            return "Empty ramp"
        step = max(1, n // n_rows)
        header = f"{'Height (m)':>12}  {'Speed (m/s)':>12}"
        sep    = "-" * 26
        rows = [header, sep]
        for i in range(0, n, step):
            rows.append(f"{times[i]:>12.2f}  {values[i]:>12.3f}")
        if (n - 1) % step != 0:
            rows.append(f"{times[-1]:>12.2f}  {values[-1]:>12.3f}")
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_spaced(z_min: float, z_max: float, n: int) -> List[float]:
    """Return *n* heights logarithmically spaced between *z_min* and *z_max*."""
    if n <= 1:
        return [z_min]
    log_min = math.log(max(z_min, 1e-3))
    log_max = math.log(z_max)
    return [math.exp(log_min + (log_max - log_min) * i / (n - 1)) for i in range(n)]
