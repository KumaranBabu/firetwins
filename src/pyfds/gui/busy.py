"""The busy hourglass: a painted, animated hourglass shown over a window while the application works.

Two ways in:

* ``run_busy(parent, "Previewing the model", fn, *args)`` runs *fn* on a worker thread and keeps the hourglass turning
  (paint and timer events only: clicks and keys wait) until it returns; its result comes back, its exception is
  raised again here. Only for work that touches no widget.
* ``with busy(parent, "Rendering the movie") as b: ... b.tick("Frame 3 of 90")`` for work that must stay on the GUI
  thread (3D rendering): each ``tick`` moves the sand on and can change the detail line.

The card is its own frameless, see-through window above *parent*'s window, because the 3D views are native VTK windows
that a child widget cannot paint over. The mouse pointer becomes a small hourglass of the same drawing.
"""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from PySide6.QtCore import QEasingCurve, QEvent, QEventLoop, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

#: Seconds for the sand to run through, then to turn the glass over.
DRAIN_S, FLIP_S = 3.0, 0.65
_CYCLE = DRAIN_S + FLIP_S
_EASE = QEasingCurve(QEasingCurve.InOutCubic)

_SAND_LIGHT, _SAND_DARK = QColor("#f6cf7a"), QColor("#d4922f")
_WOOD_LIGHT, _WOOD_DARK = QColor("#b9824a"), QColor("#6e4522")


def phase(seconds: float) -> tuple:
    """``(drained, turned)`` at *seconds* into the animation: the fraction of sand run through (0..1) and the turn of
    the glass in degrees (0 while the sand runs, then 0..180 eased)."""
    t = seconds % _CYCLE
    if t < DRAIN_S:
        return t / DRAIN_S, 0.0
    return 1.0, 180.0 * _EASE.valueForProgress((t - DRAIN_S) / FLIP_S)


def _glass() -> QPainterPath:
    """The two bulbs and the neck, in drawing units: x -24..24, y -42..42, the neck at y = 0."""
    p = QPainterPath(QPointF(-24, -42))
    p.cubicTo(-25, -18, -4.5, -10, -2.6, 0)
    p.cubicTo(-4.5, 10, -25, 18, -24, 42)
    p.lineTo(24, 42)
    p.cubicTo(25, 18, 4.5, 10, 2.6, 0)
    p.cubicTo(4.5, -10, 25, -18, 24, -42)
    p.closeSubpath()
    return p


_GLASS = _glass()


def _band(top: float, bottom: float, dip: float = 0.0) -> QPainterPath:
    """Everything between *top* and *bottom*; a positive *dip* sinks the middle of the top edge (a falling surface),
    a negative one raises it (a heap)."""
    p = QPainterPath(QPointF(-40, top))
    p.quadTo(0, top + 2 * dip, 40, top)
    p.lineTo(40, bottom)
    p.lineTo(-40, bottom)
    p.closeSubpath()
    return p


