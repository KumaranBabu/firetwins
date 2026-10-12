"""
FDS Mesh Quality Advisor
=========================
Cell-size recommendations based on the characteristic fire diameter D* and
the non-dimensional HRR Q*, per FDS User Guide §3.2.

References
----------
- McGrattan, K. et al. (2023). Fire Dynamics Simulator User's Guide.
  NIST Special Publication 1018, 7th ed., §3.2 — Mesh Resolution.
- Quintiere, J. (2006). Fundamentals of Fire Phenomena. §4.3.
- SFPE Handbook, 5th ed., Chapter 13 (Heskestad).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .fire_growth import equivalent_diameter, GrowthRate, ALPHA

# Standard ambient
G:   float = 9.81    # m/s²
RHO: float = 1.204   # kg/m³
CP:  float = 1.0     # kJ/(kg·K)
T_0: float = 293.0   # K


# ── Non-dimensional fire diameter D* ─────────────────────────────────────────

def d_star(q_kw: float) -> float:
    """
    Characteristic fire diameter D* [m] — FDS User Guide §3.2.

        D* = (Q / (ρ₀ · c_p · T₀ · √g))^(2/5)

    For standard air: D* ≈ (Q / 1116)^(2/5)  [Q in kW, D* in m]
    """
    denom = RHO * CP * T_0 * math.sqrt(G)   # ≈ 1116 kW^(2/5)/m
    return (q_kw / denom) ** 0.4


def q_star(q_kw: float, D: float) -> float:
    """
    Non-dimensional HRR Q* (Froude number-based scaling).

        Q* = Q / (ρ₀ · c_p · T₀ · √g · D^(5/2))
    """
    if D <= 0:
        raise ValueError("D must be > 0")
    denom = RHO * CP * T_0 * math.sqrt(G) * D ** 2.5
    return q_kw / denom


# ── Cell-size advisor ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MeshAdvice:
    """Output of :func:`recommend_cell_size`."""
    q_kw: float
    d_star_m: float
    ratio_min: float         # D*/dx minimum recommended
    ratio_max: float         # D*/dx maximum recommended (well-resolved)
    dx_max_m: float          # largest cell still in acceptable range
    dx_recommended_m: float  # target cell size (D*/dx = 15)
    dx_well_resolved_m: float  # well-resolved (D*/dx = 20)
    poisson_ijk: Optional[Tuple[int, int, int]] = None  # Poisson-compliant cell count hint


def recommend_cell_size(
    q_kw: float,
    ratio_target: float = 15.0,
    ratio_min: float = 10.0,
    ratio_max: float = 20.0,
) -> MeshAdvice:
    """
    Recommend FDS cell sizes for *q_kw* [kW] fire.

    Rule of thumb from FDS User Guide §3.2:
      - Marginal: D*/dx ≥ 10
      - Good:     D*/dx ≥ 15
      - Excellent: D*/dx ≥ 20

    Parameters
    ----------
    q_kw:         Peak HRR [kW].
    ratio_target: D*/dx target (default 15).
    ratio_min:    Minimum acceptable D*/dx (default 10).
    ratio_max:    Well-resolved D*/dx (default 20).
    """
    ds = d_star(q_kw)
    return MeshAdvice(
        q_kw=q_kw,
        d_star_m=ds,
        ratio_min=ratio_min,
        ratio_max=ratio_max,
        dx_max_m=ds / ratio_min,
        dx_recommended_m=ds / ratio_target,
        dx_well_resolved_m=ds / ratio_max,
    )


# ── Poisson-compliance helpers ────────────────────────────────────────────────

def _next_poisson(n: int) -> int:
    """Return the smallest integer ≥ n of the form 2^a·3^b·5^c·7^d."""
    if n <= 1:
        return 1
    candidate = n
    while True:
        m = candidate
        for p in (2, 3, 5, 7):
            while m % p == 0:
                m //= p
        if m == 1:
            return candidate
        candidate += 1


def poisson_ijk_for_domain(
    lx: float, ly: float, lz: float, dx: float
) -> Tuple[int, int, int]:
    """
    Return Poisson-compliant (NX, NY, NZ) for a domain of *lx × ly × lz* [m]
    with target cell size *dx* [m].
    """
    nx = _next_poisson(max(1, math.ceil(lx / dx)))
    ny = _next_poisson(max(1, math.ceil(ly / dx)))
    nz = _next_poisson(max(1, math.ceil(lz / dx)))
    return nx, ny, nz


def actual_cell_size(
    domain_size: float, n_cells: int
) -> float:
    """Actual cell size [m] given domain size and cell count."""
    return domain_size / n_cells


# ── MPI decomposition advisor ─────────────────────────────────────────────────

@dataclass
class MpiDecompositionAdvice:
    """Suggested MPI domain decomposition."""
    n_ranks: int
    split_axis: str
    meshes: List[Tuple[float, float]]  # (x_min, x_max) or y/z limits per rank
    cells_per_rank: int
    total_cells: int
    notes: List[str] = field(default_factory=list)


def mpi_split_advice(
    lx: float, ly: float, lz: float,
    dx: float,
    n_ranks: int,
    split_axis: str = "auto",
) -> MpiDecompositionAdvice:
    """
    Suggest how to split a domain across *n_ranks* MPI processes.

    Chooses the longest axis unless *split_axis* is specified.
    Each sub-mesh is Poisson-compliant along the split direction.

    Parameters
    ----------
    lx, ly, lz:  Domain extents [m].
    dx:          Target cell size [m].
    n_ranks:     Number of MPI processes.
    split_axis:  'X', 'Y', 'Z', or 'auto'.
    """
    if split_axis == "auto":
        split_axis = "X" if (lx >= ly and lx >= lz) else ("Y" if ly >= lz else "Z")

    axis_len = {"X": lx, "Y": ly, "Z": lz}[split_axis.upper()]
    n_total  = _next_poisson(max(1, math.ceil(axis_len / dx)))
    n_per    = _next_poisson(max(1, n_total // n_ranks))

    meshes = []
    lo = 0.0
    step = axis_len / n_ranks
    for i in range(n_ranks):
        hi = lo + step if i < n_ranks - 1 else axis_len
        meshes.append((round(lo, 6), round(hi, 6)))
        lo = hi

    cells_per = _next_poisson(max(1, math.ceil(step / dx)))
    other_axes = {k: v for k, v in {"X": lx, "Y": ly, "Z": lz}.items()
                  if k != split_axis.upper()}
    total = cells_per * n_ranks * math.prod(
        _next_poisson(max(1, math.ceil(v / dx))) for v in other_axes.values()
    )

    notes = []
    if n_total % n_ranks != 0:
        notes.append(f"Cell count {n_total} not evenly divisible by {n_ranks} ranks — "
                     f"ranks may have slightly different sizes.")

    return MpiDecompositionAdvice(
        n_ranks=n_ranks,
        split_axis=split_axis.upper(),
        meshes=meshes,
        cells_per_rank=cells_per,
        total_cells=total,
        notes=notes,
    )
