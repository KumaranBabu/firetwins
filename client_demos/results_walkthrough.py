"""Post-processing of a finished demo run, in the real windows: PyFDS Results (the Smokeview-style viewer that comes with
PyFDS) and Smokeview itself (fds_smv/SMV6/smokeview.exe, driven by a Smokeview script).

    python client_demos/results_walkthrough.py example_1
    python client_demos/results_walkthrough.py example_2

Screenshots continue the numbering in documentation/screenshots/<example>/ and the outcomes are appended to its
validation_log.json. Rendered stills and the movie go to client_demos/<example>/results/.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from demo_kit import ROOT, Demo, ScreenRecorder, shown_window, window_shot                       # noqa: E402

from PySide6.QtCore import Qt                                                        # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox                               # noqa: E402

from pyfds.api import FdsApi                                                         # noqa: E402
from pyfds.gui.results.window import ResultsWindow                                   # noqa: E402

CASE = sys.argv[1] if len(sys.argv) > 1 else "example_1"
CHID = {"example_1": "example_1", "example_2": "couch"}[CASE]
RUN = HERE / CASE / "run"
SMV = RUN / f"{CHID}.smv"
OUT = HERE / CASE / "results"
OUT.mkdir(exist_ok=True)

# What to show, per case: (caption, [(kind, quantity, label contains)], time in s)
SCENES = {
    "example_1": [
        ("Temperature slice through the burner (Y = 2.4 m) at {t:g} s: the plume rises to the ceiling and the hot "
         "layer spreads under it.", [("slice2d", "TEMPERATURE", "SLICE_T_Y")], 30.0),
        ("The same slice at the end of the run ({t:g} s).", [("slice2d", "TEMPERATURE", "SLICE_T_Y")], 60.0),
        ("Two temperature slices at {t:g} s: along the room (Y = 2.4 m) and across it (X = 3.0 m).",
         [("slice2d", "TEMPERATURE", "SLICE_T_Y"), ("slice2d", "TEMPERATURE", "SLICE_T_X")], 60.0),
        ("3D smoke (soot density) and the flame (heat release rate per unit volume) at {t:g} s.",
         [("smoke3d", "SOOT DENSITY", ""), ("smoke3d", "HRRPUV", "")], 30.0),
        ("3D smoke at {t:g} s: smoke leaves through the top of the door and the window.",
         [("smoke3d", "SOOT DENSITY", ""), ("smoke3d", "HRRPUV", "")], 60.0),
        ("Visibility at head height (Z = 1.5 m) at {t:g} s (metres; 30 m is the FDS upper limit, clear air).",
         [("slice2d", "SOOT VISIBILITY", "")], 60.0),
        ("Devices at {t:g} s: the heat detector and the thermocouple tree above the burner, coloured by their "
         "current value.", [("devices", "", ""), ("slice2d", "TEMPERATURE", "SLICE_T_Y")], 60.0),
    ],
    "example_2": [
        ("Temperature slice through the couch (X = 2.5 m) at {t:g} s.", [("slice2d", "TEMPERATURE", "")], 10.0),
        ("The same slice at the end of the run ({t:g} s): the flame plume over the seat cushion.",
         [("slice2d", "TEMPERATURE", "")], 25.0),
        ("Heat release rate per unit volume (the flame) on the same plane at {t:g} s.", [("slice2d", "HRRPUV", "")], 25.0),
        ("3D smoke (soot density) and flame at {t:g} s.", [("smoke3d", "SOOT DENSITY", ""), ("smoke3d", "HRRPUV", "")], 15.0),
        ("3D smoke and flame at {t:g} s.", [("smoke3d", "SOOT DENSITY", ""), ("smoke3d", "HRRPUV", "")], 25.0),
        ("Boundary file, burning rate on the couch surfaces at {t:g} s (kg/m2/s).", [("boundary", "BURNING RATE", "")], 25.0),
        ("Boundary file, wall temperature at {t:g} s.", [("boundary", "WALL TEMPERATURE", "")], 25.0),
        ("Static ignitor particle and the temperature slice at {t:g} s.",
         [("particles", "", ""), ("slice2d", "TEMPERATURE", "")], 5.0),
    ],
}

d = Demo.__new__(Demo)                       # continue the numbering and the log of the editor walkthrough
d.name = CASE
d.shots_dir = ROOT / "documentation" / "screenshots" / CASE
d.log_path = d.shots_dir / "validation_log.json"
d.log = json.loads(d.log_path.read_text(encoding="utf-8")) if d.log_path.exists() else []
d.n = max([int(e["screenshot"][:2]) for e in d.log if "screenshot" in e] + [0])
from PySide6.QtWidgets import QApplication                                            # noqa: E402
d.app = QApplication.instance() or QApplication([])
from pyfds.gui.theme import apply_theme, saved_theme                                  # noqa: E402
apply_theme(saved_theme(), d.app, remember=False)
sys.excepthook = d._die
from PySide6.QtCore import QTimer                                                     # noqa: E402
d._watch = QTimer()
d._watch.timeout.connect(d._message_boxes)
d._watch.start(1200)

if not SMV.exists():
    d.step(f"R0 results present ({SMV.name})", "failed", "run the editor walkthrough first")
    sys.exit(1)

win = ResultsWindow(FdsApi())
win.showMaximized()
d.pump(1.5)
rec = ScreenRecorder(ROOT / "documentation" / "videos" / f"{CASE}_post_processing.mp4")
d.shot(win, "results_empty", "PyFDS Results (Results > Open PyFDS Results in the editor, or the PyFDS Results shortcut) "
                             "before a run is loaded.")
d.menu_shot(win, "File", "results_file_menu", "PyFDS Results, File menu: Open Results (.smv) opens the .smv file of a run.")
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(SMV), "Smokeview (*.smv)"))
t0 = time.perf_counter()
win.open_results()
d.pump(2.0)
v = win.viewer
d.shot(win, "results_loaded", f"File > Open Results (.smv) with {SMV.name}: the geometry is shown and the Navigation View on "
                              "the left lists every result of the run.")
d.step("R1 open results in PyFDS Results", "ok" if v.run is not None else "failed",
       {"seconds": round(time.perf_counter() - t0, 2), "datasets": len(list(v.tree.leaves())),
        "time_range_s": [round(x, 2) for x in v.time_range()]})


def find(kind: str, quantity: str, label: str):
    return [n.id for n in v.tree.leaves() if n.kind == kind and (not quantity or n.quantity == quantity)
            and (not label or label in n.id)]


def show(nodes, t: float) -> None:
    for leaf in list(v.active_leaves()):
        if not leaf.id.startswith("geometry/"):
            v.deactivate(leaf.id)
    for nid in nodes:
        v.activate(nid)
    win.sync(True)
    pb = v.playback
    if pb is not None and pb.n_frames:
        win.slider.setValue(int(np.argmin(np.abs(np.asarray(pb.times) - t))))
    d.pump(1.5)


for i, (caption, wants, t) in enumerate(SCENES[CASE]):
    nodes = [nid for kind, qty, label in wants for nid in find(kind, qty, label)]
    if not nodes:
        d.step(f"R2.{i + 1} {caption.format(t=t)[:50]}", "failed", f"no dataset for {wants}")
        continue
    try:
        show(nodes, t)
        d.shot(win, f"results_view_{i + 1}", caption.format(t=t))
        d.step(f"R2.{i + 1} show {', '.join(w[1] or w[0] for w in wants)} at {t:g} s", "ok", nodes)
    except Exception as exc:                                                       # noqa: BLE001
        d.step(f"R2.{i + 1} show {wants}", "failed", repr(exc))

# time histories --------------------------------------------------------------------------------------------------------
loaded = []
for csv in (f"{CHID}_hrr.csv", f"{CHID}_devc.csv"):
    if (RUN / csv).exists():
        QFileDialog.getOpenFileName = staticmethod(lambda *a, c=csv, **k: (str(RUN / c), "CSV (*.csv)"))
        win.load_csv()
        loaded.append(csv)
d.pump(0.5)
win.time_plot()
d.pump(1.0)
plot = win._plot
wanted = {"HRR", "HEAT_DET", "TC_060", "TC_120", "TC_180", "TC_230"}
series = [plot.list.item(i).text() for i in range(plot.list.count())]
for i in range(plot.list.count()):
    if plot.list.item(i).text().split("/")[-1].strip() in wanted:
        plot.list.item(i).setCheckState(Qt.Checked)
d.pump(1.0)
d.shot(plot, "time_plot", "Tools > Time History Plot after File > Load CSV File with the heat release (_hrr.csv) and device "
                          "(_devc.csv) files: tick the series to plot.")
d.step("R3 time history plot", "ok" if series else "failed", {"csv": loaded, "series": series[:20]})
plot.close()

# colour bar, screenshot and movie dialogs, real output files ---------------------------------------------------------------
first = SCENES[CASE][1][1]
show([nid for kind, qty, label in first for nid in find(kind, qty, label)], SCENES[CASE][1][2])
d.drive(win.colorbar_prefs, "results_colorbar_dialog", "Preferences > Colorbar: range mode, limits, colour map and "
                                                        "labels of a quantity's colour bar.", accept=False)
from pyfds.api.viz import capture as cap                                                  # noqa: E402
from pyfds.gui.results.dialogs import MovieDialog, ScreenshotDialog                        # noqa: E402
d.drive(lambda: ScreenshotDialog(v, win, (win.view.width(), win.view.height())).exec(), "results_screenshot_dialog",
        "File > Save Screenshot: one picture, a series over time, or one per saved view, at a chosen size.", accept=False)
d.drive(lambda: MovieDialog(v, win, (1280, 720)).exec(), "results_movie_dialog",
        "File > Movie > Save Movie: an MP4 of the time range at a chosen frame rate and speed.", accept=False)
renderer = win.view.make_renderer(v)
stills = []
for t in (SCENES[CASE][0][2], SCENES[CASE][1][2]):
    stills += v.render_screenshots(v.screenshot_plan(str(OUT / f"{CHID}_t{int(t):02d}.png"), "single", t), renderer, (1280, 720))
lo, hi = v.time_range()
movie = v.render_movie(cap.movie_plan(str(OUT / f"{CHID}.mp4"), lo, hi, fps=10, speed=2.0, size=(1280, 720)), renderer)
d.step("R4 export stills and movie", "ok" if stills and movie.get("encoded") else "partial",
       {"stills": [Path(s).name for s in stills], "movie": str(movie.get("path")), "encoded": movie.get("encoded")})

QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(HERE / CASE / f"{CHID}.pyfdsv"), "PyFDS visualization (*.pyfdsv)"))
win.save_as()
d.pump(0.6)
d.step("R5 save visualization", "ok" if (HERE / CASE / f"{CHID}.pyfdsv").exists() else "failed", f"{CHID}.pyfdsv")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
d.pump(0.5)                                                  # PyFDS Results stays open behind Smokeview

# Smokeview ---------------------------------------------------------------------------------------------------------------
smokeview = ROOT / "fds_smv" / "SMV6" / "smokeview.exe"
from pyfds.smokeview.scripting import SsfScriptBuilder                                     # noqa: E402
b = SsfScriptBuilder()
b.set_render_options(width=1280, height=720)
if CASE == "example_1":
    b.load_slice("TEMPERATURE", axis=2, position=2.4).set_time(30.0).screenshot("smv_temperature_slice_t30")
    b.set_time(60.0).screenshot("smv_temperature_slice_t60").unload_all()
    b.load_smoke3d("SOOT DENSITY").load_smoke3d("HRRPUV").set_time(30.0).screenshot("smv_smoke_t30")
    b.set_time(60.0).screenshot("smv_smoke_t60")
else:
    b.load_boundary("BURNING RATE").set_time(15.0).screenshot("smv_burning_rate_t15").set_time(25.0).screenshot("smv_burning_rate_t25").unload_all()
    b.load_smoke3d("SOOT DENSITY").load_smoke3d("HRRPUV").set_time(15.0).screenshot("smv_smoke_t15")
    b.set_time(25.0).screenshot("smv_smoke_t25")
script = RUN / f"{CHID}_demo.ssf"
b.write(str(script))                                         # Smokeview closes by itself when the script ends
for old in RUN.glob("smv_*.png"):                           # a rerun: the same names, so 'new' must mean new files
    old.unlink()
before = set()
proc = subprocess.Popen([str(smokeview), "-script", script.name, SMV.name], cwd=str(RUN), startupinfo=shown_window())
deadline = time.monotonic() + 240
expected = 4
desk = d.shots_dir / f"{d.n + 1:02d}_smokeview_window.png"
grabbed = False
while time.monotonic() < deadline and len({p.name for p in RUN.glob("smv_*.png")} - before) < expected:
    d.pump(1.0)                                       # keeps the screen recorder running while Smokeview works
    if len({p.name for p in RUN.glob("smv_*.png")} - before) >= 2:      # the 3D smoke is loaded: picture the window
        grabbed = window_shot(proc.pid, desk) or grabbed                 # Smokeview's window only, not the desktop
d.pump(2.0)
if grabbed:
    d.n += 1
    d.log.append({"screenshot": desk.name, "caption": "Smokeview 6.10.1 (Results > Open Smokeview... in the editor, or double-click the .smv "
                  "file) while the script renders: the case's geometry with the scripted data loaded; right-click in "
                  "the window for the menus.", "size": "window"})
proc.terminate()
d.pump(1.0)
d.step("R7 screen recording", "ok", rec.close())
made = sorted(p.name for p in RUN.glob("smv_*.png"))
for name in made:                                          # Smokeview's own pictures go to the manual too
    (d.shots_dir / f"{d.n + 1:02d}_{name}").write_bytes((RUN / name).read_bytes())
    d.n += 1
    d.log.append({"screenshot": f"{d.n:02d}_{name}", "caption": f"Rendered by Smokeview from the script: {name}",
                  "size": "1280x720"})
d.step("R6 Smokeview script renders", "ok" if len(made) >= expected else "partial",
       {"images": made, "desktop_capture": grabbed})
d.log_path.write_text(json.dumps(d.log, indent=1, default=str), encoding="utf-8")
print("results part done")
import os                                                                                  # noqa: E402
os._exit(0)
