"""Run > Monitor Simulation: live progress, heat release curve and solver log of a running (or finished) case.

It reads the files FDS writes (``<CHID>.out`` and ``<CHID>_hrr.csv``) on a timer, so it works for a run
started from this window and for one started elsewhere, and it never blocks the solver.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

_TOTAL_TIME = re.compile(r"Total Time:\s+([0-9.]+)\s*s")


def read_progress(out_file: Path, t_end: float) -> Tuple[float, str]:
    """(simulated seconds so far, state) where state is ``waiting``, ``running``, ``done`` or ``failed``."""
    if not out_file.exists():
        return 0.0, "waiting"
    text = out_file.read_text(errors="replace")
    times = _TOTAL_TIME.findall(text)
    t = float(times[-1]) if times else 0.0
    if "STOP: FDS completed successfully" in text:
        return max(t, t_end), "done"
    if any(l.startswith("ERROR") for l in text.splitlines()):
        return t, "failed"
    return t, "running"


def read_hrr(csv_file: Path) -> List[Tuple[float, float]]:
    if not csv_file.exists():
        return []
    rows = []
    for line in csv_file.read_text(errors="replace").splitlines()[2:]:
        parts = line.split(",")
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue
    return rows


class HrrPlot(QWidget):
    """Heat release rate against time, drawn directly (no plotting library on the GUI thread)."""

    def __init__(self, t_end: float, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.t_end = max(t_end, 1e-6)
        self.points: List[Tuple[float, float]] = []
        self.setMinimumHeight(170)

    def set_points(self, pts: List[Tuple[float, float]]) -> None:
        self.points = pts
        self.update()

    def paintEvent(self, _event) -> None:           # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 52, 12, 14, 28
        area = QRectF(left, top, w - left - right, h - top - bottom)
        p.fillRect(self.rect(), QColor("#fbfaf8"))
        p.setPen(QPen(QColor("#c9c4ba")))
        p.drawRect(area)
        ymax = max([q for _, q in self.points] + [1.0])
        ymax = ymax * 1.1
        p.setPen(QColor("#555"))
        for i in range(5):
            y = area.bottom() - area.height() * i / 4
            p.drawText(2, int(y) + 4, f"{ymax * i / 4:.0f}")
            p.setPen(QPen(QColor("#e4e0d8")))
            p.drawLine(int(area.left()), int(y), int(area.right()), int(y))
            p.setPen(QColor("#555"))
        for i in range(5):
            x = area.left() + area.width() * i / 4
            p.drawText(int(x) - 10, h - 10, f"{self.t_end * i / 4:.0f}")
        p.drawText(int(area.left()) + 4, top + 12, "Heat release rate (kW)  vs  time (s)")
        if len(self.points) > 1:
            pen = QPen(QColor("#c2410c"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            pts = [QPointF(area.left() + area.width() * t / self.t_end, area.bottom() - area.height() * q / ymax)
                   for t, q in self.points]
            for a, b in zip(pts[:-1], pts[1:]):
                p.drawLine(a, b)
        p.end()


class _MonitorBody:
    """Progress bar, heat release curve and solver log; mixed into a dialog or a dockable panel."""

    def __init__(self, output_dir: Optional[str], chid: str, t_end: float, parent: Optional[QWidget] = None,
                 open_results: Optional[Callable[[], None]] = None, interval_ms: int = 500) -> None:
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.open_results = open_results
        self.state = "idle"

        root = QVBoxLayout(self)
        self.headline = QLabel("")
        self.headline.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(self.headline)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFormat("%p%")
        root.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setStyleSheet("color: #555;")
        root.addWidget(self.detail)
        self.plot = HrrPlot(t_end)
        root.addWidget(self.plot)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        root.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.results_button = QPushButton("Open Results Viewer")
        self.results_button.setEnabled(False)
        self.results_button.clicked.connect(lambda: self.open_results and self.open_results())
        row.addWidget(self.results_button)
        self.extra_row = row
        root.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.out_file = self.hrr_file = None
        if output_dir:
            self.watch(output_dir, chid, t_end, open_results)
        else:
            self.headline.setText("No run yet - start one with Run > Run Simulation.")

    def watch(self, output_dir: str, chid: str, t_end: float, open_results: Optional[Callable[[], None]] = None) -> None:
        """Follow the files of another run (a panel is reused from run to run)."""
        self.out_file = Path(output_dir) / f"{chid}.out"
        self.hrr_file = Path(output_dir) / f"{chid}_hrr.csv"
        self.t_end = t_end
        self.plot.t_end = max(t_end, 1e-6)
        self.open_results = open_results
        self.state = "waiting"
        self.timer.start(self.interval_ms)
        self.refresh()

    def refresh(self) -> None:
        t, self.state = read_progress(self.out_file, self.t_end)
        frac = 0.0 if self.t_end <= 0 else min(t / self.t_end, 1.0)
        self.bar.setValue(int(frac * 1000))
        headline = {"waiting": "Waiting for FDS to start...", "running": "Running", "done": "Finished",
                    "failed": "FDS stopped with an error"}[self.state]
        self.headline.setText(headline)
        pts = read_hrr(self.hrr_file)
        self.plot.set_points(pts)
        now = f"simulated {t:.1f} s of {self.t_end:g} s"
        if pts:
            now += f"  |  heat release now {pts[-1][1]:.0f} kW, peak {max(q for _, q in pts):.0f} kW"
        self.detail.setText(now)
        if self.out_file.exists():
            tail = self.out_file.read_text(errors="replace").splitlines()[-14:]
            self.log.setPlainText("\n".join(tail))
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        self.results_button.setEnabled(self.state == "done")
        if self.state in ("done", "failed"):
            self.timer.stop()



class RunMonitorPanel(_MonitorBody, QWidget):
    """The monitor as a dock panel (starts idle; ``watch()`` points it at a run)."""

    def __init__(self, parent: Optional[QWidget] = None, interval_ms: int = 500) -> None:
        super().__init__(None, "", 0.0, parent, interval_ms=interval_ms)


class RunMonitorDialog(_MonitorBody, QDialog):
    """Non-modal window that follows a run."""

    def __init__(self, output_dir: str, chid: str, t_end: float, parent: Optional[QWidget] = None,
                 open_results: Optional[Callable[[], None]] = None, interval_ms: int = 500) -> None:
        super().__init__(output_dir, chid, t_end, parent, open_results, interval_ms)
        self.setWindowTitle(f"Simulation Monitor - {chid}")
        self.resize(720, 560)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        self.extra_row.addWidget(close)

    def closeEvent(self, event) -> None:            # noqa: N802
        self.timer.stop()
        super().closeEvent(event)
