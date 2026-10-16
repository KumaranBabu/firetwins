"""Mouse and key input for the 3D viewport (plan step F2): turns raw Qt events into clicks, hits and key presses.

* a *click* is a left press and release that moved less than a few pixels, so dragging to rotate the view never draws;
* ``pick_hit`` asks VTK what is under a pixel: the point, the face normal, and the key of the object (or None);
* keys go to the viewport only while its widget has focus.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from pyfds.gui.viewport_cursor import ray_floor_point
from pyfds.gui.viewport_scene import FIELD_DATA_KEY

_CLICK_SLOP = 5          # pixels the mouse may move between press and release and still be a click


def pick_hit(plotter, picker, x: int, y: int) -> Optional[Tuple[Tuple[float, float, float], Optional[Tuple[float, float, float]], Optional[str]]]:
    """``(point, normal, entity_key)`` under display pixel (*x*, *y*), else the floor point (z = 0) with no key."""
    ren = plotter.renderer
    if picker.Pick(x, y, 0, ren) and picker.GetCellId() >= 0:
        key = None
        data = picker.GetDataSet()
        arr = data.GetFieldData().GetAbstractArray(FIELD_DATA_KEY) if data is not None else None
        if arr is not None and arr.GetNumberOfValues():
            key = str(arr.GetValue(0))
        return tuple(picker.GetPickPosition()), tuple(picker.GetPickNormal()), key
    pts = []
    for z in (0.0, 1.0):
        ren.SetDisplayPoint(x, y, z)
        ren.DisplayToWorld()
        w = ren.GetWorldPoint()
        pts.append((w[0] / w[3], w[1] / w[3], w[2] / w[3]))
    floor = ray_floor_point(pts[0], pts[1])
    return (floor, (0.0, 0.0, 1.0), None) if floor is not None else None


def install_input(plotter, on_click: Callable[[int, int, bool], None], on_double_click: Callable[[int, int], None],
                  on_key: Callable[[int, int], bool], on_wheel: Optional[Callable[[int], bool]] = None,
                  on_drag: Optional[Callable[[int, int], bool]] = None):
    """Install the event filter on the plotter's widget; returns it (the caller keeps it alive).

    Callbacks get VTK display pixels (origin bottom-left). ``on_key(qt_key, modifiers)`` returns True when it used
    the key. ``on_wheel`` / ``on_drag`` may return True to stop the event from also moving the camera."""
    from PySide6.QtCore import QEvent, QObject, Qt

    widget = plotter.interactor
    widget.setFocusPolicy(Qt.StrongFocus)

    def display(event):
        dpr = widget.devicePixelRatioF()
        pos = event.position()
        return int(pos.x() * dpr), int((widget.height() - 1 - pos.y()) * dpr)

    class _Filter(QObject):
        press = None

        def eventFilter(self, _obj, event):                         # noqa: N802 (Qt API)
            kind = event.type()
            if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                widget.setFocus()
                self.press = (event.position().x(), event.position().y())
                self.last = self.press
            elif kind == QEvent.MouseMove and self.press is not None and on_drag is not None:
                now = (event.position().x(), event.position().y())
                dx, dy = now[0] - self.last[0], now[1] - self.last[1]
                self.last = now
                if on_drag(int(dx), int(dy)):
                    return True
            elif kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self.press is not None:
                moved = abs(event.position().x() - self.press[0]) + abs(event.position().y() - self.press[1])
                self.press = None
                if moved <= _CLICK_SLOP:
                    x, y = display(event)
                    on_click(x, y, bool(event.modifiers() & Qt.ControlModifier))
            elif kind == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                on_double_click(*display(event))
            elif kind == QEvent.Wheel and on_wheel is not None:
                if on_wheel(1 if event.angleDelta().y() > 0 else -1):
                    return True
            elif kind == QEvent.KeyPress:
                if on_key(event.key(), int(event.modifiers().value if hasattr(event.modifiers(), "value") else event.modifiers())):
                    return True
            return False

    flt = _Filter(widget)
    widget.installEventFilter(flt)
    return flt
