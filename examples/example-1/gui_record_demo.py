"""Photograph the real-time recording in the results viewer for the post-processing manual (gui_viewer/r*.png) and
save a short live film (gui_viewer/example_1_live.mp4).  Run after gui_viewer_walkthrough.py; needs a display."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.results.window import ResultsWindow  # noqa: E402

OUT = HERE / "gui_viewer"
app = QApplication([])
QMessageBox.information = staticmethod(lambda *a, **k: None)
w = ResultsWindow(FdsApi())
w.resize(1380, 860)
w.show()
w.open_results(str(HERE / "gui_run" / "example_1.smv"))


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(widget, name: str) -> None:
    pump(0.3)
    widget.grab().save(str(OUT / f"{name}.png"))
    print("  screenshot", name)


w.viewer.activate("geometry/fds_actual")
w.viewer.activate("root/FDS Results/2D Slices/TEMPERATURE/SLICE_T_Y (Y = 2.4)/Mesh 1")
w.sync(True)
pump(1.5)

for top in w.menuBar().actions():
    if top.text().replace("&", "") == "File":
        m = top.menu()
        m.popup(w.mapToGlobal(w.menuBar().actionGeometry(top).bottomLeft()))
        pump(0.4)
        shot(m, "r1_file_menu")
        m.hide()

film = OUT / "example_1_live.mp4"
w.record_start(str(film))
pump(1.0)
w._play_pause()
pump(2.5)
shot(w, "r2_recording")
w.record_pause_resume()
shot(w, "r3_paused")
w.record_pause_resume()
pump(1.5)
res = w.record_stop()
print(res)
sys.stdout.flush()
os._exit(0)
