"""Smokeview script command record."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class SmokeviewScriptUnsupported(NotImplementedError):
    """A builder method whose effect Smokeview 6.10.1 scripts cannot produce. Raised instead of writing a command
    Smokeview would reject ('unknown script keyword', which stops the whole script) or silently ignore."""


def _unsupported(what: str, instead: str) -> SmokeviewScriptUnsupported:
    return SmokeviewScriptUnsupported(f"Smokeview 6.10.1 scripts cannot {what}. {instead}")


@dataclass
class _SsfCommand:
    verb: str
    args: List[str] = field(default_factory=list)
    comment: str = ""

    def render(self) -> str:
        """Real SSF layout (checked against Smokeview 6): the keyword on one line, then each argument line
        on its own line below it. ``comment`` is kept for readers of the builder but not written, because
        Smokeview would take a trailing comment as part of the argument."""
        return "\n".join([self.verb] + [f" {a}" for a in self.args])


def slcf_spec(quantity: str, axis: int, position: float, *, cell_centered: bool = False, vector: bool = False) -> str:
    """The argument line of LOADSLCF: the slice as FDS's &SLCF names it (Smokeview 6.10.1 matches QUANTITY, the
    plane, and CELL_CENTERED / VECTOR, which LOADSLICE cannot select)."""
    if axis not in (1, 2, 3):
        raise ValueError(f"axis must be 1 (x), 2 (y) or 3 (z), not {axis}")
    spec = f"QUANTITY='{quantity}' PB{'XYZ'[axis - 1]}={position:g}"
    if cell_centered:
        spec += " CELL_CENTERED=T"
    if vector:
        spec += " VECTOR=T"
    return spec
