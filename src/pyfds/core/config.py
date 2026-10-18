"""
PyFDS Configuration System
===========================
Hierarchical configuration with named profiles.

Resolution order (highest wins):
  1. Runtime overrides (set via ``FdsConfig.set``)
  2. Environment variables (``PYFDS_FDS_BIN``, ``PYFDS_SMV_BIN``, etc.)
  3. User config file (``user_data/config.json``, or under ``$PYFDS_USER_DIR``)
  4. Built-in defaults

Usage::

    cfg = get_config()
    fds_bin = cfg.fds_binary
    cfg.set("fds_binary", "/usr/local/bin/fds")
    cfg.save()                      # writes user_data/config.json

    # Named profiles for different machines / HPC clusters
    cfg.set_profile("hpc_cluster")
    cfg.set("fds_binary", "/opt/fds/bin/fds_mpi")
    cfg.save_profile("hpc_cluster")
"""
from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def _user_dir() -> Path:
    """``$PYFDS_USER_DIR`` if set, else ``user_data/`` beside the application folder (never the user profile)."""
    base = os.environ.get("PYFDS_USER_DIR")
    return Path(base) if base else Path(__file__).resolve().parents[3] / "user_data"


_CONFIG_DIR = _user_dir()
_CONFIG_FILE = _CONFIG_DIR / "config.json"


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "fds_binary":            os.getenv("FDS_BIN", "fds"),
    "smv_binary":            os.getenv("SMV_BIN", "smokeview"),
    "mpiexec_binary":        os.getenv("MPIEXEC_BIN", "mpiexec"),
    "temp_directory":        str(_CONFIG_DIR / "temp"),
    "output_directory":      str(Path.cwd()),
    "default_mpi_processes": 1,
    "auto_validate":         True,
    "auto_save":             False,
    "auto_save_interval":    300.0,
    "create_backup_on_open": True,
    "recent_files_max":      10,
    "undo_depth":            200,
    "record_preview":        True,
    "fds_install_dirs":      [],            # extra folders searched for FDS builds
    "fds_installs":          [],            # FDS executables the user added by hand
    "fds_install_name":      None,          # the build chosen with api.solvers.select()
    "log_level":             "INFO",
    "max_job_workers":       4,
    "job_timeout":           None,          # seconds, None = no limit
    "plugin_dirs":           [],
    "active_profile":        "default",
}

_ENV_MAP: Dict[str, str] = {
    "PYFDS_FDS_BIN":      "fds_binary",
    "PYFDS_SMV_BIN":      "smv_binary",
    "PYFDS_MPIEXEC":      "mpiexec_binary",
    "PYFDS_TEMP_DIR":     "temp_directory",
    "PYFDS_OUTPUT_DIR":   "output_directory",
    "PYFDS_MPI":          "default_mpi_processes",
    "PYFDS_LOG_LEVEL":    "log_level",
    "PYFDS_MAX_WORKERS":  "max_job_workers",
}


# ---------------------------------------------------------------------------
# ConfigProfile
# ---------------------------------------------------------------------------

