"""Preferences: ``api.preferences`` (UX-16, UX-17).

A validated, grouped view over the application config. The FDS number format is a project setting
(``api.fds_format``), not a preference; results/rendering options live with the viewer.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# key -> (group, type, minimum, maximum, description)
_SCHEMA: Dict[str, tuple] = {
    "auto_save":             ("General", bool, None, None, "Write an autosave file while there are unsaved changes"),
    "auto_save_interval":    ("General", float, 30.0, 86400.0, "Seconds between autosaves"),
    "create_backup_on_open": ("General", bool, None, None, "Keep a copy of a project file as it was opened"),
    "recent_files_max":      ("General", int, 0, 50, "How many recent files to remember"),
    "undo_depth":            ("General", int, 10, 1000, "Edits that can be undone"),
    "record_preview":        ("Record View", bool, None, None, "Show the FDS record preview in editors"),
    "fds_binary":            ("FDS", str, None, None, "FDS executable"),
    "default_mpi_processes": ("FDS", int, 1, 4096, "MPI processes for a new run"),
    "auto_validate":         ("FDS", bool, None, None, "Check the model automatically as it changes"),
}


class PreferencesManager:
    def __init__(self, api) -> None:
        self._api = api

    @staticmethod
    def _cfg():
        from pyfds.core.config import get_config
        return get_config()

    def keys(self):
        return list(_SCHEMA)

    def get(self, key: str) -> Any:
        if key not in _SCHEMA:
            raise KeyError(f"unknown preference {key!r}")
        return self._cfg().get(key)

    def all(self) -> Dict[str, Dict[str, Any]]:
        """``{group: {key: {value, description}}}`` for a preferences dialog."""
        out: Dict[str, Dict[str, Any]] = {}
        for key, (group, _t, _lo, _hi, desc) in _SCHEMA.items():
            out.setdefault(group, {})[key] = {"value": self._cfg().get(key), "description": desc}
        return out

    def set(self, key: str, value: Any) -> Any:
        if key not in _SCHEMA:
            raise KeyError(f"unknown preference {key!r}")
        _group, typ, lo, hi, _desc = _SCHEMA[key]
        if typ is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        elif typ is str:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            if typ is int and int(value) != value:
                raise ValueError(f"{key} must be a whole number")
            value = typ(value)
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                raise ValueError(f"{key} must be between {lo} and {hi}")
        self._cfg().set(key, value)
        if key == "undo_depth":
            self._api.history.set_depth(value)
        return value
