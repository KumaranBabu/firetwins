"""Drive the real 3D Results window on the demo run (gui_run/) and save a screenshot of every step into gui_viewer/.

    python examples/demo_room_fire/gui_viewer_walkthrough.py

Run gui_walkthrough.py first: it makes gui_run/ (the FDS output this script loads).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtCore import Qt, QTimer                                              # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox   # noqa: E402

from pyfds.api import FdsApi                                                   # noqa: E402
from pyfds.gui.main_window import MainWindow                                   # noqa: E402

RUN = HERE / "gui_run"
OUT = HERE / "gui_viewer"
SMV = RUN / "demo_room.smv"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*"):
    if old.is_file():
        old.unlink()
shutil.rmtree(OUT / "shots", ignore_errors=True)


def _die(exc_type, exc, tb) -> None:
    import os, traceback
    traceback.print_exception(exc_type, exc, tb)
    sys.stdout.flush()
    os._exit(1)


sys.excepthook = _die
app = QApplication.instance() or QApplication([])
api = FdsApi()
main = MainWindow(api)
main.resize(1480, 900)
main.show()
shots: list = []


def pump(s: float = 0.3) -> None:
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(widget, name: str, settle: float = 0.5) -> None:
    pump(settle)
    widget.grab().save(str(OUT / f"{name}.png"))
    shots.append(name)
    print("  screenshot", name)


def drive(open_fn, name: str, fill=None, accept: bool = False, settle: float = 0.5) -> None:
    """open_fn opens a modal dialog; photograph it (after fill), then close it."""
    def handler() -> None:
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(150, handler)
            return
        if fill:
            fill(dlg)
        shot(dlg, name, settle)
        dlg.accept() if accept else dlg.reject()
    QTimer.singleShot(400, handler)
    open_fn()
    pump(0.4)


def click_at(world, name: str) -> None:
    """A real mouse click in the 3D view at the screen position of a world point, then a screenshot."""
    import vtk
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    pl = win.view.plotter
    c = vtk.vtkCoordinate()
    c.SetCoordinateSystemToWorld()
    c.SetValue(*world)
    d = c.GetComputedDoubleDisplayValue(pl.renderer)
    w = pl.interactor
    r = w.devicePixelRatioF()
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, QPoint(int(d[0] / r), int(w.height() - d[1] / r)))
    pump(0.6)
    print("  picked:", win.selected.text if win.selected else None)
    shot(win, name)


def menu_popup(win, title: str, name: str) -> None:
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == title:
            m = top.menu()
            m.popup(win.mapToGlobal(win.menuBar().actionGeometry(top).bottomLeft()))
            pump(0.4)
            shot(m, name)
            m.hide()
            return
    raise KeyError(title)


SL = "root/FDS Results/2D Slices/TEMPERATURE/SLICE_T_Y (Y = 2.4)/Mesh 1"
SL2 = "root/FDS Results/2D Slices/TEMPERATURE/SLICE_T_X (X = 3)/Mesh 1"
SMOKE = "root/FDS Results/3D Smoke/SOOT DENSITY/Mesh 1"
FIRE = "root/FDS Results/3D Smoke/HRRPUV/Mesh 1"
P3D = "root/FDS Results/Plot3D/TEMPERATURE"

# 1 -- start from the main window --------------------------------------------------------------
print("1 open the viewer from the main window")
menu_popup(main, "Results", "v01_results_menu")
main._show_results_window()
win = main._results_window
win.resize(1380, 860)
pump(1.0)
shot(win, "v02_empty_viewer")
menu_popup(win, "File", "v03_file_menu")

# 2 -- load the run -----------------------------------------------------------------------------
print("2 load results")
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(SMV), "Smokeview (*.smv)"))
win.open_results()
pump(1.5)
shot(win, "v04_results_loaded")
v = win.viewer
v.activate("geometry/fds_actual")
win.sync(True)
shot(win, "v05_geometry_on")

print("2a click an object")
click_at((3.0, 3.9, 1.2), "v05a_click_wall")
win.select(None)

print("2b rendering mode: walls as wireframe so the inside of the room can be seen")
from PySide6.QtWidgets import QComboBox                                  # noqa: E402
mode_box = win.findChildren(QComboBox)[0]                               # the rendering-mode box on the toolbar
mode_box.setCurrentIndex(mode_box.findData("wireframe"))
shot(win, "v05b_wireframe_walls")

# 3 -- slice, time bar --------------------------------------------------------------------------
print("3 slices and the time bar")
v.activate(SL)
win.sync(True)
pb = v.playback
win.slider.setValue(pb.n_frames // 2)
pump(1.0)
shot(win, "v06_slice_mid_run")
win.slider.setValue(pb.n_frames - 1)
pump(1.0)
shot(win, "v07_slice_end")
print("3b click a slice")
v.deactivate("geometry/fds_actual")
win.sync(True)
click_at((3.0, 2.4, 0.9), "v07a_click_slice")
win.select(None)
v.activate("geometry/fds_actual")
win.sync(True)
v.activate(SL2)
win.sync(True)
shot(win, "v08_two_slices")

# 4 -- 3D smoke and fire --------------------------------------------------------------------------
print("4 3D smoke / fire")
for nid in (SL, SL2):
    v.deactivate(nid)
for nid in (SMOKE, FIRE):
    try:
        v.activate(nid)
    except Exception as exc:                                     # noqa: BLE001
        print("  could not activate", nid, exc)
win.sync(True)
shot(win, "v09_smoke_and_fire")

# 5 -- Plot3D / isosurface -----------------------------------------------------------------------------
print("5 isosurface")
QInputDialog.getItem = staticmethod(lambda *a, **k: (P3D, True))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (300.0, True))
win.add_iso()
v.activate(P3D + "/Isosurfaces/Isosurface 1")
win.sync(True)
pump(1.0)
shot(win, "v10_isosurface_300C")

# 6 -- dialogs ------------------------------------------------------------------------------------------
print("6 colorbar, rendering, time plot")
QInputDialog.getItem = staticmethod(lambda *a, **k: ("TEMPERATURE", True))
v.activate(SL)
win.sync(True)
drive(win.colorbar_prefs, "v11_colorbar_dialog")
drive(win.rendering_prefs, "v12_rendering_dialog")
for csv in ("demo_room_hrr.csv", "demo_room_devc.csv"):
    QFileDialog.getOpenFileName = staticmethod(lambda *a, c=csv, **k: (str(RUN / c), "CSV (*.csv)"))
    win.load_csv()
pump(0.5)
shot(win, "v13a_csv_loaded")
win.time_plot()
pump(1.0)
plot = win._plot
for i in range(plot.list.count()):
    if plot.list.item(i).text().split("/")[-1].strip() in ("HRR", "TC_060", "TC_120", "TC_180", "TC_230") or "HRR" == plot.list.item(i).text():
        plot.list.item(i).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
print("  series:", [plot.list.item(i).text() for i in range(plot.list.count())][:12])
pump(1.0)
shot(plot, "v13_time_plot")
win._plot.close()

# 7 -- camera: views, section box ---------------------------------------------------------------------
print("7 views and section")
for name in ("top", "front", "side", "isometric"):
    v.standard_view(name)
    win._camera_changed()
    pump(0.8)
    shot(win, f"v14_view_{name}")
QInputDialog.getItem = staticmethod(lambda *a, **k: ("y_max", True))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (2.4, True))
win.section_plane()
pump(1.0)
shot(win, "v15_section_plane")
v.remove_section_box()
win.sync(True)

QInputDialog.getText = staticmethod(lambda *a, **k: ("Detector view", True))
v.standard_view("isometric")
win.new_view()
QInputDialog.getText = staticmethod(lambda *a, **k: ("0.6,0.6,0  5.4,0.6,0", True))
win.add_dimension()
answers = iter(["Burner", "3.0,2.4,0.5"])
QInputDialog.getText = staticmethod(lambda *a, **k: (next(answers), True))
win.add_label()
pump(1.0)
shot(win, "v16_view_dimension_label")

# 8 -- screenshots and the animation (the real output files) ---------------------------------------------------
print("8 screenshot and movie")
shots_dir = OUT / "shots"
shots_dir.mkdir(exist_ok=True)
from pyfds.api.viz import capture as cap                                 # noqa: E402
from pyfds.gui.results.dialogs import MovieDialog, ScreenshotDialog      # noqa: E402

v.activate(FIRE)
v.activate(SL)
win.sync(True)


def sdlg() -> None:
    ScreenshotDialog(v, win, (win.view.width(), win.view.height())).exec()


def mdlg() -> None:
    MovieDialog(v, win, (1280, 720)).exec()


drive(sdlg, "v17_screenshot_dialog")
drive(mdlg, "v18_movie_dialog")
renderer = win.view.make_renderer(v)
done = []
for t in (5.0, 10.0, 20.0):
    done += v.render_screenshots(v.screenshot_plan(str(shots_dir / f"t{int(t):02d}.png"), "single", t), renderer, (960, 540))
print("  screenshots:", done)
lo, hi = v.time_range()
plan = cap.movie_plan(str(OUT / "demo_room.mp4"), lo, hi, fps=10, speed=2.0, size=(960, 540))
res = v.render_movie(plan, renderer)
print("  movie:", res)
(OUT / "movie_result.json").write_text(json.dumps({k: str(x) for k, x in res.items()}, indent=1))

# 9 -- save the visualization -----------------------------------------------------------------------------------
print("9 save visualization")
dst = HERE / "demo_room.pyfdsv"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(dst), "PyFDS visualization (*.pyfdsv)"))
win.save_as()
pump(0.8)
shot(win, "v19_saved_visualization")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
win.close()
main.close()
print("done:", len(shots), "screenshots in", OUT)
app.quit()
