"""Open the couch results in the 3D results viewer and save screenshots (gui_viewer/): the geometry, the temperature slice
through the couch, and the flame (HRRPUV) with the slice at the end of the run.   python examples/example-2/gui_viewer_shots.py"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

from pyfds.api import FdsApi                                         # noqa: E402
from pyfds.gui.results.window import ResultsWindow                   # noqa: E402

OUT = HERE / "gui_viewer"
OUT.mkdir(exist_ok=True)
SLICE = "root/FDS Results/2D Slices/TEMPERATURE/SLCF_0 (X = 2.5)/Mesh {n}"
SLICE2 = "root/FDS Results/2D Slices/TEMPERATURE/SLCF_0 (X = 2.6)/Mesh {n}"
FLAME = "root/FDS Results/3D Smoke/HRRPUV/Mesh {n}"

app = QApplication.instance() or QApplication([])
QMessageBox.information = staticmethod(lambda *a, **k: None)
win = ResultsWindow(FdsApi())
win.resize(1400, 850)
win.show()


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


win.open_results(str(HERE / "gui_run" / "couch.smv"))
pump(3)
v = win.viewer
v.activate("geometry/fds_actual")
win.sync(True)
v.standard_view("isometric")
win._camera_changed()
pump(2)
win.grab().save(str(OUT / "c1_geometry.png"))

for n in (1, 3):
    v.activate(SLICE.format(n=n))
for n in (2, 4):
    v.activate(SLICE2.format(n=n))
win.sync(True)
win._seek(win.slider.maximum())
pump(3)
win.grab().save(str(OUT / "c2_temperature_slice_end.png"))

for n in (1, 2, 3, 4):
    v.activate(FLAME.format(n=n))
win.sync(True)
pump(3)
win.grab().save(str(OUT / "c3_flame_and_slice_end.png"))
print("time", v.time)
sys.stdout.flush()
os._exit(0)
