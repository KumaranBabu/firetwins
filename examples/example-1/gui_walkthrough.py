"""Drive the real PyFDS desktop window through the whole demo case and save a screenshot of every step.

This opens the actual application window (Qt, native platform), uses its menus and dialogs exactly as a
user would (values are typed into the real dialogs by this script), runs the real FDS, and plays the
results back in the Results Viewer. Screenshots go to ``examples/example-1/gui/``.

    python examples/example-1/gui_walkthrough.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from PySide6.QtCore import Qt, QTimer                                   # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,   # noqa: E402
                               QLineEdit, QMessageBox)

from pyfds.api import FdsApi                                            # noqa: E402
from pyfds.core.viewport import CameraPreset, VisibilityFlags            # noqa: E402
from pyfds.gui.main_window import MainWindow                            # noqa: E402

OUT = HERE / "gui"
RUN = HERE / "gui_run"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()

def _die(exc_type, exc, tb) -> None:
    """An exception inside a Qt slot would otherwise be printed and ignored while the script carries on."""
    import os, traceback
    traceback.print_exception(exc_type, exc, tb)
    sys.stdout.flush()
    os._exit(1)


sys.excepthook = _die
app = QApplication.instance() or QApplication([])
api = FdsApi()
win = MainWindow(api)
win.resize(1480, 900)
win.show()
shots: list = []


def pump(seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(widget, name: str) -> None:
    pump(0.4)
    path = OUT / f"{name}.png"
    widget.grab().save(str(path))
    shots.append(name)
    print("  screenshot", path.name)


def _watchdog() -> None:
    """Any message box that appears while the script runs is photographed and dismissed."""
    m = app.activeModalWidget()
    if isinstance(m, QMessageBox):
        shot(m, f"message_{len(shots):02d}")
        m.accept()


wd = QTimer()
wd.timeout.connect(_watchdog)
wd.start(1500)


def set_field(dlg, name: str, value) -> None:
    w = dlg._fields[name]
    if isinstance(w, QCheckBox):
        w.setChecked(bool(value))
    elif isinstance(w, QComboBox):
        w.setCurrentText(str(value))
    else:
        w.setText(str(value))


def drive(open_fn, fill, name: str, accept: bool = True) -> None:
    """Run ``open_fn`` (opens a modal dialog); fill it, photograph it, then accept or cancel it."""
    def handler() -> None:
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(120, handler)
            return
        if fill:
            fill(dlg)
        shot(dlg, name)
        dlg.accept() if accept else dlg.reject()
    QTimer.singleShot(300, handler)
    open_fn()
    pump(0.4)


def menu_action(menu: str, text: str):
    """The action called ``text`` in the menu ``menu`` or in any submenu below the menu bar (menus move between releases)."""
    def walk(m):
        for act in m.actions():
            yield act
            if act.menu() is not None:
                yield from walk(act.menu())
    tops = sorted(win.menuBar().actions(), key=lambda t: t.text().replace("&", "") != menu)   # the named menu first
    for top in tops:
        for act in walk(top.menu()):
            if act.text().replace("&", "") == text:
                return act
    raise KeyError(f"{menu} > {text}")


def fields(**vals):
    return lambda dlg: [set_field(dlg, k, v) for k, v in vals.items()]


def view(preset=CameraPreset.ISOMETRIC, zoom: float = 1.0) -> None:
    win._on_camera_preset(preset)
    if zoom != 1.0:
        win.viewport_widget.plotter.camera.zoom(zoom)
        win.viewport_widget.plotter.render()
    pump(0.6)


# 01 ----------------------------------------------------------------------------------------------
print("1 new project")
shot(win, "01_new_project")

print("2 project settings and simulation parameters")
drive(win._on_project_settings, fields(chid="example_1", title="Example 1: room fire with door, window, heat detector"),
      "02a_project_settings")
def fill_sim(dlg):
    dlg.field_widget("time", "t_end").set_value(20.0)
    dlg.apply()                                   # what OK does; the script then closes the dialog without a second save


drive(win._on_simulation_parameters, fill_sim, "02b_simulation_parameters", accept=False)

print("3 mesh")
drive(lambda: win._on_add_entity("add_mesh"), fields(ijk="40,30,20", xb="0,6,0,4.5,0,3", name="DOMAIN"), "03a_add_mesh")
view(zoom=2.0)
shot(win, "03b_mesh_in_view")

print("4 library: wall construction")
def library_pick(category: str, entry: str):
    def fill(dlg):
        dlg.category.setCurrentIndex(dlg.category.findData(category))
        items = dlg.names.findItems(entry, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchExactly)
        dlg.names.setCurrentItem(items[0])
        dlg.add_button.click()
        pump(0.2)
    return fill
drive(menu_action("Model", "Library...").trigger, library_pick("surfaces", "gypsum_wall_25mm"), "04_library_wall_surface",
      accept=False)

print("5 geometry: room with door and window")
def fill_room(dlg):
    dlg.surface.setCurrentText("GYPSUM_WALL_25MM")
    dlg._add_row("S", 3.0, 0.9, 2.1, 0.0)
    dlg._add_row("E", 2.25, 1.2, 1.05, 0.9)
drive(menu_action("Draw", "Draw Room (walls, door, window)...").trigger, fill_room, "05a_draw_room")
view(zoom=2.0)
shot(win, "05b_room_in_view")

print("6 physics: burner, fuel")
drive(menu_action("Model", "Add Typed Surface (burner, supply, exhaust...)...").trigger,
      fields(kind="burner", name="BURNER_SURF", heat_release_rate=500, tau_q=-15, color="ORANGE"), "06a_burner_surface")
drive(lambda: win._on_add_entity("add_obstruction"),
      fields(xb="2.7,3.3,2.1,2.7,0,0.15", surf_id="BURNER_SURF", name="BURNER"), "06b_burner_block")
drive(lambda: win._on_add_entity("add_simple_reaction"), fields(fuel="PROPANE", heat_of_combustion=46000, name="PROPANE_FIRE"),
      "06c_reaction")

print("7 open boundaries")
menu_action("Model", "Open Mesh Boundaries").trigger()
pump(0.5)
shot(win, "07_open_boundaries")

print("8 instruments and pictures")
drive(menu_action("Model", "Library...").trigger, library_pick("heat_detectors", "heat_detector_74C"),
      "08a_library_heat_detector", accept=False)
drive(lambda: win._on_add_entity("add_device"),
      fields(quantity="LINK TEMPERATURE", xyz="3.0,2.4,2.35", name="HEAT_DET", prop_id="HEAT_DETECTOR_74C"),
      "08b_heat_detector_device")
for i, z in enumerate((0.6, 1.2, 1.8, 2.3)):
    drive(lambda: win._on_add_entity("add_thermocouple"), fields(xyz=f"3.0,2.4,{z}", devc_id=f"TC_{round(z * 100):03d}"),
          "08c_thermocouple" if i == 0 else f"_tc{i}", accept=True)
    if i:
        (OUT / f"_tc{i}.png").unlink(missing_ok=True)
drive(lambda: win._on_add_entity("add_slice"), fields(quantity="TEMPERATURE", plane="Y", position=2.4, name="SLICE_T_Y"),
      "08d_slice")
drive(lambda: win._on_add_entity("add_slice"), fields(quantity="TEMPERATURE", plane="X", position=3.0, name="SLICE_T_X"),
      "_slice2")
(OUT / "_slice2.png").unlink(missing_ok=True)

print("9 whole model")
win._on_toggle_visibility(VisibilityFlags.VENTS, False)       # View > Show/Hide > Vents: the green open-boundary faces hide the room
view(zoom=2.0)
shot(win, "09a_model_complete_isometric")
view(CameraPreset.FRONT, zoom=2.0)
shot(win, "09b_model_front")
view(zoom=2.0)

print("10 validate")
drive(win._on_validate, None, "10_validation_report")

print("11 save")
RUN.mkdir(exist_ok=True)
proj = HERE / "example_1.pyfds"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(proj), "PyFDS Project (*.pyfds)"))
win._on_save_as()
pump(0.5)
shot(win, "11_saved_project")

print("12 run")
import shutil
from pyfds.gui.run.model import RunSetup
shutil.rmtree(RUN, ignore_errors=True)
RUN.mkdir(exist_ok=True)
win._on_run_dialog(setup=RunSetup(mode="local", output_dir=str(RUN)))     # what Run Simulation's dialog returns
pump(1.0)
monitor = win.run_panel                       # docked Run Monitor tab (bottom panel)
assert monitor is not None, "the run monitor did not open"
marks = [0.12, 0.45, 0.8]
t0 = time.monotonic()
while time.monotonic() - t0 < 900:
    pump(0.5)
    frac = monitor.bar.value() / 1000.0
    if marks and frac >= marks[0]:
        shot(win, f"12{'abc'[3 - len(marks)]}_run_monitor_{int(marks[0] * 100)}pct")
        marks.pop(0)
    if monitor.state in ("done", "failed"):
        break
pump(2.0)
print("  run state:", monitor.state)
shot(win, "12d_run_monitor_finished")
assert monitor.state == "done", "FDS did not finish"
pump(2.0)

print("13 results viewer")
win._show_results_viewer(str(RUN))
viewer = win._results_viewer
pump(1.5)
shot(viewer, "13a_results_viewer_first_frame")
viewer.slider.setValue(viewer.slider.maximum() // 2)
pump(1.0)
shot(viewer, "13b_results_viewer_mid")
viewer.slider.setValue(viewer.slider.maximum())
pump(1.0)
shot(viewer, "13c_results_viewer_end")
viewer.layers.item(1).setCheckState(Qt.Checked) if viewer.layers.count() > 1 else None
pump(1.0)
shot(viewer, "13d_results_viewer_second_slice")
viewer.close()
shot(win, "14_main_window_after_run")
print("done:", len(shots), "screenshots in", OUT)
app.quit()
