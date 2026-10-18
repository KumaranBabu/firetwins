"""Results window: real-time movie recording (Record / Pause / Resume / Stop), row V-68."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QToolBar

from pyfds.api.viz import recorder as rec

RECORD_FPS = 15


class ResultsWindowRecordMixin:
    _recorder: Optional[rec.LiveRecorder] = None

    def _build_record_controls(self) -> None:
        """Record / Pause / Stop buttons in the bar under the 3D view and a REC indicator in the status bar."""
        bar = QToolBar("Record", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        self.rec_btn, self.rec_pause_btn, self.rec_stop_btn = QPushButton("Record"), QPushButton("Pause"), QPushButton("Stop")
        self.rec_btn.setToolTip("Record the 3D view as it plays, in real time (an MP4 file)")
        self.rec_btn.clicked.connect(lambda: self._try(self.record_start, "Record"))
        self.rec_pause_btn.clicked.connect(lambda: self._try(self.record_pause_resume, "Record"))
        self.rec_stop_btn.clicked.connect(lambda: self._try(self.record_stop, "Record"))
        for b in (self.rec_btn, self.rec_pause_btn, self.rec_stop_btn):
            bar.addWidget(b)
        self.status_rec = QLabel("")
        self.status_rec.setStyleSheet("color: #c00; font-weight: 600;")
        self.statusBar().addPermanentWidget(self.status_rec)
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(int(1000 / RECORD_FPS))
        self._rec_timer.timeout.connect(self._record_tick)
        self._record_ui()

    def _record_ui(self) -> None:
        r = self._recorder
        state = r.state if r is not None else rec.IDLE
        self.rec_btn.setEnabled(state in (rec.IDLE, rec.STOPPED))
        self.rec_pause_btn.setEnabled(state in (rec.RECORDING, rec.PAUSED))
        self.rec_pause_btn.setText("Resume" if state == rec.PAUSED else "Pause")
        self.rec_stop_btn.setEnabled(state in (rec.RECORDING, rec.PAUSED))
        if state == rec.RECORDING:
            self.status_rec.setText(f"REC {r.elapsed:4.1f} s")
        elif state == rec.PAUSED:
            self.status_rec.setText(f"REC paused {r.elapsed:4.1f} s")
        else:
            self.status_rec.setText("")

    def record_start(self, path: Optional[str] = None) -> None:
        if self._recorder is not None and self._recorder.state in (rec.RECORDING, rec.PAUSED):
            raise ValueError("a recording is already running")
        if path is None:
            path = self._ask_file(False, "Record Movie", "MP4 video (*.mp4)", "recording.mp4")
        if not path:
            return
        self._recorder = rec.LiveRecorder(path, fps=RECORD_FPS)
        self._recorder.start()
        self._rec_timer.start()
        self._record_tick()
        self.statusBar().showMessage("Recording: play, orbit and pan as you like; Pause and Stop are under the 3D view")

    def record_pause_resume(self) -> None:
        r = self._recorder
        if r is None or r.state not in (rec.RECORDING, rec.PAUSED):
            raise ValueError("nothing is being recorded")
        r.pause() if r.state == rec.RECORDING else r.resume()
        self._record_ui()

    def record_stop(self) -> Optional[dict]:
        r = self._recorder
        if r is None or r.state not in (rec.RECORDING, rec.PAUSED):
            raise ValueError("nothing is being recorded")
        self._rec_timer.stop()
        res = r.stop()
        self._record_ui()
        where = res["path"] if res["encoded"] else f"{res['frames_dir']} (no video encoder found: numbered PNG frames)"
        self.statusBar().showMessage(f"Recorded {res['frames']} frames ({res['seconds']} s): {where}")
        if not getattr(self, "_quiet", False):
            QMessageBox.information(self, "Record Movie", f"{res['frames']} frames, {res['seconds']} s\n{where}")
        return res

    def _record_tick(self) -> None:
        r = self._recorder
        if r is None or r.state != rec.RECORDING:
            self._record_ui()
            return
        r.add_frame(self._grab_view())
        self._record_ui()

    def _grab_view(self):
        pl = self.view.plotter
        pl.render()                                   # screenshot() draws only when asked to render first
        return pl.screenshot(return_img=True).copy()

    def _abort_recording(self) -> None:
        if self._recorder is not None and self._recorder.state in (rec.RECORDING, rec.PAUSED):
            self._rec_timer.stop()
            self._recorder.abort()
