"""PyFDS built-in validation rules, grouped by area.

Each rule implements the ``ValidationRule`` protocol (``.name``, ``.check(project)``).
Use ``ValidationEngine.default()`` to get them all. Split from the former single
``rules.py`` (plan step G2); every name is still importable from here.
"""
from .mesh import MeshPresenceRule, PoissonComplianceRule, MpiRankGapRule, MeshOverlapRule, MeshAlignmentRule, FireResolutionRule, MeshAspectRatioRule, CylindricalMeshRule
from .hvac import HvacNodeReferenceRule, HvacTopologyRule
from .references import DanglingSurfaceRule, RampMonotonicityRule, ReferenceIntegrityRule, ControlFunctionRule, DuplicateIdRule, SurfaceLayerRule, CtrlLoopRule, FuelSpeciesRule, BackingValueRule
from .geometry import HoleContainmentRule, ObstBoundsRule, VentCoplanarRule, DeviceBoundsRule, InitBoundsRule, SliceBoundsRule
from .physics import SurfaceTypeRule, LiquidFuelRule, ComplexReactionRule
from .systems import DeviceSystemRule, HvacLayoutRule, MaterialResidueRule, ParticleKindRule
from ._common import _e, _w, _i, _is_poisson, _nearest_poisson  # noqa: F401

__all__ = [
    "MeshPresenceRule",
    "PoissonComplianceRule",
    "MpiRankGapRule",
    "MeshOverlapRule",
    "MeshAlignmentRule",
    "FireResolutionRule",
    "MeshAspectRatioRule",
    "CylindricalMeshRule",
    "HvacNodeReferenceRule",
    "HvacTopologyRule",
    "DanglingSurfaceRule",
    "RampMonotonicityRule",
    "ReferenceIntegrityRule",
    "ControlFunctionRule",
    "DuplicateIdRule",
    "SurfaceLayerRule",
    "CtrlLoopRule",
    "FuelSpeciesRule",
    "BackingValueRule",
    "HoleContainmentRule",
    "ObstBoundsRule",
    "VentCoplanarRule",
    "DeviceBoundsRule",
    "InitBoundsRule",
    "SliceBoundsRule",
    "SurfaceTypeRule",
    "LiquidFuelRule",
    "ComplexReactionRule",
    "DeviceSystemRule",
    "HvacLayoutRule",
    "ParticleKindRule",
    "MaterialResidueRule",
]
