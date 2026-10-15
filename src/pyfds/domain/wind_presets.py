"""Monin-Obukhov wind presets: thermal stability class and landscape type (SIM-05).

Stability uses the Pasquill-Gifford classes A-F with Golder's (1972) relation
``1/L = a + b * log10(z0)`` (L = Obukhov length in m, z0 = roughness length in m). Landscape
roughness lengths follow the Davenport-Wieringa classification. Both are standard tables, offered as
starting points: the engineer should confirm them for the site.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

STABILITY: Dict[str, Tuple[str, float, float]] = {
    "A": ("very unstable", -0.096, 0.029),
    "B": ("unstable", -0.037, 0.029),
    "C": ("slightly unstable", -0.002, 0.018),
    "D": ("neutral", 0.0, 0.0),
    "E": ("slightly stable", 0.004, -0.018),
    "F": ("stable", 0.035, -0.036),
}

LANDSCAPE: Dict[str, float] = {
    "sea": 0.0002,
    "smooth": 0.005,
    "open": 0.03,
    "roughly_open": 0.10,
    "rough": 0.25,
    "very_rough": 0.5,
    "closed": 1.0,
    "chaotic": 2.0,
}


def roughness_length(landscape: str) -> float:
    try:
        return LANDSCAPE[landscape]
    except KeyError:
        raise KeyError(f"unknown landscape {landscape!r}; known: {', '.join(LANDSCAPE)}") from None


def obukhov_length(stability: str, z0: float) -> Optional[float]:
    """Obukhov length (m) for a stability class and roughness; ``None`` for neutral (L = infinity)."""
    key = (stability or "").strip().upper()
    if key not in STABILITY:
        raise KeyError(f"unknown stability class {stability!r}; use one of A-F")
    if z0 <= 0:
        raise ValueError("roughness length must be positive")
    _, a, b = STABILITY[key]
    inv_l = a + b * math.log10(z0)
    if abs(inv_l) < 1e-9:
        return None
    return 1.0 / inv_l
