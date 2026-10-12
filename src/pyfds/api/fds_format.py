"""How numbers are written into the FDS file: ``api.fds_format`` (FIO-01).

The setting belongs to the project (saved in ``.pyfds``) and applies to every export.
``significant_digits=None`` keeps the writer's built-in compact formatting.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pyfds.io.fds_writer import FdsWriter, check_number_format, NUMBER_STYLES


class FdsFormatManager:
    def __init__(self, api) -> None:
        self._api = api

    def get(self) -> Dict[str, Any]:
        return dict(self._api.project.number_format or {"significant_digits": None, "style": "auto"})

    def styles(self):
        return list(NUMBER_STYLES)

    def set_number_format(self, significant_digits: Optional[int] = None, style: str = "auto") -> Dict[str, Any]:
        """``style``: ``auto`` (decimal, scientific only for extreme values), ``decimal`` (never scientific
        with *significant_digits*), ``scientific`` (always). One undo step."""
        fmt = check_number_format({"significant_digits": significant_digits, "style": style})
        from pyfds.automation.commands import ModifyPropertyCommand
        value = None if fmt == {"significant_digits": None, "style": "auto"} else fmt
        self._api.history.execute(ModifyPropertyCommand(self._api.project, "number_format", value))
        return self.get()

    def preview(self, value: float) -> str:
        """How one number would be written with the current setting."""
        from pyfds.io import fds_writer as w
        token = w._NUMFMT.set(check_number_format(self._api.project.number_format))
        try:
            return w._fmt_float(float(value))
        finally:
            w._NUMFMT.reset(token)

    def to_string(self) -> str:
        """The whole FDS file as text, honouring the setting."""
        return FdsWriter().generate_content(self._api.project)
