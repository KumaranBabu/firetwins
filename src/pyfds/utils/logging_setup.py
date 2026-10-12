"""
PyFDS Logging Setup
===================
Configures the Python logging hierarchy for the ``pyfds`` package.

Features
--------
- Structured log records with timestamps, level, and logger name
- Optional file handler with rotation (via ``logging.handlers``)
- Configurable log level per namespace
- EventBus integration: WARNING and above are re-emitted as ``CUSTOM`` events
  so a future GUI can display them in a status/log panel

Usage::

    from pyfds.utils.logging_setup import setup_logging

    # Basic console setup
    setup_logging(level="INFO")

    # With file rotation
    setup_logging(level="DEBUG", log_file="pyfds.log", max_bytes=5_000_000)

    # Silence noisy sub-loggers
    setup_logging(level="INFO", quiet_loggers=["pyfds.io.fds_parser"])
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import List, Optional


# Default format used across all handlers
_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# EventBus log handler (bridges logging → EventBus for GUI status panels)
# ---------------------------------------------------------------------------

class _EventBusHandler(logging.Handler):
    """
    Forwards WARNING+ log records to the global EventBus as ``CUSTOM`` events.

    A future GUI subscribes to ``EventType.CUSTOM`` with a ``"log"`` tag
    filter to display real-time log messages in a status panel.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            payload = {
                "level":   record.levelname,
                "logger":  record.name,
                "message": self.format(record),
                "tag":     "log",
            }
            get_global_bus().emit(EventType.CUSTOM, payload, source="logging")
        except Exception:
            pass   # never let the log handler raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    level: str = "WARNING",
    log_file: Optional[str] = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 3,
    quiet_loggers: Optional[List[str]] = None,
    bus_level: str = "WARNING",
    fmt: str = _FMT,
    date_fmt: str = _DATE_FMT,
) -> logging.Logger:
    """
    Configure the ``pyfds`` root logger and (optionally) a rotating file log.

    Parameters
    ----------
    level : str
        Log level for the console handler and the ``pyfds`` root logger.
        E.g. ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``.
    log_file : str, optional
        If given, attach a ``RotatingFileHandler`` writing to this path.
    max_bytes : int
        Maximum size (bytes) of each log file before rotation (default 10 MB).
    backup_count : int
        Number of rotated files to keep (default 3).
    quiet_loggers : list[str], optional
        Logger names whose level is forced to WARNING (suppresses verbose output).
    bus_level : str
        Minimum level for log records forwarded to the EventBus (default WARNING).
    fmt : str
        Log record format string.
    date_fmt : str
        Date format string for the formatter.

    Returns
    -------
    logging.Logger
        The configured ``pyfds`` logger.
    """
    formatter = logging.Formatter(fmt=fmt, datefmt=date_fmt)

    # ── pyfds root logger ─────────────────────────────────────────────────────
    pyfds_logger = logging.getLogger("pyfds")
    pyfds_logger.setLevel(level.upper())

    # Clear existing handlers to avoid duplicates on repeated calls
    pyfds_logger.handlers.clear()

    # ── Console handler ───────────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level.upper())
    console.setFormatter(formatter)
    pyfds_logger.addHandler(console)

    # ── File handler (optional) ───────────────────────────────────────────────
    if log_file:
        fh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(level.upper())
        fh.setFormatter(formatter)
        pyfds_logger.addHandler(fh)

    # ── EventBus bridge ───────────────────────────────────────────────────────
    bus_handler = _EventBusHandler()
    bus_handler.setLevel(bus_level.upper())
    bus_handler.setFormatter(formatter)
    pyfds_logger.addHandler(bus_handler)

    # ── Quiet specific sub-loggers ────────────────────────────────────────────
    for name in (quiet_loggers or []):
        logging.getLogger(name).setLevel(logging.WARNING)

    pyfds_logger.info("pyfds logging configured (level=%s)", level.upper())
    return pyfds_logger


def get_logger(name: str) -> logging.Logger:
    """
    Return a ``pyfds``-namespaced logger.

    Use this inside any pyfds module instead of ``logging.getLogger(__name__)``
    to ensure the logger is always under the ``pyfds`` root.

    Parameters
    ----------
    name : str
        Typically ``__name__`` of the calling module, e.g.
        ``"pyfds.io.fds_parser"``.
    """
    # If name already starts with "pyfds" use as-is; otherwise prefix it
    if not name.startswith("pyfds"):
        name = f"pyfds.{name}"
    return logging.getLogger(name)
