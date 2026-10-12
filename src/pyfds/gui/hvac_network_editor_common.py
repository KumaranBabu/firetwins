"""Constants shared by the HVAC network editor parts."""
from __future__ import annotations

from PySide6.QtGui import QBrush, QColor

from pyfds.core.events import EventType


# Same set ProjectExplorer subscribes to (main_window.py) — duplicated
# locally rather than imported, matching viewport_3d.py's own local copy,
# to avoid a gui-module-to-gui-module circular import.
_REFRESH_EVENTS = (
    EventType.COMMAND_EXECUTED,
    EventType.UNDO_PERFORMED,
    EventType.REDO_PERFORMED,
    EventType.HISTORY_CLEARED,
    EventType.PROJECT_LOADED,
    EventType.PROJECT_CREATED,
)


_LAYER_SPACING = 160.0


_ROW_SPACING = 80.0


_AMBIENT_BRUSH = QBrush(QColor("#70ad47"))


_ROOM_BRUSH = QBrush(QColor("#5b9bd5"))


_NORMAL_PEN_COLOR = QColor("#333333")


_OK_COLOR = QColor("#2e7d32")


_WARN_COLOR = QColor("#c62828")


def _next_free_name(existing: set, prefix: str) -> str:
    n = 1
    while f"{prefix} {n}" in existing:
        n += 1
    return f"{prefix} {n}"
