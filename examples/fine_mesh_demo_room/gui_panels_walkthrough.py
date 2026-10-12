"""Take the screenshots of the work panels (manual section 11) with the finished demo case loaded.

    python examples/demo_room_fire/gui_panels_walkthrough.py

Writes gui/15a_properties_panel.png ... gui/15g_results_tab.png. Nothing in the saved project is changed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtCore import QEvent, QPointF, Qt                      # noqa: E402
from PySide6.QtGui import QMouseEvent                               # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox                          # noqa: E402

from pyfds.api import FdsApi                                        # noqa: E402
from pyfds.core.viewport import VisibilityFlags                     # noqa: E402
from pyfds.gui.main_window import MainWindow                        # noqa: E402

CHID = "fine_mesh_demo_room"
PROJECT = HERE / f"{CHID}_gui.pyfds"
RUN = HERE / "gui_run"
OUT = HERE / "gui"
SL = "root/FDS Results/2D Slices/TEMPERATURE/SLICE_T_Y (Y = 2.4)/Mesh 1"
FIRE = "root/FDS Results/3D Smoke/HRRPUV/Mesh 1"

app = QApplication.instance() or QApplication([])
api = FdsApi()
api.load(str(PROJECT))
win = MainWindow(api)
win._current_project_path = str(PROJECT)
win._last_run_dir = str(RUN)
win.resize(1500, 900)
win.show()


def pump(s: float) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def shot(name: str) -> None:
    pump(0.6)
    win.grab().save(str(OUT / f"{name}.png"))
    print("saved", name)


def move_mouse(x: float, y: float) -> None:
    w = win.viewport_widget.plotter.interactor
    p = QPointF(x, y)
    app.sendEvent(w, QMouseEvent(QEvent.MouseMove, p, w.mapToGlobal(p), Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def show_messages(panel) -> None:
    win._show_messages(panel)
    win.resizeDocks([win.messages_dock], [300], Qt.Vertical)


pump(2.0)
win.show_model_tab()
api.viewport.set_camera(api.viewport.state.camera)
win._on_camera_preset(__import__("pyfds.core.viewport", fromlist=["CameraPreset"]).CameraPreset.ISOMETRIC)
pump(1.0)

# 1. Properties panel: the burner selected, cursor readout in the status bar
burner = next(o for o in api.project.obstructions if o.name == "BURNER")
win.explorer.select_entity("obstructions", burner)
move_mouse(520, 330)
shot("15a_properties_panel")

# 2. Validation panel
win._on_validate()
win.resizeDocks([win.messages_dock], [300], Qt.Vertical)
shot("15b_validation_panel")

# 3. Run monitor panel following the finished run
win.run_panel.watch(str(RUN), CHID, api.project.params.t_end,
                    lambda: win.show_results_tab(str(RUN / f"{CHID}.smv")))
show_messages(win.run_panel)
win._update_run_label()
shot("15c_run_monitor_panel")

# 4. Layers panel (the grid and the labels hidden, as an example)
win.layers_dock.show()
win.layers_dock.raise_()
api.viewport.set_visibility(VisibilityFlags.GRID, False)
api.viewport.set_visibility(VisibilityFlags.LABELS, False)
win.layers_panel.sync()
win.messages_dock.hide()
shot("15d_layers_panel")
win.layers_panel.set_all(True)
win.explorer_dock.raise_()

# 5. Output: the FDS input preview
show_messages(win.output_panel)
win.output_panel.tabs.setCurrentIndex(1)
shot("15e_output_fds_preview")

# 6. Results tab of the bottom panel
win.results_panel.refresh()
show_messages(win.results_panel)
shot("15f_results_panel")

# 7. The results viewer in its own tab next to the model
win.messages_dock.hide()
rw = win.show_results_tab(str(RUN / f"{CHID}.smv"))
pump(2.0)
for nid in ("geometry/fds_actual", SL, FIRE):
    rw.viewer.activate(nid)
rw.sync(True)
rw.viewer.standard_view("isometric")
rw._camera_changed()
rw.viewer.set_time(float(api.project.params.t_end))
rw.sync()
pump(2.0)
shot("15g_results_tab")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)     # no "Save changes?" prompt while closing
win.close()
