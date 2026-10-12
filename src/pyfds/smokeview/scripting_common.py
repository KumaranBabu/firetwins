"""Smokeview script command record."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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
