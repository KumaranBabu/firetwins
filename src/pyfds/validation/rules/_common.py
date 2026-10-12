"""Helpers shared by the rule modules."""
from __future__ import annotations

import logging

from ..engine import ValidationResult, Severity


logger = logging.getLogger(__name__)


def _e(rule: str, msg: str, entity: str = None, hint: str = None) -> ValidationResult:
    return ValidationResult(Severity.ERROR,   rule, msg, entity, hint)


def _w(rule: str, msg: str, entity: str = None, hint: str = None) -> ValidationResult:
    return ValidationResult(Severity.WARNING, rule, msg, entity, hint)


def _i(rule: str, msg: str, entity: str = None, hint: str = None) -> ValidationResult:
    return ValidationResult(Severity.INFO,    rule, msg, entity, hint)


def _is_poisson(n: int) -> bool:
    if n <= 0:
        return False
    for f in [2, 3, 5]:
        while n % f == 0:
            n //= f
    return n == 1


def _nearest_poisson(n: int) -> int:
    c = n
    while not _is_poisson(c):
        c += 1
    return c


def box_covered(box, meshes) -> bool:
    """True when the box (x0, x1, y0, y1, z0, z1) lies inside the union of the meshes, so an object that
    straddles the boundary between two neighbouring meshes counts as inside."""
    import itertools
    axes = []
    for a in range(3):
        lo, hi = box[2 * a], box[2 * a + 1]
        cuts = {lo, hi}
        for m in meshes:
            for v in (getattr(m, "xyz"[a] + "_min"), getattr(m, "xyz"[a] + "_max")):
                if lo < v < hi:
                    cuts.add(v)
        pts = sorted(cuts)
        axes.append([(pts[i] + pts[i + 1]) / 2 for i in range(len(pts) - 1)] or [lo])
    return all(any(all(getattr(m, "xyz"[a] + "_min") <= c[a] <= getattr(m, "xyz"[a] + "_max") for a in range(3))
                   for m in meshes) for c in itertools.product(*axes))
