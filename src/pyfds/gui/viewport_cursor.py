"""Live model coordinates under the mouse for the 3D viewport (status-bar readout).

The point is where the mouse ray first hits an object; over empty space it is where the ray meets the floor
plane z = 0. Updates are throttled so dragging the view stays smooth.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

_MIN_INTERVAL = 0.06          # seconds between picks (about 16 per second)


def ray_floor_point(near: Tuple[float, float, float], far: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    """Where the segment *near* -> *far* crosses z = 0, or None when it is parallel to or never reaches the floor."""
    dz = far[2] - near[2]
    if abs(dz) < 1e-12:
        return None
    t = -near[2] / dz
    if t < 0:
        return None
    return (near[0] + t * (far[0] - near[0]), near[1] + t * (far[1] - near[1]), 0.0)


def install_cursor_tracking(plotter, emit: Callable[[Optional[Tuple[float, float, float]]], None]):
    """Call ``emit((x, y, z))`` while the mouse moves over *plotter*, and ``emit(None)`` when it leaves.

    Uses a Qt event filter on the plotter's widget (VTK's own move events are not delivered without a button
    held). Returns the filter object; the caller keeps it alive with the viewport.
    """
    import vtk
    from PySide6.QtCore import QEvent, QObject

    picker = vtk.vtkCellPicker()
    picker.SetTolerance(0.0005)
    widget = plotter.interactor
    widget.setMouseTracking(True)

    def world_at(x: int, y: int):
        ren = plotter.renderer
        if picker.Pick(x, y, 0, ren) and picker.GetCellId() >= 0:
            return tuple(picker.GetPickPosition())
        pts = []
        for z in (0.0, 1.0):
            ren.SetDisplayPoint(x, y, z)
            ren.DisplayToWorld()
            w = ren.GetWorldPoint()
            pts.append((w[0] / w[3], w[1] / w[3], w[2] / w[3]))
        return ray_floor_point(pts[0], pts[1])

    class _Filter(QObject):
        last = 0.0

        def eventFilter(self, _obj, event):                  # noqa: N802 (Qt API)
            kind = event.type()
            if kind == QEvent.MouseMove:
                now = time.monotonic()
                if now - self.last >= _MIN_INTERVAL:
                    self.last = now
                    dpr = widget.devicePixelRatioF()
                    pos = event.position()
                    emit(world_at(int(pos.x() * dpr), int((widget.height() - 1 - pos.y()) * dpr)))
            elif kind == QEvent.Leave:
                emit(None)
            return False

    flt = _Filter(widget)
    widget.installEventFilter(flt)
    return flt
