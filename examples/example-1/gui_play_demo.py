"""Play the finished demo run in the real 3D window (slice + flame + walls) and save screenshots of the time bar while it plays.

    python examples/example-1/gui_play_demo.py

Writes gui_viewer/p1_before_play.png, p2_playing.png, p3_playing_later.png, p4_paused.png and play_report.json
(frames drawn per second, how far the clock got).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QMessageBox  # noqa: E402

from pyfds.api import FdsApi                                        # noqa: E402
from pyfds.gui.main_window import MainWindow                        # noqa: E402

OUT = HERE / "gui_viewer"
SMV = HERE / "gui_run" / "example_1.smv"
SL = "root/FDS Results/2D Slices/TEMPERATURE/SLICE_T_Y (Y = 2.4)/Mesh 1"
FIRE = "root/FDS Results/3D Smoke/HRRPUV/Mesh 1"

app = QApplication.instance() or QApplication([])
main = MainWindow(FdsApi())
main.resize(1480, 900)
main.show()


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


main._show_results_window()
win = main._results_window
win.resize(1380, 860)
pump(1.0)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(SMV), "Smokeview (*.smv)"))
win.open_results()
pump(1.0)
v = win.viewer
for nid in ("geometry/fds_actual", SL, FIRE):
    v.activate(nid)
win.sync(True)
box = win.findChildren(QComboBox)[0]
box.setCurrentIndex(box.findData("wireframe"))
v.standard_view("isometric")
win._camera_changed()
pump(1.0)
win.grab().save(str(OUT / "p1_before_play.png"))

frames = []
orig = win.draw


def counting_draw() -> None:
    t = time.perf_counter()
    orig()
    frames.append((time.perf_counter() - t, v.time))


win.draw = counting_draw
t0 = time.perf_counter()
QTest.mouseClick(win.play_btn, Qt.LeftButton)
pump(3.0)
win.grab().save(str(OUT / "p2_playing.png"))
pump(3.0)
win.grab().save(str(OUT / "p3_playing_later.png"))
elapsed = time.perf_counter() - t0
QTest.mouseClick(win.play_btn, Qt.LeftButton)
pump(0.5)
win.grab().save(str(OUT / "p4_paused.png"))
win.draw = orig
n = len(frames)
rep = {"seconds_played": round(elapsed, 1), "frames_drawn": n, "frames_per_second": round(n / elapsed, 1),
       "slowest_frame_s": round(max(f[0] for f in frames), 2) if frames else None,
       "clock_reached_s": round(v.time, 2), "software_smoke_mapper": win.view.adapter.fast_volumes}
print(rep)
(OUT / "play_report.json").write_text(json.dumps(rep, indent=1))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
win.close()
main.close()
