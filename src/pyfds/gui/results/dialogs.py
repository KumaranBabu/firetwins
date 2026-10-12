"""Results dialogs that are more than a list of fields: Screenshot, Movie, Tour Editor, Section Box, Skybox, window size."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from pyfds.api.viz import capture as cap
from pyfds.api.viz import model as vm
from pyfds.api.viz import views as vw


def _buttons(dlg: QDialog, ok: str = "OK") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(ok)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


def _file_row(edit: QLineEdit, save: bool, filt: str, parent: QWidget) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    b = QPushButton("...")

    def pick() -> None:
        fn = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
        p, _ = fn(parent, "Choose file", edit.text(), filt)
        if p:
            edit.setText(p)

    b.clicked.connect(pick)
    lay.addWidget(edit)
    lay.addWidget(b)
    return row


class ScreenshotDialog(QDialog):
    """Size, creation mode (single / multiple / from file) with its fields, and the views to include."""

    def __init__(self, viewer, parent: Optional[QWidget] = None, default_size=(1280, 720)) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setWindowTitle("Screenshot")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)
        self.path = QLineEdit("screenshot.png")
        form.addRow("File", _file_row(self.path, True, "PNG (*.png);;JPEG (*.jpg)", self))
        self.w, self.h = QSpinBox(), QSpinBox()
        for s, v in ((self.w, default_size[0]), (self.h, default_size[1])):
            s.setRange(16, 16384)
            s.setValue(v)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.w)
        rl.addWidget(QLabel("x"))
        rl.addWidget(self.h)
        form.addRow("Size", row)
        self.mode = QComboBox()
        self.mode.addItems(["single", "multiple", "file"])
        form.addRow("Creation", self.mode)
        lo, hi = viewer.time_range()
        self.time = QDoubleSpinBox()
        self.start, self.end, self.step = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for s, v in ((self.time, viewer.time), (self.start, lo), (self.end, hi), (self.step, max((hi - lo) / 10, 0.1))):
            s.setRange(-1e6, 1e6)
            s.setDecimals(3)
            s.setValue(v)
        form.addRow("Time (single)", self.time)
        form.addRow("Start time", self.start)
        form.addRow("End time", self.end)
        form.addRow("Interval", self.step)
        self.tsv = QLineEdit()
        form.addRow("Times file (.tsv)", _file_row(self.tsv, False, "TSV (*.tsv);;All files (*)", self))
        self.views = QListWidget()
        self.views.setSelectionMode(QAbstractItemView.MultiSelection)
        for name in [cap.CURRENT] + [v.name for v in viewer.viz.views]:
            self.views.addItem(name)
        self.views.item(0).setSelected(True)
        form.addRow("Views", self.views)
        lay.addWidget(_buttons(self, "Create"))

    def shots(self) -> List[cap.Shot]:
        views = [i.text() for i in self.views.selectedItems()] or [cap.CURRENT]
        mode = self.mode.currentText()
        return self.viewer.screenshot_plan(self.path.text(), mode, self.time.value(), views[0], self.start.value(),
                                           self.end.value(), self.step.value(), views, self.tsv.text() or None)

    def size(self):
        return (self.w.value(), self.h.value())


class MovieDialog(QDialog):
    def __init__(self, viewer, parent: Optional[QWidget] = None, window_size=(1280, 720), panorama: bool = False) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.window_size = window_size
        self.panorama = panorama
        self.setWindowTitle("360 Movie" if panorama else "Movie")
        form = QFormLayout(self)
        self.path = QLineEdit("movie.mp4")
        form.addRow("File", _file_row(self.path, True, "MP4 (*.mp4)", self))
        self.w, self.h = QSpinBox(), QSpinBox()
        for s, v in ((self.w, window_size[0]), (self.h, window_size[1])):
            s.setRange(16, 8192)
            s.setValue(v)
        self.use_window = QCheckBox("Use window size")
        self.use_window.setChecked(True)
        form.addRow("Video width", self.w)
        if panorama:                                       # equirectangular: height is always half the width
            self.w.setRange(64, 16384)
            self.w.setValue(2048)
            self.use_window.setChecked(False)
            self.use_window.hide()
            self.h.hide()
            form.addRow(QLabel("Equirectangular 2:1; every frame is six 90-degree views stitched together"))
        else:
            form.addRow("Video height", self.h)
            form.addRow("", self.use_window)
        self.fps = QSpinBox()
        self.fps.setRange(1, 120)
        self.fps.setValue(30)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 1000)
        self.speed.setValue(1.0)
        self.speed.setSuffix(" x")
        lo, hi = viewer.time_range()
        self.begin, self.end = QDoubleSpinBox(), QDoubleSpinBox()
        for s, v in ((self.begin, lo), (self.end, hi)):
            s.setRange(-1e6, 1e6)
            s.setDecimals(3)
            s.setValue(v)
        self.bitrate = QSpinBox()
        self.bitrate.setRange(100, 100000)
        self.bitrate.setValue(6000)
        self.bitrate.setSuffix(" kbit/s")
        self.view = QComboBox()
        self.view.addItems([cap.CURRENT] + [v.name for v in viewer.viz.views])
        for label, w in (("Frame rate", self.fps), ("Speed", self.speed), ("Begin time", self.begin), ("End time", self.end),
                         ("Data rate", self.bitrate), ("View", self.view)):
            form.addRow(label, w)
        enc = viewer.encoder_path()
        form.addRow(QLabel("Encoder: " + (Path(enc).name if enc else "none found - PNG frames will be kept")))
        form.addWidget(_buttons(self, "Create"))

    def plan(self) -> cap.MoviePlan:
        if self.panorama:
            return cap.movie360_plan(self.path.text(), self.begin.value(), self.end.value(), self.fps.value(), self.speed.value(),
                                     self.w.value())
        size = self.window_size if self.use_window.isChecked() else (self.w.value(), self.h.value())
        return cap.movie_plan(self.path.text(), self.begin.value(), self.end.value(), self.fps.value(), self.speed.value(), size)


class SectionBoxDialog(QDialog):
    """Up to six planes, each ticked on or off; values start at the model bounds."""

    NAMES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")

    def __init__(self, viewer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setWindowTitle("Section Box")
        box = vw.active_section(viewer.viz)
        if box is None:
            raise ValueError("the active view has no section box: use View > Add Section Box first")
        self.rows = {}
        form = QFormLayout(self)
        for name in self.NAMES:
            chk = QCheckBox("on")
            val = QDoubleSpinBox()
            val.setRange(-1e6, 1e6)
            val.setDecimals(3)
            b = viewer.run.bounds() if viewer.run else (0, 1, 0, 1, 0, 1)
            on, cur = box.planes.get(name, (False, b[self.NAMES.index(name)]))
            val.setValue(float(cur))
            chk.setChecked(bool(on))
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(val)
            rl.addWidget(chk)
            form.addRow(name.replace("_", " ").upper(), row)
            self.rows[name] = (chk, val)
        form.addWidget(_buttons(self))

    def apply(self) -> None:
        self.viewer.set_section_planes({n: (c.isChecked(), v.value()) for n, (c, v) in self.rows.items()})


class TourEditor(QDialog):
    """Keyframe table: Time, Transition; add / remove / shift / duplicate / record camera; repeat and delay."""

    def __init__(self, viewer, view: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.viewer, self.view = viewer, view
        self.setWindowTitle(f"Tour Editor - {view}")
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.repeat = QCheckBox("Repeat")
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 1e6)
        self.delay.setPrefix("delay ")
        self.delay.setSuffix(" s")
        top.addWidget(self.repeat)
        top.addWidget(self.delay)
        top.addStretch()
        lay.addLayout(top)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Time (s)", "Transition"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        for text, fn in (("Add (current camera)", self.add), ("Record camera", self.record), ("Remove", self.remove),
                         ("Shift times...", self.shift), ("Duplicate", self.duplicate)):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, f=fn: self._guard(f))
            row.addWidget(b)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        box.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        lay.addWidget(box)
        self.repeat.toggled.connect(lambda _c: self._guard(self._save_tour))
        self.delay.editingFinished.connect(lambda: self._guard(self._save_tour))
        self.reload()

    def _guard(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            QMessageBox.warning(self, "Tour Editor", f"{type(exc).__name__}: {exc}")
        self.reload()

    def _tour(self) -> vm.Tour:
        return self.viewer._tour(self.view)

    def reload(self) -> None:
        t = self._tour()
        self.repeat.blockSignals(True)
        self.repeat.setChecked(t.repeat)
        self.repeat.blockSignals(False)
        self.delay.setValue(t.repeat_delay)
        self.table.setRowCount(len(t.keyframes))
        for i, k in enumerate(t.keyframes):
            self.table.setItem(i, 0, QTableWidgetItem(f"{k.time:g}"))
            self.table.setItem(i, 1, QTableWidgetItem(k.transition))

    def _save_tour(self) -> None:
        self.viewer.set_tour(self.view, self.repeat.isChecked(), self.delay.value())

    def selected(self) -> List[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def add(self) -> None:
        self.viewer.add_keyframe(self.viewer.time, self.view)

    def record(self) -> None:
        for i in self.selected():
            self.viewer.set_keyframe(i, self.view, record_camera=True)

    def remove(self) -> None:
        self.viewer.remove_keyframes(self.selected(), self.view)

    def shift(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        off, ok = QInputDialog.getDouble(self, "Shift times", "Offset in seconds (negative = earlier)", 0.0, -1e6, 1e6, 3)
        if ok:
            self.viewer.shift_keyframes(self.selected(), offset=off, view=self.view)

    def duplicate(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        delay, ok = QInputDialog.getDouble(self, "Duplicate keyframes", "Last keyframe delay (s)", 2.0, 0.001, 1e6, 3)
        if ok:
            self.viewer.duplicate_keyframes(self.selected(), "end_of_tour", last_delay=delay, view=self.view)

    def commit_table(self) -> None:
        """Apply times and transitions edited directly in the table."""
        t = self._tour()
        for i, k in enumerate(list(t.keyframes)):
            try:
                tm = float(self.table.item(i, 0).text())
            except (ValueError, AttributeError):
                continue
            tr = self.table.item(i, 1).text()
            if tm != k.time:
                self.viewer.set_keyframe(i, self.view, time=tm)
            if tr != k.transition:
                self.viewer.set_keyframe(i, self.view, transition=tr)

    def accept(self) -> None:                                  # noqa: D401
        try:
            self.commit_table()
        except Exception as exc:
            QMessageBox.warning(self, "Tour Editor", f"{type(exc).__name__}: {exc}")
            return
        super().accept()


class SkyboxDialog(QDialog):
    KINDS = ("none", "predefined", "image360", "cubemap", "split_cubemap")

    def __init__(self, viewer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Skybox")
        sb = viewer.viz.skybox
        form = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItems(self.KINDS)
        self.kind.setCurrentText(sb.kind)
        self.files = QLineEdit(";".join(sb.files))
        self.files.setToolTip("Image files separated by ;  (360 image / cubemap: 1, split cubemap: 6)")
        self.rot = QDoubleSpinBox()
        self.rot.setRange(-360, 360)
        self.rot.setValue(sb.z_rotation)
        self.show_box = QCheckBox("Show skybox")
        self.show_box.setChecked(sb.show)
        self.compress = QCheckBox("Compress textures")
        self.compress.setChecked(sb.compress_textures)
        for label, w in (("Type", self.kind), ("Image files", self.files), ("Z rotation", self.rot), ("", self.show_box),
                         ("", self.compress)):
            form.addRow(label, w)
        form.addWidget(_buttons(self))

    def values(self) -> dict:
        files = [f for f in self.files.text().split(";") if f.strip()]
        return dict(kind=self.kind.currentText(), files=files, z_rotation=self.rot.value(), show=self.show_box.isChecked(),
                    compress_textures=self.compress.isChecked())


class WindowSizeDialog(QDialog):
    """Edit 3D Window Size: width, height, and Set Window Size / Match Aspect Ratio."""

    def __init__(self, width: int, height: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit 3D Window Size")
        form = QFormLayout(self)
        self.w, self.h = QSpinBox(), QSpinBox()
        for s, v in ((self.w, width), (self.h, height)):
            s.setRange(100, 8000)
            s.setValue(v)
        self.mode = QComboBox()
        self.mode.addItems(["Set Window Size", "Match Aspect Ratio"])
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        form.addRow("Mode", self.mode)
        form.addWidget(_buttons(self))
