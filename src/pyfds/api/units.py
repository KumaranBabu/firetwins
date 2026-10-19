"""Unit system: ``api.units`` (UI-10).

The model always holds SI values. This manager keeps the project's display/entry choice (SI or
English, saved in the ``.pyfds`` file, not in undo history, never written to FDS) and converts.
"""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain import units as _u


class UnitsManager:
    def __init__(self, api) -> None:
        self._api = api

    @property
    def system(self) -> str:
        return self._api.project.editor.units

    def set_system(self, system: str) -> str:
        s = _u._check(system)
        ed = self._api.project.editor
        if ed.units != s:
            ed.units = s
            self._api.project.notify_global("UNITS_CHANGED", s)
        return s

    def kinds(self):
        return _u.kinds()

    def label(self, kind: str) -> str:
        return _u.label(kind, self.system)

    def to_display(self, value: float, kind: str) -> float:
        """Stored SI value -> value in the project's unit system."""
        return _u.to_display(value, kind, self.system)

    def from_display(self, value: float, kind: str) -> float:
        """Value typed in the project's unit system -> SI for the model."""
        return _u.from_display(value, kind, self.system)

    def parse(self, text: str, kind: str) -> float:
        """A typed value with an optional unit ("500 cfm", "3 ft") as SI; a bare number is in the current unit system."""
        from pyfds.domain import units as _u
        return _u.parse_with_unit(text, kind, self.system)

    def convert(self, value: float, kind: str, from_system: str, to_system: str) -> float:
        return _u.convert(value, kind, from_system, to_system)

    def describe(self) -> Dict[str, Any]:
        return {"system": self.system, "labels": {k: _u.label(k, self.system) for k in _u.kinds()}}
