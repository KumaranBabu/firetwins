"""Batch analysis: per-variant and per-channel statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VariantSummary:
    """Per-variant result snapshot."""
    variant_id: str
    axis_values: Dict[str, Any]         # {dot-path → value}
    device_peaks:     Dict[str, float]  # channel → peak value
    device_means:     Dict[str, float]  # channel → time-mean
    device_integrals: Dict[str, float]  # channel → ∫ value dt
    device_units:     Dict[str, str]    # channel → units string
    completed: bool = True
    error: Optional[str] = None

    def peak(self, channel: str) -> Optional[float]:
        return self.device_peaks.get(channel)


@dataclass
class ChannelStats:
    """Cross-variant statistics for one device channel."""
    channel: str
    units: str
    n_variants: int

    peak_min:  float = 0.0
    peak_max:  float = 0.0
    peak_mean: float = 0.0
    peak_std:  float = 0.0

    integral_min:  float = 0.0
    integral_max:  float = 0.0
    integral_mean: float = 0.0
    integral_std:  float = 0.0

    outlier_variant_ids: List[str] = field(default_factory=list)

    @property
    def peak_cov(self) -> float:
        """Coefficient of variation for peak values (0 → 1)."""
        return (self.peak_std / self.peak_mean) if self.peak_mean else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "channel":       self.channel,
            "units":         self.units,
            "n_variants":    self.n_variants,
            "peak_min":      self.peak_min,
            "peak_max":      self.peak_max,
            "peak_mean":     self.peak_mean,
            "peak_std":      self.peak_std,
            "peak_cov":      round(self.peak_cov, 4),
            "integral_min":  self.integral_min,
            "integral_max":  self.integral_max,
            "integral_mean": self.integral_mean,
            "integral_std":  self.integral_std,
            "outliers":      self.outlier_variant_ids,
        }
