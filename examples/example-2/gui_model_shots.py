"""Open the imported couch case in the main window and save screenshots (gui/): the model, and the same view in focus mode.
    python examples/example-2/gui_model_shots.py"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtWidgets import QApplication                           # noqa: E402

from pyfds import CameraPreset                                       # noqa: E402
from pyfds.api import FdsApi                                         # noqa: E402
from pyfds.gui.main_window import MainWindow                         # noqa: E402

OUT = HERE / "gui"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
api = FdsApi()
api.session.open_project(str(HERE / "couch.pyfds"))
w = MainWindow(api)
w.resize(1500, 900)
w.show()


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


pump(2)
w._on_camera_preset(CameraPreset.ISOMETRIC)
w.explorer.select_entity("obstructions", api.project.obstructions[1])
pump(2)
w.grab().save(str(OUT / "01_imported_couch_model.png"))
w.toggle_focus_mode(True)
pump(2)
w.grab().save(str(OUT / "02_focus_mode.png"))
sys.stdout.flush()
os._exit(0)
