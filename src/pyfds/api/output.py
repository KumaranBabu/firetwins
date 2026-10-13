"""Output definitions: slices, boundary files, isosurfaces, Plot3D, profiles.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .base import _CollectionManager

logger = logging.getLogger(__name__)


class SliceManager(_CollectionManager):
    """Manage FDS slice-file output requests (&SLCF)."""
    def __init__(self, api):
        from pyfds.domain.model import Slice
        super().__init__(api, Slice)

    def add_slice(self, quantity: str, plane: str = "X", position: float = 0.0, **kwargs) -> Any:
        from pyfds.domain.model import Slice
        from pyfds.domain.quantities import CONTEXT_SLCF, validate_quantity
        if not validate_quantity(quantity, CONTEXT_SLCF):
            raise ValueError(f"{quantity!r} is not a valid FDS SLCF quantity")
        if not kwargs.get("name"):                  # every slice needs its own name (the default repeats)
            from .species import _unique
            kwargs["name"] = _unique(self, "SLICE")
        s = Slice(quantity=quantity, plane=plane, position=position, **kwargs)
        self.add(s)
        return s


    def add_volume_slice(self, quantity: str, xb, **kwargs) -> Any:
        """3-D (volumetric) slice over the box *xb* = [x1, x2, y1, y2, z1, z2]."""
        if len(xb) != 6:
            raise ValueError("xb must be [x_min, x_max, y_min, y_max, z_min, z_max]")
        return self.add_slice(quantity, xb=tuple(float(v) for v in xb), **kwargs)


class Smoke3DManager(_CollectionManager):
    """Manage 3-D smoke output requests (&SM3D): ``api.smoke3ds``."""

    def __init__(self, api):
        from pyfds.domain.model import Smoke3D
        super().__init__(api, Smoke3D)

    def add_smoke3d(self, quantity: str = "DENSITY", spec_id=None, name=None) -> Any:
        from pyfds.domain.model import Smoke3D
        if name and self.get(name) is not None:
            raise ValueError(f"smoke3d {name!r} already exists")
        name = name or f"SM3D_{len(self.all()) + 1:03d}"
        s = Smoke3D(name=name, quantity=quantity, spec_id=spec_id)
        self.add(s)
        return s


class BoundaryFileManager(_CollectionManager):
    """Manage FDS boundary-quantity output requests (&BNDF)."""
    def __init__(self, api):
        from pyfds.domain.model import BoundaryFile
        super().__init__(api, BoundaryFile)

    def add_boundary_file(self, quantity: str, **kwargs) -> Any:
        from pyfds.domain.model import BoundaryFile
        from pyfds.domain.quantities import CONTEXT_BNDF, validate_quantity
        if not validate_quantity(quantity, CONTEXT_BNDF):
            raise ValueError(f"{quantity!r} is not a valid FDS BNDF quantity")
        b = BoundaryFile(quantity=quantity, **kwargs)
        self.add(b)
        return b


class IsoSurfaceManager(_CollectionManager):
    """Manage FDS isosurface output requests (&ISOF)."""
    def __init__(self, api):
        from pyfds.domain.model import IsoSurface
        super().__init__(api, IsoSurface)

    def add_isosurface(self, quantity: str, value: float, **kwargs) -> Any:
        from pyfds.domain.model import IsoSurface
        from pyfds.domain.quantities import CONTEXT_ISOF, validate_quantity
        if not validate_quantity(quantity, CONTEXT_ISOF):
            raise ValueError(f"{quantity!r} is not a valid FDS ISOF quantity")
        iso = IsoSurface(quantity=quantity, value=value, **kwargs)
        self.add(iso)
        return iso


class Plot3DManager(_CollectionManager):
    """Manage FDS Plot3D output-channel configuration (&PL3D)."""
    def __init__(self, api):
        from pyfds.domain.model import Plot3D
        super().__init__(api, Plot3D)

    def add_plot3d(self, quantity: str, **kwargs) -> Any:
        from pyfds.domain.model import Plot3D
        from pyfds.domain.quantities import CONTEXT_PL3D, validate_quantity
        if not validate_quantity(quantity, CONTEXT_PL3D):
            raise ValueError(f"{quantity!r} is not a valid FDS PL3D quantity")
        p = Plot3D(quantity=quantity, **kwargs)
        self.add(p)
        return p


class ProfManager(_CollectionManager):
    """Manage in-depth/vertical profile output requests (&PROF)."""
    def __init__(self, api):
        from pyfds.domain.model import Prof
        super().__init__(api, Prof)

    def add_profile(self, quantity: str, xyz: List[float], **kwargs) -> Any:
        from pyfds.domain.model import Prof
        from pyfds.domain.quantities import CONTEXT_PROF, validate_quantity
        if not validate_quantity(quantity, CONTEXT_PROF):
            raise ValueError(f"{quantity!r} is not a valid FDS PROF quantity")
        prof = Prof(quantity=quantity, x=xyz[0], y=xyz[1], z=xyz[2], **kwargs)
        self.add(prof)
        return prof
