"""Background Smokeview movie render so the window stays usable while frames are drawn."""
from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal


class RenderWorker(QThread):
    """Runs ``render(cancel_event)`` off the GUI thread; ``finished_rc`` carries the return code or error."""

    finished_rc = Signal(int, str)

    def __init__(self, render: Callable[[threading.Event], int], parent=None) -> None:
        super().__init__(parent)
        self._render = render
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        try:
            rc = self._render(self._cancel)
        except Exception as exc:  # reported on the GUI thread
            self.finished_rc.emit(-1, str(exc))
            return
        self.finished_rc.emit(int(rc), "")
