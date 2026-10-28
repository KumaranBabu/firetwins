"""Example 1 - room fire: build the case in the real PyFDS editor, validate it, run FDS from the Run dialog, follow the
Run Monitor, then post-process in PyFDS Results and in Smokeview. Every screenshot in the manual comes from here.

    python client_demos/example_1/scripts/walkthrough.py            (about 15 minutes; needs the desktop)

Outputs: client_demos/example_1/example_1.pyfds + example_1.fds, the FDS run in client_demos/example_1/run/,
screenshots and validation_log.json in documentation/screenshots/example_1/.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))
from demo_kit import ROOT, Demo, ScreenRecorder                             # noqa: E402

from PySide6.QtWidgets import QFileDialog, QMessageBox                          # noqa: E402

from pyfds.api import FdsApi                                                    # noqa: E402
from pyfds.core.viewport import CameraPreset, VisibilityFlags                   # noqa: E402
from pyfds.gui.main_window import MainWindow                                    # noqa: E402

RUN = HERE / "run"
PROJECT = HERE / "example_1.pyfds"
d = Demo("example_1")
api = FdsApi()
win = MainWindow(api)
win.restore_keymap = lambda: None
win.showMaximized()
d.pump(2.0)
rec = ScreenRecorder(ROOT / "documentation" / "videos" / "example_1_build_and_run.mp4")


def view(preset=CameraPreset.ISOMETRIC, zoom: float = 1.0) -> None:
    win._on_camera_preset(preset)
    if zoom != 1.0:
        win.viewport_widget.plotter.camera.zoom(zoom)
        win.viewport_widget.plotter.render()
    d.pump(0.6)


# A -- start -------------------------------------------------------------------------------------------------------
d.shot(win, "editor_start", "PyFDS opens maximized with an empty project: menus and toolbars at the top, the "
                            "Project Explorer and Properties on the left, the 3D view in the centre.")
d.step("A1 launch PyFDS editor", "ok", f"window {win.width()}x{win.height()}")
d.menu_shot(win, "File", "file_menu", "File menu: New, Open, Save, Import and Export.")

# B -- project and simulation settings -------------------------------------------------------------------------------
d.drive(win._on_project_settings, "project_settings",
        "File > Project Settings: CHID (the name of every output file) and the case title.",
        d.fields(chid="example_1", title="Example 1: room fire with door, window, heat detector"))
d.step("B1 project settings", "ok", {"chid": api.project.chid, "title": api.project.title})


def fill_sim(dlg) -> None:
    dlg.field_widget("time", "t_end").set_value(60.0)
    dlg.apply()


def sim_tabs(dlg) -> None:
    d.tab_shots(dlg, dlg.tabs, [dlg.tabs.tabText(i).replace("&", "") for i in range(1, dlg.tabs.count())],
                "simulation_parameters", "Model > Simulation Parameters")


d.drive(win._on_simulation_parameters, "simulation_parameters",
        "Model > Simulation Parameters, Time tab: the simulation ends at T_END = 60 s.", fill_sim, accept=False,
        extra_shots=sim_tabs)
d.step("B2 simulation parameters", "ok" if api.project.params.t_end == 60.0 else "failed",
       {"t_end": api.project.params.t_end, "radiation_angles": api.project.radi.number_radiation_angles})

# C -- mesh ------------------------------------------------------------------------------------------------------------
d.drive(lambda: win._on_add_entity("add_mesh"), "add_mesh",
        "Model > Add Mesh: a 6 x 4.5 x 3 m domain in 60 x 45 x 30 cells (0.1 m cells, 81,000 in all). 0.1 m is the "
        "coarsest cell that resolves this 180 kW fire (validation: D*/dx at least 4).",
        d.fields(ijk="60,45,30", xb="0,6,0,4.5,0,3", name="DOMAIN"))
view(zoom=2.0)
d.shot(win, "mesh_in_view", "The mesh appears in the 3D view and under Meshes in the Project Explorer.")
d.step("C1 mesh", "ok" if len(api.project.meshes) == 1 else "failed", [m.name for m in api.project.meshes])

# D -- walls from the library, room with door and window ------------------------------------------------------------------
def library_pick(category: str, entry: str):
    def fill(dlg) -> None:
        from PySide6.QtCore import Qt
        dlg.category.setCurrentIndex(dlg.category.findData(category))
        items = dlg.names.findItems(entry, Qt.MatchExactly)
        dlg.names.setCurrentItem(items[0])
        dlg.add_button.click()
        d.pump(0.3)
    return fill


d.drive(d.menu_action(win, "Model", "Library...").trigger, "library_wall",
        "Model > Library: the 25 mm gypsum wall construction (two 12.5 mm boards) is added to the project.",
        library_pick("surfaces", "gypsum_wall_25mm"), accept=False)


def fill_room(dlg) -> None:
    dlg.surface.setCurrentText("GYPSUM_WALL_25MM")
    dlg._add_row("S", 3.0, 0.9, 2.1, 0.0)
    dlg._add_row("E", 2.25, 1.2, 1.05, 0.9)


d.drive(d.menu_action(win, "Draw", "Draw Room (walls, door, window)...").trigger, "draw_room",
        "Draw > Draw Room: walls, ceiling and two openings - a 0.9 x 2.1 m door in the south wall and a "
        "1.2 x 1.05 m window (sill 0.9 m) in the east wall.", fill_room)
view(zoom=2.0)
d.shot(win, "room_in_view", "The room (4.8 x 3.3 x 2.4 m inside the mesh) with its door and window.")
d.step("D1 room", "ok", {"obstructions": len(api.project.obstructions), "holes": len(api.project.holes)})

# E -- fire --------------------------------------------------------------------------------------------------------------
d.drive(d.menu_action(win, "Model", "Add Typed Surface (burner, supply, exhaust...)...").trigger, "burner_surface",
        "Model > Add Typed Surface, burner: 500 kW/m2, reached along a t-squared curve in 15 s (TAU_Q = -15).",
        d.fields(kind="burner", name="BURNER_SURF", heat_release_rate=500, tau_q=-15, color="ORANGE"))
d.drive(lambda: win._on_add_entity("add_obstruction"), "burner_block",
        "Model > Add Obstruction: the burner body, a 0.6 x 0.6 x 0.15 m inert block in the middle of the room.",
        d.fields(xb="2.7,3.3,2.1,2.7,0,0.15", surf_id="INERT", name="BURNER"))
d.drive(lambda: win._on_add_entity("add_vent"), "burner_vent",
        "Model > Add Vent: the burning surface is a vent on the top face of the block only (0.36 m2 x 500 kW/m2 = "
        "180 kW). Giving the whole block the burner surface would also burn its four sides and double the fire.",
        d.fields(xb="2.7,3.3,2.1,2.7,0.15,0.15", surf_id="BURNER_SURF", name="BURNER_TOP"))
d.drive(lambda: win._on_add_entity("add_simple_reaction"), "reaction",
        "Model > Add Reaction: propane, heat of combustion 46,000 kJ/kg.",
        d.fields(fuel="PROPANE", heat_of_combustion=46000, name="PROPANE_FIRE"))


def fill_yields(dlg) -> None:
    dlg.field_widget("soot_yield").set_value(0.024)
    dlg.field_widget("co_yield").set_value(0.005)
    dlg.apply()
    tabs, field = getattr(dlg, "tabs", None), dlg.field_widget("soot_yield").widget
    for i in range(tabs.count() if tabs is not None else 0):      # show the tab that holds the yields
        if tabs.widget(i).isAncestorOf(field):
            tabs.setCurrentIndex(i)
            break


d.drive(lambda: win._on_edit_collection("reactions", "Edit Reactions", "PROPANE_FIRE"), "reaction_yields",
        "Model > Edit Reactions: soot yield 0.024 kg/kg and CO yield 0.005 kg/kg for propane (well-ventilated "
        "values, SFPE Handbook, Tewarson). With the default yield of 0 the fire would make no smoke.", fill_yields)
reac = api.project.reactions[0]
d.step("E1 fire and reaction", "ok" if (reac.soot_yield, reac.co_yield) == (0.024, 0.005) else "failed",
       {"hrrpua": api.project.surfaces[-1].heat_release_rate if api.project.surfaces else None,
        "soot_yield": reac.soot_yield, "co_yield": reac.co_yield})

# F -- open boundaries, then close the floor ---------------------------------------------------------------------------
d.menu_action(win, "Model", "Open Mesh Boundaries").trigger()
d.pump(0.6)
vents = [v.name for v in api.project.vents]
d.step("F1 open mesh boundaries", "ok", vents)
floor = next((v for v in api.project.vents if v.z_min == v.z_max == 0.0 and v.surface_id == "OPEN"), None)
if floor is not None:
    win.explorer.select_entity("vents", floor)
    d.pump(0.4)
    d.shot(win, "floor_vent_selected", "Open Mesh Boundaries opens all six faces of the mesh. The floor of a room "
                                       "standing on the ground must stay closed: select DOMAIN_ZMIN_OPEN in the "
                                       "Project Explorer and press Delete.")
    real_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)     # the user answers Yes to "Remove ...?"
    win._on_delete_selected()
    QMessageBox.question = real_question
    d.pump(0.4)
d.step("F2 floor closed", "ok" if not any(v.z_min == v.z_max == 0.0 for v in api.project.vents) else "failed",
       [v.name for v in api.project.vents])

# G -- instruments and outputs -------------------------------------------------------------------------------------------
d.drive(d.menu_action(win, "Model", "Library...").trigger, "library_heat_detector",
        "Model > Library: a heat detector property (RTI 5, activation 74 C).",
        library_pick("heat_detectors", "heat_detector_74C"), accept=False)
d.drive(lambda: win._on_add_entity("add_device"), "heat_detector",
        "Model > Add Device: the heat detector 5 cm below the ceiling above the burner.",
        d.fields(quantity="LINK TEMPERATURE", xyz="3.0,2.4,2.35", name="HEAT_DET", prop_id="HEAT_DETECTOR_74C"))
for i, z in enumerate((0.6, 1.2, 1.8, 2.3)):
    d.drive(lambda: win._on_add_entity("add_thermocouple"), "thermocouple" if i == 0 else None,
            "Model > Add Thermocouple: a vertical tree of four thermocouples at 0.6, 1.2, 1.8 and 2.3 m above the burner "
            "centre (the same dialog is used four times).",
            d.fields(xyz=f"3.0,2.4,{z}", devc_id=f"TC_{round(z * 100):03d}"))
for plane, pos, qty, name, cap in (("Y", 2.4, "TEMPERATURE", "SLICE_T_Y", "a temperature slice through the burner (Y = 2.4 m)"),
                                   ("X", 3.0, "TEMPERATURE", "SLICE_T_X", "a second temperature slice across the room (X = 3.0 m)"),
                                   ("Z", 1.5, "VISIBILITY", "SLICE_VIS_Z", "a visibility slice at head height (Z = 1.5 m)")):
    d.drive(lambda: win._on_add_entity("add_slice"), f"slice_{name.lower()}", f"Model > Add Slice: {cap}.",
            d.fields(quantity=qty, plane=plane, position=pos, name=name))
d.step("G1 instruments and outputs", "ok", {"devices": [x.name for x in api.project.devices],
                                            "slices": [s.name for s in api.project.slices]})

# H -- whole model ---------------------------------------------------------------------------------------------------------
win._on_toggle_visibility(VisibilityFlags.VENTS, False)
view(zoom=2.0)
d.shot(win, "model_isometric", "The complete model (open-boundary vents hidden): room, door, window, burner, "
                               "detector and thermocouple tree, and the three slice planes.")
view(CameraPreset.FRONT, zoom=2.0)
d.shot(win, "model_front", "Front view (View > Front): the door in the south wall and the burner behind it.")
view(zoom=2.0)
for attr, title in (("surfaces", "Edit Surfaces"), ("devices", "Edit Devices")):
    first = getattr(api.project, attr)[0].name
    d.drive(lambda a=attr, t=title, f=first: win._on_edit_collection(a, t, f), f"editor_{attr}",
            f"Model > {title}: every object of the kind in one list, its settings on the right and the FDS text "
            f"it will write at the bottom.", accept=False)

# I -- validation ------------------------------------------------------------------------------------------------------------
win._on_validate()
d.pump(1.0)
rep = api.validation.validate()
d.shot(win, "validation", "Model > Validate: the findings appear in the Validation tab at the bottom. Double-click a "
                          "finding to select the object it is about.")
d.step("I1 validation", "ok" if not rep.errors else "failed",
       {"errors": [r.message for r in rep.errors], "warnings": [r.message for r in rep.warnings],
        "notes": [r.message for r in rep.infos]})

# J -- save ------------------------------------------------------------------------------------------------------------------
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(PROJECT), "PyFDS Files (*.pyfds)"))
win._on_save_as()
d.pump(0.6)
from pyfds.io.fds_writer import FdsWriter                                         # noqa: E402
FdsWriter().write(api.project, str(HERE / "example_1.fds"))                       # the same as File > Export > FDS
d.step("J1 save", "ok" if PROJECT.exists() else "failed", str(PROJECT))

# K -- run -------------------------------------------------------------------------------------------------------------------
shutil.rmtree(RUN, ignore_errors=True)
RUN.mkdir(parents=True)


def fill_run(dlg) -> None:
    dlg.folder.setText(str(RUN))
    dlg.smokeview_box.setChecked(False)
    d.pump(0.3)


started = time.monotonic()
d.drive(win._on_run_simulation, "run_dialog",
        "Run > Run Simulation: where to run (this computer, one process - the model has one mesh), the folder for "
        "the input and results, the FDS version, and the 'Before you run' summary of the model and its checks.",
        fill_run)
d.step("K1 run started", "ok" if win._run_handle is not None else "failed", str(RUN))
if win._run_handle is None:                                  # refused (model errors): say so instead of waiting
    d.step("K2 run finished", "failed", "the run did not start")
    rec.close()
    import os                                                                       # noqa: E402
    os._exit(1)
rec.timelapse(10.0)                                          # the long FDS run: one video frame every 10 s
monitor = win.run_panel
marks = [0.25, 0.6, 0.9]
while time.monotonic() - started < 4 * 3600:
    d.pump(1.0)
    frac = monitor.bar.value() / 1000.0
    if marks and frac >= marks[0] and monitor.state == "running":
        d.shot(win, f"run_monitor_{int(marks[0] * 100)}", f"Run Monitor at {int(marks[0] * 100)} %: progress, heat release "
                                                          "rate curve and the last lines of the FDS log.")
        marks.pop(0)
    if monitor.state in ("done", "failed"):
        break
rec.realtime()
d.pump(3.0)
out_text = (RUN / "example_1.out").read_text(errors="replace") if (RUN / "example_1.out").exists() else ""
wall = next((ln.split(":")[-1].strip() for ln in out_text.splitlines() if "Total Elapsed Wall Clock Time" in ln), "?")
d.shot(win, "run_finished", "Run finished: 'STOP: FDS completed successfully' in the log, Open Results Viewer enabled.")
d.step("K2 run finished", "ok" if "STOP: FDS completed successfully" in out_text else "failed",
       {"state": monitor.state, "wall_clock_s": wall, "minutes_waited": round((time.monotonic() - started) / 60, 1)})
d.log_path.with_name("run_seconds.txt").write_text(wall)
d.pump(2.0)
d.step("L1 screen recording", "ok", rec.close())
print("editor part done")
win._run_poll.stop() if getattr(win, "_run_poll", None) else None
import os                                                                           # noqa: E402
os._exit(0)                                     # no close handlers: the user's saved layout is left as it was
