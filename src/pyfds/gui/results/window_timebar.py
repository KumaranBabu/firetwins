"""Results window: time bar and playback."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QPushButton, QSlider, QToolBar


class ResultsWindowTimebarMixin:
    # -- time controls ------------------------------------------------------------------------------------------
    def _build_time_bar(self) -> None:
        bar = QToolBar("Time", self)
        bar.setMovable(False)
        self.addToolBar(Qt.BottomToolBarArea, bar)
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self._play_pause)
        step_b, step_f = QPushButton("<"), QPushButton(">")
        from pyfds.gui.icons import icon
        self._play_ui(False)
        step_b.setIcon(icon("stepback"))
        step_f.setIcon(icon("stepfwd"))
        step_b.clicked.connect(lambda: self._step(-1))
        step_f.clicked.connect(lambda: self._step(1))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimumWidth(320)
        self.slider.valueChanged.connect(self._seek)
        self.time_label = QLabel("-")
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 100.0)
        self.speed.setValue(self.viewer.viz.playback_speed)
        self.speed.setPrefix("x")
        self.speed.valueChanged.connect(lambda x: self._try(lambda: (self.viewer.set_speed(x), self._status_hook() if getattr(self, "_status_hook", None) else None)))
        self.loop = QCheckBox("Loop")
        self.loop.toggled.connect(self.viewer.set_loop)
        for w in (step_b, self.play_btn, step_f, self.slider, self.time_label, self.speed, self.loop):
            bar.addWidget(w)

    def _play_ui(self, playing: bool) -> None:
        from pyfds.gui.icons import icon
        self.play_btn.setText("Pause" if playing else "Play")
        self.play_btn.setIcon(icon("pause" if playing else "play"))

    def _play_pause(self) -> None:
        pb = self.viewer.playback
        if pb is None:
            return
        playing = pb.toggle()
        self._play_ui(playing)
        self._last_tick = None
        if playing:
            self.viewer.prefetch_async()
        (self._timer.start if playing else self._timer.stop)()

    def _tick(self) -> None:
        now = time.perf_counter()
        last, self._last_tick = getattr(self, "_last_tick", None), now
        if last and hasattr(self, "status_fps"):
            self.status_fps.setText(f"{1.0 / max(now - last, 1e-6):.0f} fps")
        pb = self.viewer.playback
        if pb is None:
            self._timer.stop()
            return
        pb.tick(min(max(now - last, self._timer.interval() / 1000.0), 0.5) if last else self._timer.interval() / 1000.0)   # real time: slow frames are skipped, not stretched
        if not pb.playing:
            self._timer.stop()
            self._play_ui(False)
        self.viewer.time = float(pb.time)
        self.sync()

    def _step(self, n: int) -> None:
        pb = self.viewer.playback
        if pb is not None:
            pb.step(n) if hasattr(pb, "step") else pb.seek_index(max(0, min(pb.index + n, pb.n_frames - 1)))
            self.viewer.time = float(pb.time)
            self.sync()

    def _seek(self, i: int) -> None:
        pb = self.viewer.playback
        if pb is not None:
            pb.seek_index(i)
            self.viewer.time = float(pb.time)
            self.sync()
