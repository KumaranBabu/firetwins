"""Post-process the couch run (gui_run/): HRR chart, heat-flux and temperature summary, and the .pyfdsv view file.

    python examples/example-2/make_results.py          # after make_example2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

import matplotlib                                                       # noqa: E402
matplotlib.use("Agg")
from matplotlib.figure import Figure                                    # noqa: E402

from pyfds.results.reader import DeviceReader                           # noqa: E402

RUN, OUT = HERE / "gui_run", HERE / "gui_results"
OUT.mkdir(exist_ok=True)

hrr = DeviceReader.read(str(RUN / "couch_hrr.csv"))
t, q = hrr["Time"].data, hrr["HRR"].data
fig = Figure(figsize=(8, 4.5))
ax = fig.subplots()
ax.plot(t, q, color="tab:red", marker="o")
ax.set_xlabel("time (s)")
ax.set_ylabel("HRR (kW)")
ax.set_title("Burning couch: heat release rate")
ax.grid(alpha=.3)
fig.tight_layout()
fig.savefig(OUT / "hrr.png", dpi=110)

summary = {"end_time_s": float(t[-1]), "hrr_kw_at_end": round(float(q[-1]), 0), "peak_hrr_kw": round(float(q.max()), 0),
           "hrr_by_time": {f"{x:.0f}s": round(float(y), 0) for x, y in zip(t, q)}}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
print(summary)