def paint_hourglass(painter: QPainter, rect: QRectF, seconds: float, glass: QColor, *, detail: bool = True) -> None:
    """Draw the hourglass as it is *seconds* into the animation, fitted into *rect*. *glass* tints the glass outline
    (the palette's text colour reads well on both themes); ``detail=False`` leaves out the falling grains (cursor)."""
    drained, turned = phase(seconds)
    flip = turned / 180.0
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    scale = min(rect.width() / 76.0, rect.height() / 104.0)
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.rotate(turned)

    sand = QLinearGradient(0, -42, 0, 42)
    sand.setColorAt(0, _SAND_LIGHT)
    sand.setColorAt(1, _SAND_DARK)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(glass.red(), glass.green(), glass.blue(), 28))     # the glass itself, faintly
    painter.drawPath(_GLASS)

    painter.setBrush(QBrush(sand))
    if turned == 0.0:
        top = -30.0 * (1.0 - drained)                                          # the sand left above the neck
        if drained < 1.0:
            painter.drawPath(_GLASS.intersected(_band(top, 0.0, dip=min(6.0, 26.0 * drained) * (1.0 - drained))))
        heap = 7.0 * math.sin(math.pi * drained)
        level = 42.0 - 30.0 * drained                                          # the sand already through
        painter.drawPath(_GLASS.intersected(_band(level, 44.0, dip=-heap)))
        if 0.0 < drained < 0.985:                                              # the stream and its grains
            end = level - heap
            painter.drawRect(QRectF(-0.8, 0.0, 1.6, end))
            if detail:
                painter.setBrush(_SAND_LIGHT.lighter(112))
                for k in range(5):
                    y = (seconds * 46.0 + k * end / 5.0) % max(end, 1.0)
                    painter.drawEllipse(QPointF(0.55 * math.sin(7 * y), y), 1.1, 1.1)
    else:                                                                      # turning over: the heap slides to the neck
        painter.drawPath(_GLASS.intersected(_band(12.0 - 12.0 * flip, 42.0 - 12.0 * flip)))

    pen = QPen(QColor(glass.red(), glass.green(), glass.blue(), 190), 1.6)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(_GLASS)
    if detail:                                                                 # a highlight down the left of the glass
        shine = QPainterPath(QPointF(-19, -38))
        shine.cubicTo(-20, -22, -8, -12, -6, -5)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1.8, Qt.SolidLine, Qt.RoundCap))
        painter.drawPath(shine)
        shine = QPainterPath(QPointF(-6, 6))
        shine.cubicTo(-9, 13, -19, 20, -19, 34)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawPath(shine)

    wood = QLinearGradient(-34, 0, 34, 0)
    wood.setColorAt(0, _WOOD_DARK)
    wood.setColorAt(0.35, _WOOD_LIGHT)
    wood.setColorAt(1, _WOOD_DARK)
    painter.setPen(QPen(_WOOD_DARK.darker(130), 0.8))
    painter.setBrush(QBrush(wood))
    for y in (-50.0, 42.0):                                                    # the end caps
        painter.drawRoundedRect(QRectF(-36, y, 72, 8), 2.5, 2.5)
    for x in (-32.5, 29.5):                                                    # the two posts
        painter.drawRoundedRect(QRectF(x, -42, 3, 84), 1.2, 1.2)
    painter.restore()


