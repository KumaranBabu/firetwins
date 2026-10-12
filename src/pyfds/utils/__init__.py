"""PyFDS Utility helpers."""
from .formatting import fmt_xb, fmt_ijk, fmt_xyz, fmt_float, fds_bool, fds_str
from .logging_setup import setup_logging, get_logger
from pathlib import Path
from typing import Any, Union


def fds_format_value(val: Any, precision: int = 4) -> str:
    """Backward-compat shim (v0.2.0). Prefer fmt_float in new code."""
    if isinstance(val, bool):
        return ".TRUE." if val else ".FALSE."
    if isinstance(val, (list, tuple)):
        return ", ".join(fds_format_value(v, precision) for v in val)
    if isinstance(val, str):
        return f"'{val}'"
    if isinstance(val, float):
        return fmt_float(val, precision)
    return str(val)


def sanitize_path(path: Union[str, Path]) -> Path:
    """Backward-compat shim (v0.2.0)."""
    return Path(path).resolve()


__all__ = [
    "fmt_xb", "fmt_ijk", "fmt_xyz", "fmt_float", "fds_bool", "fds_str",
    "setup_logging", "get_logger",
    "fds_format_value", "sanitize_path",
]
