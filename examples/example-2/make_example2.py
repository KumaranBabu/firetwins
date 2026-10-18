"""Example 2 - a burning couch, taken from the FDS distribution's own examples (Examples/Fires/couch.fds).

    python examples/example-2/make_example2.py          # import, check, save, run (25 s of fire), keep the results

What it shows, end to end:  import an existing FDS input -> the model PyFDS makes of it (4 meshes from one &MULT, a
burn-away surface, an ignitor particle) -> validation -> save as .pyfds and .fds -> a real parallel FDS run (one MPI process
per mesh) -> results in gui_run/ for the results viewer.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from pyfds.api import FdsApi                                         # noqa: E402

SOURCE = HERE.parents[1] / "fds_smv" / "FDS6" / "Examples" / "Fires" / "couch.fds"
T_END = 25.0                                                          # the original runs 600 s; 25 s covers ignition and growth


def main() -> None:
    api = FdsApi()
    project = api.session.open_project(str(SOURCE))
    print(f"imported {SOURCE.name}: {len(project.meshes)} MESH line, {api.meshes.run_count()} meshes after the multiplier, "
          f"{len(project.obstructions)} obstructions, {len(project.surfaces)} surfaces, {len(project.materials)} materials")
    api.config.configure_simulation(t_end=T_END)
    project.title = "Burning couch (FDS example Fires/couch), first 25 s"
    problems = api.validate()
    print("validation:", problems or "no findings")
    api.session.save_project(str(HERE / "couch.pyfds"))
    api.session.save_project(str(HERE / "couch.fds"))
    t0 = time.time()
    run = api.solvers.run_local(str(HERE / "gui_run"), num_processes=api.meshes.run_count())
    while run.state == "running":
        time.sleep(10)
    print(f"run {run.state} after {time.time() - t0:.0f} s {run.message}")


if __name__ == "__main__":
    main()
