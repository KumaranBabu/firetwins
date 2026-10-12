"""Cell-count helper for the preset builders."""
from __future__ import annotations

import math as _math


def _auto_cells(lx, ly, lz, dx):
    from .geometry import GeometryHelper
    nx = max(1, _math.ceil(lx / dx))
    ny = max(1, _math.ceil(ly / dx))
    nz = max(1, _math.ceil(lz / dx))
    return (GeometryHelper.nearest_poisson(nx),
            GeometryHelper.nearest_poisson(ny),
            GeometryHelper.nearest_poisson(nz))
