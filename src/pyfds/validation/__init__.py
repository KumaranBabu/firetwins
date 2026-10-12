"""PyFDS Validation Layer — pluggable rule engine + built-in FDS physics rules."""
from .engine import ValidationEngine, ValidationReport, ValidationResult, Severity
from .rules import (
    PoissonComplianceRule, MpiRankGapRule, MeshAlignmentRule,
    MeshOverlapRule, DanglingSurfaceRule, HoleContainmentRule,
    HvacNodeReferenceRule, RampMonotonicityRule,
    ReferenceIntegrityRule, FireResolutionRule, ObstBoundsRule,
)

__all__ = [
    "ValidationEngine", "ValidationReport", "ValidationResult", "Severity",
    "PoissonComplianceRule", "MpiRankGapRule", "MeshAlignmentRule",
    "MeshOverlapRule", "DanglingSurfaceRule", "HoleContainmentRule",
    "HvacNodeReferenceRule", "RampMonotonicityRule",
    "ReferenceIntegrityRule", "FireResolutionRule", "ObstBoundsRule",
]
