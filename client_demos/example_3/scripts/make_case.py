"""Example 3: Example 1 with the door closed and gas devices at head height, for the Tenability (FED) and Compare Runs
panels of PyFDS Results. Built from example_1.pyfds through the PyFDS API (the same calls the editor makes):

    python client_demos/example_3/scripts/make_case.py

Writes client_demos/example_3/example_3.pyfds and example_3.fds; run it with Run > Run Simulation (or fds example_3.fds
in client_demos/example_3/run).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pyfds.api import FdsApi                                                    # noqa: E402

api = FdsApi()
api.load(str(ROOT / "client_demos" / "example_1" / "example_1.pyfds"))
p = api.project
p.chid = "example_3"
p.title = "Example 3: example 1 with the door closed, gas devices at head height"
door = next(h for h in p.holes if h.name == "ROOM_OPENING")                      # the south-wall door (0.9 x 2.1 m)
p.holes.remove(door)

XYZ = [1.5, 3.0, 1.5]                                    # back-left part of the room, head height, out of the plume
for name, quantity, spec in (("CO_15", "VOLUME FRACTION", "CARBON MONOXIDE"),
                             ("CO2_15", "VOLUME FRACTION", "CARBON DIOXIDE"),
                             ("O2_15", "VOLUME FRACTION", "OXYGEN"),
                             ("GAS_T_15", "TEMPERATURE", None),
                             ("VIS_15", "VISIBILITY", None),
                             ("FED_15", "FED", None)):            # FDS's own FED, to check the PyFDS dose against
    kw = {"name": name}
    if spec:
        kw["spec_id"] = spec
    api.devices.add_device(quantity, XYZ, **kw)

api.save(str(HERE / "example_3.pyfds"))
(HERE / "run").mkdir(exist_ok=True)
api.save(str(HERE / "run" / "example_3.fds"))
api.save(str(HERE / "example_3.fds"))
print((HERE / "example_3.fds").read_text())
