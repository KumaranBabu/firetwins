"""Results > Results Viewer: play a run's slices back with real FDS data (RES-02).

Layers, playback and probing come from ``api.scene``; the picture is drawn by ``api.slice_view``. The window
only holds the controls and shows the PNG it is given.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

_SPEEDS = [("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("5x", 5.0), ("10x", 10.0)]


class ResultsViewerDialog(QDialog):
    def __init__(self, api: Any, parent: Optional[QWidget] = None, folder: Optional[str] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Results Viewer")
        self.resize(1050, 720)
        self._cache: Dict[Tuple, bytes] = {}
        self._last_tick = time.monotonic()
        root = QHBoxLayout(self)

        # left: layers and display
        left = QVBoxLayout()
        self.folder_label = QLabel("No results opened")
        self.folder_label.setWordWrap(True)
        left.addWidget(self.folder_label)
        open_btn = QPushButton("Open Results Folder...")
        open_btn.clicked.connect(self._choose_folder)
        left.addWidget(open_btn)
        left.addWidget(QLabel("Slices (tick one to show)"))
        self.layers = QListWidget()
        self.layers.itemChanged.connect(self._layer_changed)
        left.addWidget(self.layers, 1)
        disp = QGroupBox("Display")
        df = QFormLayout(disp)
        self.cmap = QComboBox()
        self.cmap.addItems(api.slice_view.colormaps())
        self.vmin = QDoubleSpinBox(); self.vmax = QDoubleSpinBox()
        for s in (self.vmin, self.vmax):
            s.setRange(-1e6, 1e6); s.setDecimals(1)
        self.auto = QCheckBox("Same colour range for all frames")
        self.auto.setChecked(True)
        df.addRow("Colour map", self.cmap)
        df.addRow("Minimum", self.vmin)
        df.addRow("Maximum", self.vmax)
        df.addRow(self.auto)
        left.addWidget(disp)
        probe = QGroupBox("Probe a point (m)")
        pf = QFormLayout(probe)
        self.px, self.py, self.pz = (QDoubleSpinBox() for _ in range(3))
        for s, v in ((self.px, 3.0), (self.py, 2.4), (self.pz, 1.2)):
            s.setRange(-1000, 1000); s.setDecimals(2); s.setSingleStep(0.1); s.setValue(v)
            s.valueChanged.connect(self._update_probe)
        row = QHBoxLayout()
        for s in (self.px, self.py, self.pz):
            row.addWidget(s)
        pf.addRow("x, y, z", row)
        self.probe_out = QLabel("")
        self.probe_out.setWordWrap(True)
        pf.addRow(self.probe_out)
        left.addWidget(probe)
        root.addLayout(left, 0)

        # right: picture and transport
        right = QVBoxLayout()
        self.image = QLabel("Open a results folder to begin")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(520, 400)
        self.image.setStyleSheet("background: #ffffff; border: 1px solid #c9c4ba;")
        right.addWidget(self.image, 1)
        bar = QHBoxLayout()
        self.first = QPushButton("|<"); self.back = QPushButton("<"); self.play = QPushButton("Play")
        self.fwd = QPushButton(">"); self.last = QPushButton(">|")
        for b in (self.first, self.back, self.play, self.fwd, self.last):
            b.setMinimumWidth(48)
            bar.addWidget(b)
        self.loop = QCheckBox("Loop")
        self.speed = QComboBox()
        for label, _ in _SPEEDS:
            self.speed.addItem(label)
        self.speed.setCurrentText("1x")
        bar.addWidget(self.loop)
        bar.addWidget(QLabel("Speed"))
        bar.addWidget(self.speed)
        bar.addStretch(1)
        self.time_label = QLabel("t = 0.0 s")
        self.time_label.setStyleSheet("font-weight: 600;")
        bar.addWidget(self.time_label)
        right.addLayout(bar)
        self.slider = QSlider(Qt.Horizontal)
        right.addWidget(self.slider)
        root.addLayout(right, 1)

        self.first.clicked.connect(lambda: self._seek(0))
        self.last.clicked.connect(lambda: self._seek(-1))
        self.back.clicked.connect(lambda: self._step(-1))
        self.fwd.clicked.connect(lambda: self._step(1))
        self.play.clicked.connect(self._toggle)
        self.slider.valueChanged.connect(self._slider_moved)
        self.cmap.currentIndexChanged.connect(self._redraw)
        self.vmin.valueChanged.connect(self._redraw)
        self.vmax.valueChanged.connect(self._redraw)
        self.auto.toggled.connect(self._redraw)
        self.speed.currentIndexChanged.connect(self._speed_changed)
        self.loop.toggled.connect(lambda on: self._pb() and self._pb().set_loop(on))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)
        self._set_enabled(False)
        if folder:
            self.open_folder(folder)

    # -- data ------------------------------------------------------------------
    def _pb(self):
        return self.api.scene.playback if self.api.scene.scene.layers else None

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Simulation Output Directory")
        if d:
            self.open_folder(d)

    def open_folder(self, folder: str) -> None:
        try:
            self.api.scene.clear()
            self.api.scene.open_results(folder)
            layers = self.api.scene.add_slices()
        except Exception as exc:
            QMessageBox.warning(self, "No results to show", str(exc))
            return
        self._cache.clear()
        self.folder_label.setText(folder)
        self.layers.blockSignals(True)
        self.layers.clear()
        for i, layer in enumerate(layers):
            item = QListWidgetItem(f"{layer.quantity.lower()}  ({layer.name})")
            item.setData(Qt.UserRole, layer.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if i == 0 else Qt.Unchecked)
            self.layers.addItem(item)
        self.layers.blockSignals(False)
        for i, layer in enumerate(layers):
            self.api.scene.set_visible(layer.name, i == 0)
        pb = self.api.scene.playback
        self.slider.blockSignals(True)
        self.slider.setRange(0, pb.n_frames - 1)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._set_enabled(True)
        self._speed_changed()
        self._redraw()

    def _set_enabled(self, on: bool) -> None:
        for w in (self.first, self.back, self.play, self.fwd, self.last, self.slider, self.loop, self.speed):
            w.setEnabled(on)

    def _current_layer(self):
        for i in range(self.layers.count()):
            it = self.layers.item(i)
            if it.checkState() == Qt.Checked:
                return self.api.scene.scene.layer(it.data(Qt.UserRole))
        return None

    # -- transport --------------------------------------------------------------
    def _speed_changed(self) -> None:
        pb = self._pb()
        if pb:
            pb.set_speed(_SPEEDS[self.speed.currentIndex()][1])

    def _toggle(self) -> None:
        pb = self._pb()
        if not pb:
            return
        pb.toggle()
        self.play.setText("Pause" if pb.playing else "Play")
        self._last_tick = time.monotonic()

    def _seek(self, i: int) -> None:
        pb = self._pb()
        if pb:
            pb.pause(); self.play.setText("Play")
            pb.seek_index(i)
            self._sync()

    def _step(self, n: int) -> None:
        pb = self._pb()
        if pb:
            pb.step(n); self.play.setText("Play")
            self._sync()

    def _slider_moved(self, v: int) -> None:
        pb = self._pb()
        if pb and v != pb.index:
            pb.seek_index(v)
            self._redraw(sync_slider=False)

    def _tick(self) -> None:
        pb = self._pb()
        if not pb or not pb.playing:
            return
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        if pb.tick(dt):
            self._sync()
        if not pb.playing:
            self.play.setText("Play")

    def _sync(self) -> None:
        self._redraw()

    # -- drawing ----------------------------------------------------------------
    def _layer_changed(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.Checked:                 # one picture at a time
            self.layers.blockSignals(True)
            for i in range(self.layers.count()):
                other = self.layers.item(i)
                if other is not item:
                    other.setCheckState(Qt.Unchecked)
            self.layers.blockSignals(False)
        for i in range(self.layers.count()):
            it = self.layers.item(i)
            self.api.scene.set_visible(it.data(Qt.UserRole), it.checkState() == Qt.Checked)
        self._redraw()

    def _redraw(self, *_args, sync_slider: bool = True) -> None:
        pb = self._pb()
        layer = self._current_layer()
        if pb is None or layer is None:
            return
        idx = layer.index_at(pb.time)
        opts = {"colormap": self.cmap.currentText()}
        if not self.auto.isChecked():
            opts.update(vmin=self.vmin.value(), vmax=self.vmax.value())
            if self.vmin.value() >= self.vmax.value():
                return
        else:
            lo, hi = self.api.slice_view.bounds(layer.result, idx, **{"colormap": opts["colormap"]})
            for s, v in ((self.vmin, lo), (self.vmax, hi)):
                s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        key = (layer.name, idx, tuple(sorted(opts.items())))
        png = self._cache.get(key)
        if png is None:
            png = self.api.slice_view.render_bytes(layer.result, idx, layer.mesh, dpi=90, size=(6.4, 5.0), **opts)
            if len(self._cache) > 120:
                self._cache.clear()
            self._cache[key] = png
        pix = QPixmap()
        pix.loadFromData(png)
        self.image.setPixmap(pix.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.time_label.setText(f"t = {pb.time:.1f} s   (frame {pb.index + 1} of {pb.n_frames})")
        if sync_slider:
            self.slider.blockSignals(True); self.slider.setValue(pb.index); self.slider.blockSignals(False)
        self._update_probe()

    def _update_probe(self, *_a) -> None:
        pb = self._pb()
        if pb is None:
            return
        hits = self.api.scene.probe((self.px.value(), self.py.value(), self.pz.value()))
        shown = [h for h in hits if self._current_layer() and h["layer"] == self._current_layer().name] or hits[:1]
        self.probe_out.setText("no data at this point on the shown slice" if not shown else
                               "  ".join(f"{h['quantity'].lower()}: {h['value']:.1f} {h['units']}" for h in shown))

    def resizeEvent(self, event) -> None:           # noqa: N802
        super().resizeEvent(event)
        if self.image.pixmap() is not None and self._pb():
            self._redraw()

    def closeEvent(self, event) -> None:            # noqa: N802
        self.timer.stop()
        super().closeEvent(event)
