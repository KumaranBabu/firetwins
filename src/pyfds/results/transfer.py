"""Transfer functions for smoke and fire volumes (RES-03): scalar field -> RGBA, as plain numpy.

* ``smoke_rgba`` turns a soot density (kg/m3) into a grey, see-through volume: each cell absorbs
  ``1 - exp(-kappa * rho * dx)`` of the light passing through it (Beer-Lambert), with *kappa* the mass
  extinction coefficient (m2/kg; 8700 is FDS's default for smoke).
* ``fire_rgba`` turns a heat release rate per unit volume (kW/m3) into flame colours: cells below *cutoff*
  are clear, above it the colour runs red -> orange -> pale yellow and gets more opaque. The cutoff and
  full-scale values are display settings, not physics.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

DEFAULT_MASS_EXTINCTION = 8700.0      # m2/kg
DEFAULT_FIRE_CUTOFF = 200.0           # kW/m3
DEFAULT_FIRE_FULL = 2000.0            # kW/m3

_FIRE_STOPS = np.array([0.0, 0.5, 1.0])
_FIRE_COLORS = np.array([[0.80, 0.10, 0.00], [1.00, 0.55, 0.00], [1.00, 0.95, 0.60]])


def _check_opacity(opacity: float) -> None:
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("opacity must be between 0 and 1")


def smoke_rgba(density: np.ndarray, cell_size: float, mass_extinction: float = DEFAULT_MASS_EXTINCTION,
               color: Tuple[float, float, float] = (0.3, 0.3, 0.3), opacity: float = 1.0) -> np.ndarray:
    """RGBA array (``density.shape + (4,)``) for a soot-density field; *opacity* scales the alpha."""
    _check_opacity(opacity)
    if cell_size <= 0 or mass_extinction <= 0:
        raise ValueError("cell_size and mass_extinction must be positive")
    rho = np.nan_to_num(np.asarray(density, dtype=float), nan=0.0)
    alpha = (1.0 - np.exp(-mass_extinction * np.clip(rho, 0.0, None) * cell_size)) * opacity
    out = np.empty(rho.shape + (4,))
    out[..., 0], out[..., 1], out[..., 2] = color
    out[..., 3] = alpha
    return out


def fire_rgba(hrrpuv: np.ndarray, cutoff: float = DEFAULT_FIRE_CUTOFF, full: float = DEFAULT_FIRE_FULL,
              opacity: float = 1.0) -> np.ndarray:
    """RGBA array for a heat-release-rate-per-volume field (flames)."""
    _check_opacity(opacity)
    if not 0 <= cutoff < full:
        raise ValueError("need 0 <= cutoff < full")
    h = np.nan_to_num(np.asarray(hrrpuv, dtype=float), nan=0.0)
    q = np.clip((h - cutoff) / (full - cutoff), 0.0, 1.0)
    out = np.empty(h.shape + (4,))
    for c in range(3):
        out[..., c] = np.interp(q, _FIRE_STOPS, _FIRE_COLORS[:, c])
    out[..., 3] = np.where(h >= cutoff, (0.2 + 0.8 * q) * opacity, 0.0)
    return out


def apply(kind: str, values: np.ndarray, cell_size: float, **options) -> np.ndarray:
    """RGBA for a volume of *kind* (``smoke`` or ``fire``)."""
    if kind == "smoke":
        return smoke_rgba(values, cell_size, **options)
    if kind == "fire":
        return fire_rgba(values, **options)
    raise ValueError(f"unknown volume kind {kind!r}; use 'smoke' or 'fire'")


def transmittance(density_along_ray: np.ndarray, step: float, mass_extinction: float = DEFAULT_MASS_EXTINCTION) -> float:
    """Fraction of light that gets through a ray crossing cells of soot density (kg/m3) of length *step*."""
    return float(np.exp(-mass_extinction * np.nansum(np.clip(density_along_ray, 0.0, None)) * step))
