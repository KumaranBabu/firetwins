"""Per-user viewer defaults (PyroSim keeps these in ``Results.props``).

The preferences a person sets for how results look (colour bars, 3D smoke, units, timelines, general and rendering options,
floors, skybox, time display) can be saved once as *my defaults*; every new results visualization then starts from them.
A saved ``.pyfdsv`` always keeps its own values. The file is ``<user data>/results_prefs.json`` (``$PYFDS_USER_DIR`` in tests).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from . import model as vm

USER_KEYS = ("fds", "smoke3d", "units", "timelines", "general", "rendering", "floors", "skybox", "time_display",
             "motion_blur", "playback_speed", "playback_loop")
_FORMAT = "pyfds-results-user-preferences"


def user_prefs_path() -> Path:
    from pyfds.core import config
    return Path(config._CONFIG_DIR) / "results_prefs.json"


def save_user_defaults(viz: vm.ResultsVisualization, path: Optional[Path] = None) -> str:
    """Write the user-level settings of *viz* as this person's defaults."""
    target = Path(path) if path else user_prefs_path()
    data: Dict[str, Any] = {"format": _FORMAT, **{k: vm.to_plain(getattr(viz, k)) for k in USER_KEYS}}
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(target)
    return str(target)


def apply_user_defaults(viz: vm.ResultsVisualization, path: Optional[Path] = None) -> bool:
    """Copy the saved defaults into *viz* (a new visualization). False when there are none or the file is unreadable."""
    source = Path(path) if path else user_prefs_path()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or data.get("format") != _FORMAT:
        return False
    hints = vm.typing.get_type_hints(vm.ResultsVisualization)
    for key in USER_KEYS:
        if key in data:
            try:
                setattr(viz, key, vm.from_plain(hints[key], data[key]))
            except (TypeError, ValueError, KeyError, AttributeError):
                continue                                   # a damaged entry leaves the built-in value
    return True


def clear_user_defaults(path: Optional[Path] = None) -> bool:
    target = Path(path) if path else user_prefs_path()
    existed = target.exists()
    target.unlink(missing_ok=True)
    return existed
