"""The busy hourglass: its animation, the overlay and pointer it shows, and the two ways work runs under it."""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from pyfds.gui import busy as B


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _overlays(app):
    return [w for w in app.topLevelWidgets() if isinstance(w, B.BusyOverlay) and w.isVisible()]


def test_phase_runs_the_sand_then_turns_the_glass():
    assert B.phase(0.0) == (0.0, 0.0)
    assert B.phase(B.DRAIN_S / 2) == pytest.approx((0.5, 0.0))
    drained, turned = B.phase(B.DRAIN_S + B.FLIP_S / 2)
    assert drained == 1.0 and turned == pytest.approx(90.0)
    assert B.phase(B.DRAIN_S + B.FLIP_S + 0.25) == pytest.approx(B.phase(0.25))     # round and round


def _sand(seconds):
    img = QImage(80, 110, QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    B.paint_hourglass(p, QRectF(2, 2, 76, 104), seconds, QColor("black"))
    p.end()

    def count(y0, y1):
        n = 0
        for y in range(y0, y1):
            for x in range(20, 60):
                c = img.pixelColor(x, y)
                n += c.red() > 190 and 110 < c.green() < 215 and c.blue() < 140         # amber
        return n
    return count(12, 50), count(60, 98)                        # top bulb, bottom bulb


def test_sand_moves_from_the_top_bulb_to_the_bottom(app):
    top0, bottom0 = _sand(0.0)
    top1, bottom1 = _sand(B.DRAIN_S * 0.97)
    assert top0 > 200 and bottom0 < 20
    assert top1 < top0 / 4 and bottom1 > 200


def test_cursor_is_a_small_hourglass(app):
    cur = B.hourglass_cursor(1.0)
    assert cur.pixmap().width() == 32 and cur.hotSpot().x() == 16


def test_busy_shows_the_card_and_restores_the_pointer_after_an_error(app):
    host = QWidget()
    host.resize(600, 400)
    host.show()
    with pytest.raises(RuntimeError), B.busy(host, "Rendering the movie") as b:
        assert QApplication.overrideCursor() is not None
        assert b.overlay.isVisible() and b.overlay.geometry() == host.geometry()
        b.tick("Frame 3 of 90")
        assert b.overlay.title.text() == "Rendering the movie" and b.overlay.detail.text() == "Frame 3 of 90"
        raise RuntimeError("renderer failed")
    assert QApplication.overrideCursor() is None and not _overlays(app)
    host.close()


def test_run_busy_works_on_another_thread_and_hands_back_the_answer(app):
    host = QWidget()
    host.show()
    seen = {}

    def work(a, b=0):
        seen["thread"] = threading.current_thread().name
        seen["overlay"] = bool(_overlays(app))
        return a + b

    assert B.run_busy(host, "Previewing the model", work, 2, b=3) == 5
    assert seen == {"thread": "pyfds-busy", "overlay": True}
    assert QApplication.overrideCursor() is None and not _overlays(app)

    def boom():
        raise ValueError("FDS did not produce a preview of the model")
    with pytest.raises(ValueError, match="preview"):
        B.run_busy(host, "Previewing the model", boom)
    assert QApplication.overrideCursor() is None
    host.close()


def test_movie_frames_are_counted_on_the_card(app):
    from pyfds.gui.results.window_files import _ticking
    host = QWidget()
    drawn = []
    with B.busy(host, "Rendering the movie") as b:
        draw = _ticking(lambda *a: drawn.append(a), b, 3)
        for i in range(3):
            draw(f"f{i}.png", (64, 64), float(i), "Current")
            if i == 1:
                assert b.overlay.detail.text() == "Frame 2 of 3"
        assert b.overlay.detail.text() == "Frame 3 of 3 - joining the frames"
    assert len(drawn) == 3
