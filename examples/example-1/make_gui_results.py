"""Post-process the run that the desktop application made (gui_run/): chart, probes and real Smokeview
screenshots, saved in gui_results/ for the user manual.  Run after gui_walkthrough.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

import matplotlib                                                       # noqa: E402
matplotlib.use("Agg")
from matplotlib.figure import Figure                                    # noqa: E402

from pyfds.api import FdsApi                                            # noqa: E402
from pyfds.io.serializer import Serializer                              # noqa: E402
from pyfds.results.reader import DeviceReader                           # noqa: E402

RUN, OUT = HERE / "gui_run", HERE / "gui_results"
OUT.mkdir(exist_ok=True)
FDS_HOME = HERE.parents[1] / "fds_smv"

api = FdsApi(Serializer().load(str(HERE / "example_1.pyfds")))
devc = DeviceReader.read(str(RUN / "example_1_devc.csv"))
hrr = DeviceReader.read(str(RUN / "example_1_hrr.csv"))

fig = Figure(figsize=(9, 6))
ax = fig.subplots(2, 1, sharex=True)
ax[0].plot(hrr["Time"].data, hrr["HRR"].data, color="tab:red")
ax[0].set_ylabel("HRR (kW)")
ax[0].grid(alpha=.3)
for name, r in devc.items():
    if name.startswith("TC_"):
        ax[1].plot(r.times, r.data, label=name)
ax[1].set_ylabel("gas temperature (C)")
ax[1].set_xlabel("time (s)")
ax[1].legend(ncol=4, fontsize=8)
ax[1].grid(alpha=.3)
fig.tight_layout()
fig.savefig(OUT / "hrr_and_thermocouples.png", dpi=110)

api.scene.open_results(str(RUN))
layers = api.scene.add_slices()
api.scene.playback.seek_time(20.0)
probes = {}
for label, pt in {"above burner 1.2 m": (3.0, 2.4, 1.2), "under ceiling": (3.0, 2.4, 2.3), "doorway": (3.0, 0.75, 1.0)}.items():
    probes[label] = [round(h["value"], 1) for h in api.scene.probe(pt)][:1]
det = devc["HEAT_DET"]
summary = {
    "peak_hrr_kw": round(float(hrr["HRR"].data.max()), 0),
    "detector_trip_s": round(float(det.times[(det.data >= 74).argmax()]), 1),
    "thermocouples_20s": {k: round(float(devc[k].data[-1]), 0) for k in ("TC_060", "TC_120", "TC_180", "TC_230")},
    "probes_20s": probes,
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
print(summary)

api.config.set("smv_binary", str(FDS_HOME / "SMV6" / "smokeview.exe"))
shots = api.smokeview.render_screenshots(str(RUN / "example_1.smv"), [5.0, 10.0, 20.0], "TEMPERATURE", str(OUT / "smokeview"))
print(shots)
