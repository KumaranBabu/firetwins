"""PyFDS Results as its own program: how the model editor hands it a case.

The two programs talk through a small folder (``<user data>/results_link``), which needs no sockets and survives either side
being busy or restarted:

* the viewer writes ``alive.json`` about once a second while it runs;
* ``launch_results(path)`` drops a request file there when that heartbeat is fresh (one viewer window serves every request, and
  the case already open is refreshed instead of reloaded), otherwise it starts the viewer as a separate process
  (``PyFDSResults.exe`` next to the editor when packaged, else ``python -m pyfds.gui.results``);
* ``ResultsServer`` (owned by the viewer's window) polls the folder and passes each request to ``window.open_or_refresh``.
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer

_EXE_NAME = "PyFDSResults.exe"
_ALIVE = "alive.json"
#: A viewer busy loading a big case may not beat for a while; past this it is taken to be gone.
ALIVE_SECONDS = 15.0
_POLL_MS = 300
_STALE_SECONDS = 120.0                         # a request older than this was left by a viewer that is gone
_counter = itertools.count()


def link_dir() -> Path:
    """The folder both programs use (inside the per-user data folder, which tests redirect)."""
    from pyfds.core import config
    return Path(config._CONFIG_DIR) / "results_link"


def viewer_running(now: Optional[float] = None) -> bool:
    """True when a viewer has beaten recently."""
    try:
        beat = json.loads((link_dir() / _ALIVE).read_text(encoding="utf-8"))["t"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (time.time() if now is None else now) - float(beat) < ALIVE_SECONDS


def _write_beat(pid: int) -> None:
    folder = link_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / _ALIVE).write_text(json.dumps({"t": time.time(), "pid": pid}), encoding="utf-8")


def send_open(path: Optional[str]) -> bool:
    """Ask the running viewer to show *path* (None = just come to the front). False when no viewer is running."""
    if not viewer_running():
        return False
    folder = link_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"req_{time.time_ns():020d}_{next(_counter):06d}_{os.getpid()}.json"      # the clock is coarse: the counter keeps order
    tmp = folder / (name + ".tmp")
    tmp.write_text(json.dumps({"open": path}), encoding="utf-8")
    os.replace(tmp, folder / name)                       # the viewer never sees a half-written request
    return True


def results_command(path: Optional[str] = None) -> List[str]:
    """The command line that starts the viewer, packaged or from source."""
    if getattr(sys, "frozen", False):
        cmd = [str(Path(sys.executable).resolve().parent / _EXE_NAME)]
    else:
        cmd = [sys.executable, "-m", "pyfds.gui.results"]
    return cmd + ([str(path)] if path else [])


def start_results(path: Optional[str] = None) -> subprocess.Popen:
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        import pyfds
        src = str(Path(pyfds.__file__).resolve().parents[1])          # the child must find the same pyfds
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    proc = subprocess.Popen(results_command(path), env=env, creationflags=flags, close_fds=True)
    _write_beat(proc.pid)                                  # "starting": another click while it loads goes to it, not to a second viewer
    return proc


def launch_results(path: Optional[str] = None) -> str:
    """Show *path* in PyFDS Results: ``"sent"`` to a viewer that was already open, ``"started"`` for a new one."""
    if send_open(path):
        return "sent"
    start_results(path)
    return "started"


class ResultsServer(QObject):
    """The viewer's half: keeps the heartbeat and hands each request to ``window.open_or_refresh``."""

    def __init__(self, window, parent: Optional[QObject] = None, poll_ms: int = _POLL_MS) -> None:
        super().__init__(parent if parent is not None else (window if isinstance(window, QObject) else None))
        self._window = window
        self._folder = link_dir()
        self._folder.mkdir(parents=True, exist_ok=True)
        old = time.time_ns() - int(_STALE_SECONDS * 1e9)
        for stale in self._folder.glob("req_*"):               # requests left by an earlier viewer (those made while this one started are kept)
            try:
                made = int(stale.name.split("_")[1])
            except (IndexError, ValueError):
                made = 0
            if made < old:
                stale.unlink(missing_ok=True)
        self._last_beat = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(poll_ms)
        self.poll()

    def poll(self) -> int:
        """Beat if due, then serve every waiting request in the order it was made. Returns how many were served."""
        now = time.time()
        if now - self._last_beat >= 1.0:
            try:
                _write_beat(os.getpid())
                self._last_beat = now
            except OSError:
                pass
        served = 0
        for req in sorted(self._folder.glob("req_*.json")):
            try:
                path = json.loads(req.read_text(encoding="utf-8")).get("open")
            except (OSError, ValueError, AttributeError):
                path = None
            req.unlink(missing_ok=True)
            self._window.open_or_refresh(path)
            served += 1
        return served

    def close(self) -> None:
        """The viewer is closing: stop answering and take the heartbeat away so the editor starts a new one next time."""
        self._timer.stop()
        (self._folder / _ALIVE).unlink(missing_ok=True)
