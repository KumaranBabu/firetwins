"""
PyFDS Fire Engineering Calculators
====================================
SFPE/NFPA-based fire engineering correlations for FDS model setup and
post-processing.  All functions operate on SI units unless noted.

Quick start
-----------
>>> from pyfds.engineering import characterise_fire, GrowthRate
>>> from pyfds.engineering import recommend_cell_size
>>> from pyfds.engineering import alpert_ceiling_jet, heskestad_plume
>>> from pyfds.engineering import critical_velocity

>>> fire = characterise_fire(hrr_kw=2000, growth=GrowthRate.FAST)
>>> print(f"D* = {fire.fire_diameter:.2f} m")

>>> advice = recommend_cell_size(2000)
>>> print(f"Recommended dx = {advice.dx_recommended_m:.3f} m")

Submodules
----------
fire_growth  — t-squared curves, RAMP generation, fire area sizing
plumes       — Alpert ceiling jet, Heskestad plume, RTI sprinkler response
mesh_advisor — D*, Q*, cell-size and MPI decomposition advisor
tunnel       — Kennedy critical velocity, back-layering, spill plume
"""
from .fire_growth import (
    GrowthRate,
    ALPHA,
    HRRPUA_DEFAULTS,
    DEFAULT_RADIATIVE_FRACTION,
    DEFAULT_CONVECTIVE_FRACTION,
    FireGrowthResult,
    t_squared_hrr,
    time_to_hrr,
    fire_area,
    equivalent_diameter,
    characterise_fire,
    generate_hrr_curve,
    hrr_curve_for_fds_ramp,
)
from .plumes import (
    CeilingJetResult,
    HeskestadResult,
    SprinklerResponseResult,
    alpert_ceiling_jet,
    alpert_detector_r_max,
    heskestad_flame_height,
    heskestad_virtual_origin,
    heskestad_plume,
    sprinkler_rti,
)
from .mesh_advisor import (
    MeshAdvice,
    MpiDecompositionAdvice,
    d_star,
    q_star,
    recommend_cell_size,
    poisson_ijk_for_domain,
    actual_cell_size,
    mpi_split_advice,
)
from .tunnel import (
    CriticalVelocityResult,
    BackLayeringResult,
    SpillPlumeResult,
    critical_velocity,
    back_layering_length,
    bré_spill_plume,
    atrium_plume_mass_flow,
    smoke_filling_time,
)
from .zone_model import (
    ZoneModelResult,
    DetectorResponseResult,
    two_layer_zone_model,
    detector_response_time,
)

__all__ = [
    # fire_growth
    "GrowthRate", "ALPHA", "HRRPUA_DEFAULTS",
    "DEFAULT_RADIATIVE_FRACTION", "DEFAULT_CONVECTIVE_FRACTION",
    "FireGrowthResult",
    "t_squared_hrr", "time_to_hrr", "fire_area", "equivalent_diameter",
    "characterise_fire", "generate_hrr_curve", "hrr_curve_for_fds_ramp",
    # plumes
    "CeilingJetResult", "HeskestadResult", "SprinklerResponseResult",
    "alpert_ceiling_jet", "alpert_detector_r_max",
    "heskestad_flame_height", "heskestad_virtual_origin", "heskestad_plume",
    "sprinkler_rti",
    # mesh_advisor
    "MeshAdvice", "MpiDecompositionAdvice",
    "d_star", "q_star", "recommend_cell_size",
    "poisson_ijk_for_domain", "actual_cell_size", "mpi_split_advice",
    # tunnel
    "CriticalVelocityResult", "BackLayeringResult", "SpillPlumeResult",
    "critical_velocity", "back_layering_length", "bré_spill_plume",
    "atrium_plume_mass_flow", "smoke_filling_time",
    # zone_model
    "ZoneModelResult", "DetectorResponseResult",
    "two_layer_zone_model", "detector_response_time",
]
