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


CONFIG_FORMAT = "pyfds-config"


class PreferencesManager:
    def __init__(self, api) -> None:
        self._api = api

    def export_config(self, filepath: str) -> int:
        """Write the preferences and the display-unit system to a JSON file (File > Export Configuration).
        Returns the number of settings written. Paths such as ``fds_binary`` are machine specific."""
        import json
        from pathlib import Path
        data = {"format": CONFIG_FORMAT, "version": 1, "units": self._api.units.system,
                "preferences": {k: self._cfg().get(k) for k in _SCHEMA}}
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return len(data["preferences"]) + 1

    def import_config(self, filepath: str) -> Dict[str, Any]:
        """Apply a configuration file. Settings this version does not know, or whose value is not valid here, are
        listed in ``rejected`` and left alone. Returns ``{"applied": [...], "rejected": {key: reason}}``."""
        import json
        from pathlib import Path
        try:
            doc = json.loads(Path(filepath).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read {filepath}: {exc}") from None
        if not isinstance(doc, dict) or doc.get("format") != CONFIG_FORMAT:
            raise ValueError(f"{filepath} is not a PyFDS configuration file")
        applied, rejected = [], {}
        for key, value in (doc.get("preferences") or {}).items():
            try:
                self.set(key, value)
                applied.append(key)
            except (KeyError, ValueError) as exc:
                rejected[key] = str(exc)
        if doc.get("units") in ("SI", "EN"):
            self._api.units.set_system(doc["units"])
            applied.append("units")
        return {"applied": applied, "rejected": rejected}

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
