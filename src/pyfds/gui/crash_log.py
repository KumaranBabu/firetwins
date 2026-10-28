"""A log file and a last-resort error handler for the two desktop programs.

Without them an error inside a Qt event handler goes to a console a packaged program does not have: the user sees
nothing and support has nothing to look at. ``install`` writes the ``pyfds`` log to a rotating file in the user folder
(the same place as the user library) and reports uncaught exceptions there and in a message box.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

_installed: Optional[str] = None
_last_shown: Tuple[str, float] = ("", 0.0)
_QUIET_SECONDS = 30.0          # the same error raised again (a paint handler, a timer) is logged but not shown again


def user_dir() -> Path:
    from pyfds.api.library import LibraryManager
    return Path(LibraryManager.default_path()).parent


def install(program: str) -> str:
    """Log INFO and above of ``pyfds`` to ``<user dir>/logs/<program>.log`` (2 MB x 3 files) and catch uncaught
    exceptions. Returns the log path ('' when no folder could be written). Calling it again changes nothing."""
    global _installed
    if _installed is not None:
        return _installed
    handler, path = None, None
    for folder in (user_dir() / "logs", Path(tempfile.gettempdir()) / "pyfds_logs"):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{program}.log"
            handler = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            break
        except OSError:
            continue
    if handler is None:
        _installed = ""
        return _installed
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    log = logging.getLogger("pyfds")
    log.addHandler(handler)
    if log.getEffectiveLevel() > logging.INFO:
        log.setLevel(logging.INFO)
    previous = sys.excepthook

    def hook(kind, exc, tb):
        if issubclass(kind, KeyboardInterrupt):
            return previous(kind, exc, tb)
        log.error("Unexpected error", exc_info=(kind, exc, tb))
        _tell_user(exc, str(path))

    sys.excepthook = hook
    _installed = str(path)
    log.info("%s started (Python %s)", program, sys.version.split()[0])
    return _installed


def _tell_user(exc: BaseException, path: str) -> None:
    global _last_shown
    text = f"{type(exc).__name__}: {exc}"
    now = time.monotonic()
    if text == _last_shown[0] and now - _last_shown[1] < _QUIET_SECONDS:
        return
    _last_shown = (text, now)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            return
        QMessageBox.warning(None, "Unexpected error",
                            f"{text}\n\nThe program keeps running, but the last action may not have finished.\n"
                            f"Details for support are in:\n{path}")
    except Exception:                       # reporting must never raise from inside the hook
        pass
