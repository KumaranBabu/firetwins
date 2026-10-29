"""Example 2 - burning couch: open the original FDS input (FDS distribution, Examples/Fires/couch.fds) in the real PyFDS
editor, inspect it, shorten the run to 25 s, validate, run FDS on 4 MPI processes from the Run dialog and follow it.

    python client_demos/example_2/scripts/walkthrough.py            (about 35 minutes; needs the desktop)

Outputs: client_demos/example_2/couch.pyfds + couch.fds, the run in client_demos/example_2/run/, screenshots and
validation_log.json in documentation/screenshots/example_2/.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))
from demo_kit import ROOT, Demo, ScreenRecorder                              # noqa: E402

from PySide6.QtWidgets import QFileDialog                                      # noqa: E402

from pyfds.api import FdsApi                                                    # noqa: E402
from pyfds.core.viewport import CameraPreset, VisibilityFlags                   # noqa: E402
from pyfds.gui.main_window import MainWindow                                    # noqa: E402

ORIGINAL = ROOT / "fds_smv" / "FDS6" / "Examples" / "Fires" / "couch.fds"
SOURCE = HERE / "couch_original.fds"                     # the untouched FDS example, kept beside the demo
RUN = HERE / "run"
PROJECT = HERE / "couch.pyfds"
shutil.copyfile(ORIGINAL, SOURCE)

d = Demo("example_2")
api = FdsApi()
win = MainWindow(api)
win.restore_keymap = lambda: None
win.showMaximized()
d.pump(2.0)
rec = ScreenRecorder(ROOT / "documentation" / "videos" / "example_2_open_and_run.mp4")


def view(preset=CameraPreset.ISOMETRIC, zoom: float = 1.0) -> None:
    win._on_camera_preset(preset)
    if zoom != 1.0:
        win.viewport_widget.plotter.camera.zoom(zoom)
        win.viewport_widget.plotter.render()
    d.pump(0.6)


# A -- open the FDS file ------------------------------------------------------------------------------------------------
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(SOURCE), "FDS/PyFDS Files (*.fds *.pyfds)"))
win._on_open()
d.pump(2.0)
view(zoom=1.6)
d.shot(win, "opened", "File > Open with couch_original.fds: the couch (purple upholstery on a gypsum base) and the "
                      "four meshes made by the MULT line are listed in the Project Explorer and drawn in the 3D view.")
p = api.project
d.step("A1 open original FDS input", "ok" if p.obstructions else "failed",
       {"meshes_in_file": len(p.meshes), "meshes_run": api.meshes.run_count(), "obstructions": len(p.obstructions),
        "surfaces": [s.name for s in p.surfaces], "materials": [m.name for m in p.materials], "t_end": p.params.t_end})

# B -- inspect ------------------------------------------------------------------------------------------------------------
for attr, title, pick, cap in (
        ("meshes", "Edit Meshes", None, "Model > Edit Meshes: one 2.5 x 2.5 x 2.4 m mesh of 25 x 25 x 24 cells (0.1 m); "
                                        "its multiplier (MULT_ID) repeats it 2 x 2 to cover 5 x 5 m."),
        ("surfaces", "Edit Surfaces", "UPHOLSTERY", "Model > Edit Surfaces, UPHOLSTERY: fabric (0.5 mm) over foam (100 mm), "
                                                   "burns away; the properties are the FDS example's (marked 'fabricated')."),
        ("materials", "Edit Materials", "FOAM", "Model > Edit Materials, FOAM: density, conductivity, specific heat and "
                                                "the pyrolysis reaction that produces POLYURETHANE fuel gas."),
        ("particles", "Edit Particles", None, "Model > Edit Particles: the static 'ignitor particle', a 1000 C cylinder "
                                              "placed on the seat cushion that starts the fire.")):
    items = getattr(p, attr)
    if items:
        d.drive(lambda a=attr, t=title, s=(pick or items[0].name): win._on_edit_collection(a, t, s),
                f"editor_{attr}", cap, accept=False)
d.step("B1 inspect model in the editors", "ok")


def fill_sim(dlg) -> None:
    dlg.field_widget("time", "t_end").set_value(25.0)
    dlg.apply()


d.drive(win._on_simulation_parameters, "simulation_parameters",
        "Model > Simulation Parameters: T_END reduced from 600 s to 25 s so the demo run stays short; "
        "nothing else in the case is changed.", fill_sim, accept=False)
d.step("B2 shorten run", "ok" if p.params.t_end == 25.0 else "failed", {"t_end": p.params.t_end})

win._on_toggle_visibility(VisibilityFlags.VENTS, True)
view(CameraPreset.FRONT, zoom=1.6)
d.shot(win, "front_view", "Front view: the open vent in the south wall (green) is the only opening; the other "
                          "boundaries are the default solid wall surface.")
view(zoom=1.6)

# C -- validate, save --------------------------------------------------------------------------------------------------------
win._on_validate()
d.pump(1.0)
rep = api.validation.validate()
d.shot(win, "validation", "Model > Validate Project on the imported case.")
d.step("C1 validation", "ok" if not rep.errors else "failed",
       {"errors": [r.message for r in rep.errors], "warnings": [r.message for r in rep.warnings],
        "notes": [r.message for r in rep.infos]})
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(PROJECT), "PyFDS Files (*.pyfds)"))
win._on_save_as()
d.pump(0.6)
from pyfds.io.fds_writer import FdsWriter                                         # noqa: E402
FdsWriter().write(api.project, str(HERE / "couch.fds"))
d.step("C2 save", "ok" if PROJECT.exists() else "failed", str(PROJECT))

# D -- run on 4 processes ---------------------------------------------------------------------------------------------------
shutil.rmtree(RUN, ignore_errors=True)
RUN.mkdir(parents=True)


def fill_run(dlg) -> None:
    dlg.folder.setText(str(RUN))
    dlg.smokeview_box.setChecked(False)
    d.pump(0.3)


started = time.monotonic()
d.drive(win._on_run_simulation, "run_dialog",
        "Analysis > Run Simulation with four meshes: 'This computer, in parallel (MPI)' is preselected with one process per "
        "mesh; the table shows which mesh each process computes and the summary shows the cells per process.", fill_run)
d.step("D1 run started", "ok" if win._run_handle is not None else "failed", str(RUN))
if win._run_handle is None:
    d.step("D2 run finished", "failed", "the run did not start")
    rec.close()
    os._exit(1)
rec.timelapse(10.0)                                          # the long FDS run: one video frame every 10 s
monitor = win.run_panel
marks = [0.2, 0.5, 0.8]
while time.monotonic() - started < 3 * 3600:
    d.pump(2.0)
    frac = monitor.bar.value() / 1000.0
    if marks and frac >= marks[0] and monitor.state == "running":
        d.shot(win, f"run_monitor_{int(marks[0] * 100)}", f"Run Monitor at {int(marks[0] * 100)} %.")
        marks.pop(0)
    if monitor.state in ("done", "failed"):
        break
rec.realtime()
d.pump(3.0)
out_text = (RUN / "couch.out").read_text(errors="replace") if (RUN / "couch.out").exists() else ""
wall = next((ln.split(":")[-1].strip() for ln in out_text.splitlines() if "Total Elapsed Wall Clock Time" in ln), "?")
d.shot(win, "run_finished", "Run finished on 4 MPI processes.")
d.step("D2 run finished", "ok" if "STOP: FDS completed successfully" in out_text else "failed",
       {"state": monitor.state, "wall_clock_s": wall,
        "mpi_processes": next((ln.split(":")[-1].strip() for ln in out_text.splitlines() if "Number of MPI Processes" in ln), "?"),
        "minutes_waited": round((time.monotonic() - started) / 60, 1)})
d.pump(2.0)
d.step("E1 screen recording", "ok", rec.close())
win._run_poll.stop() if getattr(win, "_run_poll", None) else None
os._exit(0)
