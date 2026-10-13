"""Heat-release-rate curves for the fire library (FIR-06).

Built-in items are *formula* fires, not measured data: the standard t-squared growth classes (NFPA 72 /
SFPE alpha values), a steady fire, and growth followed by steady burning and decay. Measured curves
(furniture, vehicles ...) belong in the project's own items (``api.fires.save_item``) so their source stays
with the data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

#: t^2 growth coefficients alpha (kW/s^2): Q = alpha * t^2 (NFPA 72, Annex B)
T2_ALPHA: Dict[str, float] = {"slow": 0.00293, "medium": 0.01172, "fast": 0.04689, "ultrafast": 0.18760}


@dataclass(frozen=True)
class FireItem:
    name: str
    description: str
    times: Tuple[float, ...]            # s
    hrr: Tuple[float, ...]              # kW
    source: str = "formula"

    @property
    def peak(self) -> float:
        return max(self.hrr)

    @property
    def energy_mj(self) -> float:
        return sum((self.hrr[i] + self.hrr[i + 1]) * (self.times[i + 1] - self.times[i]) / 2.0
                   for i in range(len(self.times) - 1)) / 1000.0


def t2_growth(alpha: float, peak_kw: float, steady_s: float = 0.0, decay_s: float = 0.0,
              points: int = 12) -> Tuple[List[float], List[float]]:
    """``(times, hrr)``: Q = alpha t^2 up to *peak_kw*, held for *steady_s*, then falling linearly to zero
    over *decay_s*. The growth part is sampled at *points* times (the ramp is piecewise linear in FDS)."""
    if alpha <= 0 or peak_kw <= 0:
        raise ValueError("alpha and peak_kw must be positive")
    if steady_s < 0 or decay_s < 0 or points < 3:
        raise ValueError("steady_s and decay_s must be zero or more; use at least 3 points")
    t_peak = (peak_kw / alpha) ** 0.5
    times = [t_peak * i / (points - 1) for i in range(points)]
    hrr = [min(alpha * t * t, peak_kw) for t in times]
    hrr[-1] = peak_kw
    if steady_s > 0:
        times.append(t_peak + steady_s)
        hrr.append(peak_kw)
    if decay_s > 0:
        times.append(times[-1] + decay_s)
        hrr.append(0.0)
    return [round(t, 4) for t in times], [round(q, 4) for q in hrr]


def builtin_items(peak_kw: float = 1000.0) -> Dict[str, FireItem]:
    """The built-in formula fires, all peaking at *peak_kw*."""
    items: Dict[str, FireItem] = {}
    for cls, alpha in T2_ALPHA.items():
        t, q = t2_growth(alpha, peak_kw, steady_s=300.0, decay_s=300.0)
        items[f"t2 {cls}"] = FireItem(
            f"t2 {cls}", f"t-squared growth, alpha = {alpha} kW/s^2, peak {peak_kw:g} kW, 300 s steady, 300 s decay",
            tuple(t), tuple(q))
    items["steady"] = FireItem("steady", f"{peak_kw:g} kW from the start", (0.0, 1.0), (peak_kw, peak_kw))
    return items


def interpolate(item_times: List[float], item_hrr: List[float], t: float) -> float:
    """HRR (kW) at time *t* by linear interpolation; 0 outside the curve."""
    if t < item_times[0] or t > item_times[-1]:
        return 0.0
    for i in range(len(item_times) - 1):
        if item_times[i] <= t <= item_times[i + 1]:
            span = item_times[i + 1] - item_times[i]
            return item_hrr[i] if span == 0 else item_hrr[i] + (item_hrr[i + 1] - item_hrr[i]) * (t - item_times[i]) / span
    return item_hrr[-1]


def validate_curve(times: List[float], hrr: List[float]) -> Optional[str]:
    """A problem with a user HRR curve, or ``None``."""
    if len(times) != len(hrr) or len(times) < 2:
        return "give at least two points, one HRR per time"
    if any(b <= a for a, b in zip(times, times[1:])):
        return "times must be strictly increasing"
    if any(q < 0 for q in hrr):
        return "HRR cannot be negative"
    if max(hrr) <= 0:
        return "the curve has no heat release"
    return None
