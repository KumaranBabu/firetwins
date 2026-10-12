"""
PyFDS Tenability & Life Safety
================================
ISO 13571 / SFPE-based tenability calculations for FDS post-processing.

Quick start
-----------
>>> from pyfds.tenability import calculate_fed, aset_margin
>>> from pyfds.tenability import visibility_timeseries
>>> from pyfds.tenability import layer_height_timeseries

>>> # Load DEVC data from FDS results and compute FED
>>> result = calculate_fed(times_s, co_ppm, o2_pct=o2, temp_c=temps)
>>> print(f"Incapacitation at t = {result.t_incapacitation:.0f} s")
>>> print(f"ASET margin = {aset_margin(result.t_incapacitation, rset):.0f} s")

Submodules
----------
fed          — FED/FEC incapacitation and lethality (ISO 13571 / Purser)
visibility   — Smoke visibility via Jin (1978) extinction model
layer_height — Smoke layer interface from thermocouple arrays (N-percent rule)
"""
from .fed import (
    FED_INCAPACITATION,
    FED_LETHALITY,
    FEDResult,
    fed_co_step,
    fed_hcn_step,
    fed_o2_step,
    fed_heat_step,
    calculate_fed,
    aset_margin,
)
from .visibility import (
    SignType,
    MASS_OPTICAL_DENSITY,
    VisibilityResult,
    VisibilityTimeSeries,
    visibility_from_extinction,
    visibility_from_smoke_density,
    visibility_from_fds_soot,
    optical_depth,
    transmittance,
    visibility_timeseries,
)
from .layer_height import (
    LayerHeightResult,
    LayerHeightTimeSeries,
    n_percent_interface,
    layer_height_timeseries,
    zone_upper_temp,
    descend_rate,
)

__all__ = [
    # fed
    "FED_INCAPACITATION", "FED_LETHALITY", "FEDResult",
    "fed_co_step", "fed_hcn_step", "fed_o2_step", "fed_heat_step",
    "calculate_fed", "aset_margin",
    # visibility
    "SignType", "MASS_OPTICAL_DENSITY",
    "VisibilityResult", "VisibilityTimeSeries",
    "visibility_from_extinction", "visibility_from_smoke_density",
    "visibility_from_fds_soot", "optical_depth", "transmittance",
    "visibility_timeseries",
    # layer_height
    "LayerHeightResult", "LayerHeightTimeSeries",
    "n_percent_interface", "layer_height_timeseries",
    "zone_upper_temp", "descend_rate",
]