def hourglass_cursor(seconds: float, size: int = 32) -> QCursor:
    """The mouse pointer: a small hourglass at *seconds* into the animation, its hot spot in the middle."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    paint_hourglass(p, QRectF(1, 1, size - 2, size - 2), seconds, QColor("#202020"), detail=False)
    p.end()
    return QCursor(pix, size // 2, size // 2)


class Hourglass(QWidget):
    """The animated hourglass on its own (30 frames a second while it is shown)."""

    def __init__(self, parent: QWidget | None = None, size: int = 120) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)                                          # room for the glass on its side
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)

    def seconds(self) -> float:
        return time.monotonic() - self._t0

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        h = 0.76 * self.height()                                               # the turning glass's diagonal fits
        paint_hourglass(p, QRectF((self.width() - h * 0.73) / 2, (self.height() - h) / 2, h * 0.73, h), self.seconds(),
                        self.palette().color(QPalette.WindowText))
        p.end()


class BusyOverlay(QWidget):
    """The card over a window: the hourglass, what is being done, a detail line and the time so far.

    A frameless, see-through tool window covering *parent*'s window (dimmed), so it is drawn above native 3D views and
    takes every click meant for the window underneath."""

    def __init__(self, parent: QWidget | None, message: str) -> None:
        self._host = parent.window() if parent is not None else None
        super().__init__(self._host, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("busyOverlay")
        self._t0 = time.monotonic()

        self.card = QWidget(self)
        self.card.setObjectName("busyCard")
        self.card.setAttribute(Qt.WA_StyledBackground)
        pal = self.palette()
        self.card.setStyleSheet(
            f"#busyCard {{ background: {pal.color(QPalette.Window).name()}; border-radius: 14px;"
            f" border: 1px solid {pal.color(QPalette.Mid).name()}; }}")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.card.setGraphicsEffect(shadow)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(28, 22, 28, 18)
        lay.setSpacing(6)
        self.hourglass = Hourglass(self.card)
        lay.addWidget(self.hourglass, 0, Qt.AlignHCenter)
        self.title = QLabel(message, self.card)
        self.title.setAlignment(Qt.AlignCenter)
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.15)
        font.setBold(True)
        self.title.setFont(font)
        self.detail = QLabel("", self.card)
        self.elapsed = QLabel("", self.card)
        for label in (self.detail, self.elapsed):
            label.setAlignment(Qt.AlignCenter)
            label.setEnabled(False)                                            # the palette's quieter text colour
        lay.addWidget(self.title)
        lay.addWidget(self.detail)
        lay.addWidget(self.elapsed)
        self.detail.hide()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._show_elapsed)
        self._clock.start(250)
        if self._host is not None:
            self._host.installEventFilter(self)

    # -- what the card says ---------------------------------------------------------------------------------------------
    def set_detail(self, text: str | None) -> None:
        if text is None:
            return
        self.detail.setText(text)
        self.detail.setVisible(bool(text))
        self._place()

    def _show_elapsed(self) -> None:
        s = int(time.monotonic() - self._t0)
        if s >= 2:
            self.elapsed.setText(f"Elapsed {s // 60}:{s % 60:02d}")

    # -- where it is ------------------------------------------------------------------------------------------------------
    def _place(self) -> None:
        if self._host is not None:
            self.setGeometry(self._host.geometry())
        else:
            self.resize(420, 300)
        self.card.adjustSize()
        w = max(self.card.width(), 300)
        self.card.resize(w, self.card.height())
        self.card.move((self.width() - w) // 2, (self.height() - self.card.height()) // 2)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._host and event.type() in (QEvent.Move, QEvent.Resize):
            self._place()
        return False

    def showEvent(self, event) -> None:
        self._place()
        super().showEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 70))
        p.end()

    def mousePressEvent(self, event) -> None:                                  # the window underneath is busy
        event.accept()

    def close_overlay(self) -> None:
        if self._host is not None:
            self._host.removeEventFilter(self)
        self._clock.stop()
        self.hourglass._timer.stop()
        self.hide()
        self.deleteLater()


class Busy:
    """One busy spell: the overlay and the hourglass pointer, until :meth:`finish`."""

    def __init__(self, parent: QWidget | None, message: str) -> None:
        self._app = QApplication.instance()
        self._t0 = time.monotonic()
        self._last = 0.0
        self.overlay = BusyOverlay(parent, message)
        self.overlay.show()
        QApplication.setOverrideCursor(hourglass_cursor(0.0))
        self._pump()

    def tick(self, detail: str | None = None) -> None:
        """Move the sand on (at most 30 times a second) and optionally change the detail line. Clicks and keys
        are held back, so nothing else starts while this work runs."""
        self.overlay.set_detail(detail)
        now = time.monotonic()
        if detail is not None or now - self._last >= 1 / 30:
            self._pump()

    def _pump(self) -> None:
        self._last = time.monotonic()
        QApplication.changeOverrideCursor(hourglass_cursor(self._last - self._t0))
        if self._app is not None:
            self._app.processEvents(QEventLoop.ExcludeUserInputEvents)

    def finish(self) -> None:
        QApplication.restoreOverrideCursor()
        self.overlay.close_overlay()


@contextmanager
def busy(parent: QWidget | None, message: str) -> Iterator[Busy]:
    """Show the hourglass over *parent*'s window while the ``with`` block runs on the GUI thread; call ``tick()``
    from inside the work to keep it moving."""
    b = Busy(parent, message)
    try:
        yield b
    finally:
        b.finish()


def run_busy(parent: QWidget | None, message: str, fn: Callable[..., Any], *args: Any,
             detail: Callable[[], str | None] | None = None, **kwargs: Any) -> Any:
    """Run ``fn(*args, **kwargs)`` on a worker thread with the hourglass turning over *parent*'s window; return its
    result or raise its exception here. *fn* must not touch widgets. *detail*, if given, is asked for the detail line
    a few times a second."""
    out: dict = {}

    def work() -> None:
        try:
            out["value"] = fn(*args, **kwargs)
        except BaseException as exc:                                           # noqa: BLE001 - raised again below
            out["error"] = exc

    worker = threading.Thread(target=work, name="pyfds-busy", daemon=True)
    with busy(parent, message) as b:
        worker.start()
        while worker.is_alive():
            worker.join(1 / 30)
            b.tick(detail() if detail else None)
    if "error" in out:
        raise out["error"]
    return out.get("value")