@dataclass
class ConfigProfile:
    """A named set of configuration overrides."""
    name: str
    overrides: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.overrides.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.overrides[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "overrides": deepcopy(self.overrides)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConfigProfile":
        return cls(name=d["name"], overrides=d.get("overrides", {}))


# ---------------------------------------------------------------------------
# FdsConfig
# ---------------------------------------------------------------------------

class FdsConfig:
    """
    The primary configuration object.

    All access is thread-safe.  Keys are the same as the ``_DEFAULTS`` dict.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = deepcopy(_DEFAULTS)
        self._runtime: Dict[str, Any] = {}
        self._profiles: Dict[str, ConfigProfile] = {
            "default": ConfigProfile("default"),
        }
        self._active_profile: str = "default"
        self._load_env()
        self._load_file()

    # ── Core access ──────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return value from: runtime override → active profile → file → env → default."""
        with self._lock:
            if key in self._runtime:
                return self._runtime[key]
            prof = self._profiles.get(self._active_profile)
            if prof and key in prof.overrides:
                return prof.overrides[key]
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a runtime override (does not persist until ``save()`` is called)."""
        with self._lock:
            self._runtime[key] = value
        logger.debug("Config override: %s = %r", key, value)

    def set_many(self, overrides: Dict[str, Any]) -> None:
        for k, v in overrides.items():
            self.set(k, v)

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def fds_binary(self) -> str:
        return self.get("fds_binary")

    @property
    def smv_binary(self) -> str:
        return self.get("smv_binary")

    @property
    def mpiexec_binary(self) -> str:
        return self.get("mpiexec_binary")

    @property
    def temp_directory(self) -> Path:
        return Path(self.get("temp_directory"))

    @property
    def output_directory(self) -> Path:
        return Path(self.get("output_directory"))

    @property
    def default_mpi_processes(self) -> int:
        return int(self.get("default_mpi_processes", 1))

    @property
    def auto_validate(self) -> bool:
        return bool(self.get("auto_validate", True))

    @property
    def max_job_workers(self) -> int:
        return int(self.get("max_job_workers", 4))

    @property
    def job_timeout(self) -> Optional[float]:
        v = self.get("job_timeout")
        return float(v) if v is not None else None

    @property
    def plugin_dirs(self) -> List[str]:
        return list(self.get("plugin_dirs", []))

    # ── Profiles ─────────────────────────────────────────────────────────────

    def set_profile(self, name: str) -> None:
        """Activate a named profile (creates it if it does not exist)."""
        with self._lock:
            if name not in self._profiles:
                self._profiles[name] = ConfigProfile(name)
            self._active_profile = name
        logger.debug("Config active profile → %s", name)

    def save_profile(self, name: str, overrides: Optional[Dict[str, Any]] = None) -> None:
        """Save current runtime overrides (or *overrides*) into a named profile."""
        with self._lock:
            prof = self._profiles.setdefault(name, ConfigProfile(name))
            if overrides:
                prof.overrides.update(overrides)
            else:
                prof.overrides.update(self._runtime)

    def get_profile(self, name: str) -> Optional[ConfigProfile]:
        return self._profiles.get(name)

    @property
    def profile_names(self) -> List[str]:
        return list(self._profiles.keys())

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self) -> None:
        """Write current state (merged defaults + runtime overrides) to the config file."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        merged = deepcopy(self._data)
        merged.update(self._runtime)
        merged["active_profile"] = self._active_profile
        merged["profiles"] = {
            n: p.to_dict() for n, p in self._profiles.items()
        }
        with open(_CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        logger.info("Config saved to %s", _CONFIG_FILE)

    def reload(self) -> None:
        """Re-read the config file from disk."""
        with self._lock:
            self._load_file()

    # ── Internal loaders ─────────────────────────────────────────────────────

    def _load_env(self) -> None:
        """Apply environment variable overrides."""
        for env_key, cfg_key in _ENV_MAP.items():
            val = os.getenv(env_key)
            if val is not None:
                # Attempt type-safe conversion
                default = _DEFAULTS.get(cfg_key)
                if isinstance(default, int):
                    try:
                        val = int(val)
                    except ValueError:
                        pass
                elif isinstance(default, float):
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                self._data[cfg_key] = val

    def _load_file(self) -> None:
        """Load settings from the user config file if it exists."""
        if not _CONFIG_FILE.exists():
            return
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            # Restore top-level keys
            for k, v in saved.items():
                if k not in ("profiles", "active_profile"):
                    self._data[k] = v
            # Restore profiles
            for prof_dict in saved.get("profiles", {}).values():
                prof = ConfigProfile.from_dict(prof_dict)
                self._profiles[prof.name] = prof
            # Restore active profile
            saved_active = saved.get("active_profile", "default")
            if saved_active in self._profiles:
                self._active_profile = saved_active
            logger.debug("Config loaded from %s", _CONFIG_FILE)
        except Exception as exc:
            logger.warning("Failed to load config from %s: %s", _CONFIG_FILE, exc)

    def to_dict(self) -> Dict[str, Any]:
        """Return a merged view of all settings (for diagnostics)."""
        merged = deepcopy(self._data)
        merged.update(self._runtime)
        merged["active_profile"] = self._active_profile
        return merged

    def __repr__(self) -> str:
        return (f"<FdsConfig fds={self.fds_binary!r} "
                f"smv={self.smv_binary!r} "
                f"profile={self._active_profile!r}>")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_config_instance: Optional[FdsConfig] = None
_config_lock = threading.Lock()


def get_config() -> FdsConfig:
    """Return (or lazily create) the process-wide ``FdsConfig`` singleton."""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = FdsConfig()
    return _config_instance


def reset_config() -> None:
    """Replace the singleton with a fresh instance. Useful in tests."""
    global _config_instance
    with _config_lock:
        _config_instance = FdsConfig()
