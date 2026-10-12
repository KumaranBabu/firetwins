"""Statistics record for colour bars."""
from __future__ import annotations

from dataclasses import dataclass


STATS_VERSION = 1


@dataclass
class QuantityStats:
    min: float
    max: float
    p1: float
    p99: float
    n: int = 0
