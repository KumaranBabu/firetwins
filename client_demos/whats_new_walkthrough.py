"""Screenshots of the menus and panels added or changed by the 2026-10-29 review, in the real windows on the screen.

    python client_demos/whats_new_walkthrough.py editor     # model editor: menus, explorer filter, calculators, Run dialog
    python client_demos/whats_new_walkthrough.py results    # PyFDS Results with example_3: Tenability, Compare Runs

Pictures and their captions go to documentation/screenshots/whats_new/ (validation_log.json), like the example
walkthroughs; the manual builder reads them from there. 'editor' starts the folder afresh; 'results' writes
validation_log_results.json and numbers its pictures from 51.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from demo_kit import ROOT, Demo                                                    # noqa: E402

from PySide6.QtCore import QPoint, Qt                                                # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox                 # noqa: E402

from pyfds.api import FdsApi                                                         # noqa: E402

PART = sys.argv[1] if len(sys.argv) > 1 else "editor"
EX1, EX3 = HERE / "example_1", HERE / "example_3"


def demo() -> Demo:
    if PART == "editor":
        return Demo("whats_new")
    d = Demo.__new__(Demo)                       # its own log; pictures numbered from 51, after the editor part's
    d.name = "whats_new"
    d.shots_dir = ROOT / "documentation" / "screenshots" / "whats_new"
    d.shots_dir.mkdir(parents=True, exist_ok=True)
    d.log_path = d.shots_dir / "validation_log_results.json"
    d.log, d.n = [], 50
    for old in d.shots_dir.glob("*.png"):
        if int(old.name[:2]) > d.n:
            old.unlink()
    d.app = QApplication.instance() or QApplication([])
    from pyfds.gui.theme import apply_theme, saved_theme
    apply_theme(saved_theme(), d.app, remember=False)
    sys.excepthook = d._die
    from PySide6.QtCore import QTimer
    d._watch = QTimer()
    d._watch.timeout.connect(d._message_boxes)
    d._watch.start(1200)
    return d


d = demo()


def top_menu(win, title: str):
    return next(a.menu() for a in win.menuBar().actions() if a.text().replace("&", "") == title)


def submenu_shot(win, top: str, sub: str, name: str, caption: str) -> None:
    """The submenu opened beside its entry in the top menu, photographed with the top menu."""
    m = top_menu(win, top)
    act = next(a for a in m.actions() if a.menu() is not None and a.text().replace("&", "") == sub)
    m.popup(win.mapToGlobal(win.menuBar().actionGeometry(
        next(a for a in win.menuBar().actions() if a.menu() is m)).bottomLeft()))
    d.pump(0.4)
    m.setActiveAction(act)
    act.menu().popup(m.mapToGlobal(QPoint(m.actionGeometry(act).right(), m.actionGeometry(act).top())))
    d.pump(0.5)
    left = min(m.geometry().left(), act.menu().geometry().left())
    top_y = min(m.geometry().top(), act.menu().geometry().top())
    right = max(m.geometry().right(), act.menu().geometry().right())
    bottom = max(m.geometry().bottom(), act.menu().geometry().bottom())
    d.n += 1
    file = f"{d.n:02d}_{name}.png"
    QApplication.primaryScreen().grabWindow(0, left, top_y, right - left + 1, bottom - top_y + 1).save(str(d.shots_dir / file))
    d.log.append({"screenshot": file, "caption": caption, "size": [right - left + 1, bottom - top_y + 1]})
    d.log_path.write_text(json.dumps(d.log, indent=1, default=str), encoding="utf-8")
    print("   screenshot", file)
    act.menu().hide()
    m.hide()
    d.pump(0.3)


def editor() -> None:
    from pyfds.core.viewport import CameraPreset
    from pyfds.gui.main_window import MainWindow
    api = FdsApi()
    win = MainWindow(api)
    win.restore_keymap = lambda: None
    win.showMaximized()
    d.pump(2.0)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(EX1 / "example_1.pyfds"), "PyFDS (*.pyfds)"))
    win._on_open()
    d.pump(1.5)
    win._on_camera_preset(CameraPreset.ISOMETRIC)
    d.pump(1.0)
    d.shot(win, "editor_with_model", "The model editor with client_demos\\example_1\\example_1.pyfds open (File > Open). "
                                     "The menu bar: File, Edit, Model, Devices, Output, Analysis (running FDS), Results, View, "
                                     "Tools, Help.")
    d.step("W1 editor with example_1", "ok", {"obstructions": len(api.project.obstructions),
                                              "devices": len(api.project.devices)})

    # explorer filter
    win.explorer_filter.setText("TC_")
    d.pump(0.8)
    box = win.explorer_filter.parentWidget()
    d.shot(box, "explorer_filter", "Project Explorer filter: typing TC_ leaves only the four thermocouples (and the "
                                   "groups that hold them). It also takes tag: and type: (for example type:vent).")
    d.step("W2 explorer filter", "ok", "TC_")
    win.explorer_filter.setText("type:vent")
    d.pump(0.8)
    d.shot(box, "explorer_filter_type", "The same filter with type:vent - every vent of the model, nothing else.")
    win.explorer_filter.clear()
    d.pump(0.5)

    # menus, top level and the new submenus
    captions = {
        "File": "File menu.",
        "Edit": "Edit menu: Undo/Redo, clipboard, and the new Visibility and Transform submenus.",
        "View": "View menu: standard views, display options and the Rendering Mode submenu.",
        "Model": "Model menu: the editors, the Add... commands, Add from Library, Model Checks, and (right column) "
                 "Add Special, Open Mesh Boundaries and the Draw, HVAC, Scenarios and Floors submenus.",
        "Devices": "Devices menu.",
        "Output": "Output menu.",
        "Analysis": "Analysis menu (running FDS): Run Simulation, parallel/cluster/cloud runs, Open Smokeview After "
                    "Run, Stop and Cancel, Monitor Simulation.",
        "Results": "Results menu of the editor: Open PyFDS Results, View Results of Last Run, Open Smokeview... (any .smv "
                   "in Smokeview) and Open Results Folder.",
        "Tools": "Tools menu, with the new Fire Engineering Calculators.",
        "Help": "Help menu: the FDS User Guide and the Smokeview Verification Guide open in the PDF viewer.",
    }
    names = [a.text().replace("&", "") for a in win.menuBar().actions() if a.menu() is not None]
    for title in names:
        if title in captions:
            d.menu_shot(win, title, f"menu_{title.lower()}", captions[title])
    d.step("W3 top menus", "ok", names)
    for top, sub, cap in (("Edit", "Visibility", "Edit > Visibility: hide and show objects."),
                          ("Edit", "Transform", "Edit > Transform: move, rotate, scale and mirror the selection."),
                          ("Model", "Add from Library", "Model > Add from Library: surfaces, fuels and materials from "
                                                        "the library."),
                          ("Model", "Add Special", "Model > Add Special: typed surfaces (burner, supply, exhaust), "
                                                   "complex stoichiometry reactions, liquid fuels."),
                          ("Model", "Model Checks", "Model > Model Checks: every 'check my model' command in one place "
                                                    "(some used to be under Tools)."),
                          ("View", "Rendering Mode", "View > Rendering Mode: wireframe, shaded, outlines, realistic.")):
        try:
            submenu_shot(win, top, sub, f"submenu_{sub.lower().replace(' ', '_')}", cap)
        except StopIteration:
            d.step(f"W4 submenu {top} > {sub}", "failed", "not found")

    # Fire Engineering Calculators, with example 1's fire
    dlg = win._on_fire_engineering()
    d.pump(0.8)

    def calc(title: str, values: dict, name: str, caption: str) -> None:
        dlg.choice.setCurrentText(title)
        d.pump(0.2)
        for k, val in values.items():
            dlg._inputs[k].setValue(val)
        rows = dlg.calculate()
        d.shot(dlg, name, caption)
        d.step(f"W5 calculator {title}", "ok" if rows else "failed", dict(rows))

    calc("Fire size and cell size", {"hrr_kw": 180.0}, "fire_eng_cell_size",
         "Tools > Fire Engineering Calculators, 'Fire size and cell size' for example 1's 180 kW burner: the "
         "characteristic diameter D* = 0.48 m and the cell sizes for D*/dx from 10 to 20.")
    calc("Heat detector response", {"hrr_kw": 180.0, "ceiling_height_m": 2.25, "detector_radial_distance_m": 0.0},
         "fire_eng_detector", "'Heat detector response' for the same fire, the ceiling 2.25 m above the burner top and the "
                              "detector on the fire axis. The calculator uses a standard sprinkler-type link (RTI 50, "
                              "68 C), not example 1's fast detector.")
    calc("Smoke filling time (NFPA 92)", {"hrr_kw": 180.0, "floor_area_m2": 15.84, "room_height_m": 2.4,
                                           "z_interface_m": 1.5},
         "fire_eng_filling", "'Smoke filling time (NFPA 92)' for example 1's room (4.8 x 3.3 m, 2.4 m high): the time "
                             "for the smoke layer to come down to 1.5 m with no openings, steady 180 kW from the start.")
    dlg.close()

    # Run dialog (not started): the Smokeview option
    def fill_run(rd) -> None:
        rd.folder.setText(str(EX1 / "run"))
        rd.smokeview_box.setChecked(True)
        d.pump(0.3)
    d.drive(win._on_run_simulation, "run_dialog_smokeview",
            "Analysis > Run Simulation with 'Open Smokeview when the run finishes' ticked: when FDS ends, Smokeview opens "
            "<CHID>.smv from the run folder (the dialog was closed here without running).", fill_run, accept=False)
    d.step("W6 run dialog", "ok")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)


def results() -> None:
    from pyfds.gui.results.window import ResultsWindow
    run3 = EX3 / "run"
    smv = run3 / "example_3.smv"
    win = ResultsWindow(FdsApi())
    win.showMaximized()
    d.pump(1.5)
    for title, cap in (("File", "PyFDS Results, File menu: Open Results (.smv), Load CSV File, Save "
                                "Screenshot, and the Movie submenu."),
                       ("View", "PyFDS Results, View menu, with the Section Box and Units submenus."),):
        d.menu_shot(win, title, f"results_menu_{title.lower()}", cap)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(smv), "Smokeview (*.smv)"))
    win.open_results()
    d.pump(2.0)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(run3 / "example_3_devc.csv"), "CSV (*.csv)"))
    win.load_csv()
    d.pump(0.8)
    d.menu_shot(win, "Analysis", "results_menu_analysis", "PyFDS Results, Analysis menu, with the new Tenability (FED) "
                                                          "and Compare Runs (Time History Plot is in Tools).")
    win.time_plot()
    d.pump(1.0)
    plot = win._plot
    for i in range(plot.list.count()):
        if plot.list.item(i).text().split("/")[-1].strip() in {"CO_15", "O2_15", "CO2_15"}:
            plot.list.item(i).setCheckState(Qt.Checked)
    d.pump(1.0)
    d.shot(plot, "time_plot_gases", "Example 3, Tools > Time History Plot: carbon monoxide, carbon dioxide and oxygen "
                                    "(volume fractions) at head height in the room.")
    plot.close()

    dlg = win.open_tenability()
    d.pump(0.6)
    picked_temp = dlg.combos["temp"].currentData()           # the dialog's own pick, recorded, not changed
    dlg.resize(640, 600)
    dlg.rset.setValue(60.0)
    rows = dlg.calculate()
    d.shot(dlg, "tenability", "Analysis > Tenability (FED) for example 3: the gas columns are picked from the loaded "
                              "_devc.csv, the gas temperature from the same place as the gases (GAS_T_15 for CO_15); the "
                              "dose uses FDS's own constants. RSET 60 s here.")
    fds_fed = None
    series = win.viewer.csv_series()
    fed_key = next((k for k in series if k.endswith("FED_15")), None)
    if fed_key:
        fds_fed = float(series[fed_key].values[-1])
    d.step("R1 tenability", "ok" if rows else "failed", {"rows": dict(rows), "fds_FED_15_at_end": fds_fed,
                                                       "temperature_column": picked_temp})
    dlg.close()

    cmp = win.open_compare_runs()
    d.pump(0.5)
    cmp.baseline.setText(str(EX1 / "run"))
    cmp.variant.setText(str(run3))
    report = cmp.compare()
    d.pump(0.5)
    d.shot(cmp, "compare_runs", "Analysis > Compare Runs: example 1 (door open, baseline) against example 3 (door "
                                "closed), device by device; differences above 5 % are flagged, and devices that only one "
                                "run has are listed as such.")
    d.step("R2 compare runs", "ok" if report else "failed",
           {c.name: [c.status, round(c.peak_pct_diff, 1) if c.peak_pct_diff == c.peak_pct_diff else None]
            for c in (report.channels if report else [])})
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)


editor() if PART == "editor" else results()
d.pump(0.5)
print(PART, "part done")
import os                                                                            # noqa: E402
os._exit(0)                                     # no close handlers: the user's saved layout is left as it was
