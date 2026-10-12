"""Compatibility shim — the ``.smv`` metadata parser lives in ``pyfds.results.smv_parser``.

Kept so existing imports keep working; ``results`` must not import ``smokeview``
(see ``tests/architecture``).
"""
from pyfds.results.smv_parser import (  # noqa: F401
    SmvParser, SmvMetadata, SmvGrid, SmvSlice, SmvBoundary,
    SmvIsosurface, SmvDevice, SmvPlot3D, SmvSmoke3D, SmvParticle,
    SmvViewpoint, SmvSurface,
)
