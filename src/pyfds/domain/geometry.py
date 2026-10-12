"""
PyFDS Geometry Helpers
======================
Pure-Python geometry utilities used by the domain layer and validation.

No FDS-specific knowledge lives here — only spatial math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Bounding Box
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    """
    Axis-aligned 3-D bounding box.

    All coordinates are in metres. Min must be ≤ max in every axis.
    """
    x_min: float; x_max: float
    y_min: float; y_max: float
    z_min: float; z_max: float

    @classmethod
    def from_entity(cls, obj) -> "BoundingBox":
        """Construct from any object with x_min/x_max/y_min/y_max/z_min/z_max."""
        return cls(
            x_min=obj.x_min, x_max=obj.x_max,
            y_min=obj.y_min, y_max=obj.y_max,
            z_min=obj.z_min, z_max=obj.z_max,
        )

    @classmethod
    def from_xb(cls, xb: List[float]) -> "BoundingBox":
        """Construct from an XB list [x1, x2, y1, y2, z1, z2]."""
        if len(xb) != 6:
            raise ValueError(f"XB must have exactly 6 values, got {len(xb)}")
        return cls(xb[0], xb[1], xb[2], xb[3], xb[4], xb[5])

    # ── Dimensions ──────────────────────────────────────────────────────────

    @property
    def dx(self) -> float:
        return self.x_max - self.x_min

    @property
    def dy(self) -> float:
        return self.y_max - self.y_min

    @property
    def dz(self) -> float:
        return self.z_max - self.z_min

    @property
    def volume(self) -> float:
        return self.dx * self.dy * self.dz

    @property
    def surface_area(self) -> float:
        dx, dy, dz = self.dx, self.dy, self.dz
        return 2.0 * (dx * dy + dy * dz + dx * dz)

    @property
    def center(self) -> Tuple[float, float, float]:
        return (
            (self.x_min + self.x_max) / 2.0,
            (self.y_min + self.y_max) / 2.0,
            (self.z_min + self.z_max) / 2.0,
        )

    @property
    def xb(self) -> List[float]:
        return [self.x_min, self.x_max, self.y_min, self.y_max, self.z_min, self.z_max]

    # ── Spatial predicates ───────────────────────────────────────────────────

    def contains_point(self, x: float, y: float, z: float) -> bool:
        return (self.x_min <= x <= self.x_max and
                self.y_min <= y <= self.y_max and
                self.z_min <= z <= self.z_max)

    def contains_box(self, other: "BoundingBox") -> bool:
        """Return True if *other* is fully inside self."""
        return (other.x_min >= self.x_min and other.x_max <= self.x_max and
                other.y_min >= self.y_min and other.y_max <= self.y_max and
                other.z_min >= self.z_min and other.z_max <= self.z_max)

    def overlaps(self, other: "BoundingBox", tol: float = 0.0) -> bool:
        """Return True if the two boxes share interior volume."""
        return (self.x_min < other.x_max - tol and self.x_max > other.x_min + tol and
                self.y_min < other.y_max - tol and self.y_max > other.y_min + tol and
                self.z_min < other.z_max - tol and self.z_max > other.z_min + tol)

    def abuts(self, other: "BoundingBox", tol: float = 1e-4) -> Optional[str]:
        """
        Return the axis ('X', 'Y', or 'Z') along which the two boxes share a face,
        or None if they do not touch.
        """
        for axis, lo1, hi1, lo2, hi2, lo1b, hi1b, lo2b, hi2b, lo1c, hi1c, lo2c, hi2c in [
            ("X",
             self.x_min, self.x_max, other.x_min, other.x_max,
             self.y_min, self.y_max, other.y_min, other.y_max,
             self.z_min, self.z_max, other.z_min, other.z_max),
            ("Y",
             self.y_min, self.y_max, other.y_min, other.y_max,
             self.x_min, self.x_max, other.x_min, other.x_max,
             self.z_min, self.z_max, other.z_min, other.z_max),
            ("Z",
             self.z_min, self.z_max, other.z_min, other.z_max,
             self.x_min, self.x_max, other.x_min, other.x_max,
             self.y_min, self.y_max, other.y_min, other.y_max),
        ]:
            face_touch = abs(hi1 - lo2) < tol or abs(hi2 - lo1) < tol
            overlap_b = lo1b < hi2b - tol and hi1b > lo2b + tol
            overlap_c = lo1c < hi2c - tol and hi1c > lo2c + tol
            if face_touch and overlap_b and overlap_c:
                return axis
        return None

    def union(self, other: "BoundingBox") -> "BoundingBox":
        return BoundingBox(
            x_min=min(self.x_min, other.x_min),
            x_max=max(self.x_max, other.x_max),
            y_min=min(self.y_min, other.y_min),
            y_max=max(self.y_max, other.y_max),
            z_min=min(self.z_min, other.z_min),
            z_max=max(self.z_max, other.z_max),
        )

    def intersection(self, other: "BoundingBox") -> Optional["BoundingBox"]:
        nx_min = max(self.x_min, other.x_min)
        nx_max = min(self.x_max, other.x_max)
        ny_min = max(self.y_min, other.y_min)
        ny_max = min(self.y_max, other.y_max)
        nz_min = max(self.z_min, other.z_min)
        nz_max = min(self.z_max, other.z_max)
        if nx_min < nx_max and ny_min < ny_max and nz_min < nz_max:
            return BoundingBox(nx_min, nx_max, ny_min, ny_max, nz_min, nz_max)
        return None

    def expand(self, dx: float, dy: float, dz: float) -> "BoundingBox":
        return BoundingBox(
            self.x_min - dx, self.x_max + dx,
            self.y_min - dy, self.y_max + dy,
            self.z_min - dz, self.z_max + dz,
        )

    def __repr__(self) -> str:
        return (f"BoundingBox(x=[{self.x_min},{self.x_max}] "
                f"y=[{self.y_min},{self.y_max}] z=[{self.z_min},{self.z_max}])")


# ---------------------------------------------------------------------------
# Geometry helper utilities
# ---------------------------------------------------------------------------

class GeometryHelper:
    """
    Collection of static spatial utility methods for FDS scenario construction.
    """

    # ── Cell count helpers ───────────────────────────────────────────────────

    @staticmethod
    def poisson_factors(n: int) -> List[int]:
        """Return the prime factors of *n* (only 2, 3, 5 are Poisson-legal in FDS)."""
        result = []
        for f in [2, 3, 5]:
            while n % f == 0:
                result.append(f)
                n //= f
        if n != 1:
            result.append(n)  # non-Poisson factor
        return result

    @staticmethod
    def is_poisson_compliant(n: int) -> bool:
        """Return True if n = 2^a * 3^b * 5^c for non-negative integers a, b, c."""
        if n <= 0:
            return False
        for f in [2, 3, 5]:
            while n % f == 0:
                n //= f
        return n == 1

    @staticmethod
    def nearest_poisson(n: int) -> int:
        """Return the nearest Poisson-compliant integer ≥ n."""
        if GeometryHelper.is_poisson_compliant(n):
            return n
        candidate = n + 1
        while not GeometryHelper.is_poisson_compliant(candidate):
            candidate += 1
        return candidate

    @staticmethod
    def cell_sizes(box: BoundingBox, cells: Tuple[int, int, int]) -> Tuple[float, float, float]:
        """Return (dx, dy, dz) cell dimensions for *cells* in *box*."""
        nx, ny, nz = cells
        return box.dx / nx, box.dy / ny, box.dz / nz

    @staticmethod
    def auto_cell_count(
        box: BoundingBox,
        dx: float,
        dy: Optional[float] = None,
        dz: Optional[float] = None,
        force_poisson: bool = True,
    ) -> Tuple[int, int, int]:
        """
        Compute (nx, ny, nz) such that each cell is approximately *dx*×*dy*×*dz*.

        Parameters
        ----------
        box:
            Domain bounds.
        dx:
            Target cell width in X.
        dy:
            Target cell width in Y (defaults to *dx*).
        dz:
            Target cell width in Z (defaults to *dx*).
        force_poisson:
            Round up each dimension to the nearest Poisson number.
        """
        dy = dy or dx
        dz = dz or dx
        nx = max(1, math.ceil(box.dx / dx))
        ny = max(1, math.ceil(box.dy / dy))
        nz = max(1, math.ceil(box.dz / dz))
        if force_poisson:
            nx = GeometryHelper.nearest_poisson(nx)
            ny = GeometryHelper.nearest_poisson(ny)
            nz = GeometryHelper.nearest_poisson(nz)
        return nx, ny, nz

    # ── Domain decomposition ─────────────────────────────────────────────────

    @staticmethod
    def split_x(box: BoundingBox, n: int) -> List[BoundingBox]:
        """Split *box* into *n* equal slabs along X."""
        slab_w = box.dx / n
        slabs = []
        for i in range(n):
            x0 = box.x_min + i * slab_w
            x1 = box.x_min + (i + 1) * slab_w
            slabs.append(BoundingBox(x0, x1, box.y_min, box.y_max, box.z_min, box.z_max))
        return slabs

    @staticmethod
    def split_y(box: BoundingBox, n: int) -> List[BoundingBox]:
        slab_w = box.dy / n
        slabs = []
        for i in range(n):
            y0 = box.y_min + i * slab_w
            y1 = box.y_min + (i + 1) * slab_w
            slabs.append(BoundingBox(box.x_min, box.x_max, y0, y1, box.z_min, box.z_max))
        return slabs

    @staticmethod
    def split_z(box: BoundingBox, n: int) -> List[BoundingBox]:
        slab_w = box.dz / n
        slabs = []
        for i in range(n):
            z0 = box.z_min + i * slab_w
            z1 = box.z_min + (i + 1) * slab_w
            slabs.append(BoundingBox(box.x_min, box.x_max, box.y_min, box.y_max, z0, z1))
        return slabs

    # ── D*/dx fire resolution heuristic ─────────────────────────────────────

    @staticmethod
    def fire_diameter(hrr_kw: float, alpha: float = 0.35) -> float:
        """
        Compute the characteristic fire diameter D* (m).

        D* = (Q / (ρ_∞ * c_p * T_∞ * √g))^(2/5)

        Uses standard atmospheric values at 20°C.
        """
        rho = 1.2        # kg/m³
        cp = 1.0         # kJ/(kg·K)
        t_inf = 293.0    # K
        g = 9.81         # m/s²
        d_star = (hrr_kw / (rho * cp * t_inf * math.sqrt(g))) ** 0.4
        return d_star

    @staticmethod
    def recommended_cell_size(hrr_kw: float, ratio: float = 10.0) -> float:
        """
        Return the recommended maximum cell size (m) for a given fire HRR.

        FDS best-practice guidance: D*/dx ≥ 10 for well-resolved LES fires.

        Parameters
        ----------
        hrr_kw:
            Peak HRR in kW.
        ratio:
            D*/dx ratio target (default 10, minimum 4 for engineering accuracy).
        """
        return GeometryHelper.fire_diameter(hrr_kw) / ratio

    @staticmethod
    def dstar_dx_ratio(hrr_kw: float, dx: float) -> float:
        """Return D*/dx for a given HRR and cell size."""
        d_star = GeometryHelper.fire_diameter(hrr_kw)
        return d_star / dx if dx > 0 else float("inf")
