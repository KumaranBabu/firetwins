# Example 2 - a burning couch (from the FDS distribution)

The case is `Examples/Fires/couch.fds` from the FDS install (`fds_smv/FDS6/Examples/Fires/`), taken in unchanged and run
for 25 s of its 600 s (about 27 minutes on 4 logical cores).

| Step | How | Result |
|---|---|---|
| Import | `api.session.open_project("couch.fds")` or File > Import FDS | 1 `&MESH` + `&MULT` = 4 meshes, 5 obstructions, 3 surfaces (upholstery burns away), 3 materials, an ignitor particle |
| Check | `api.validate()` / Model > Validate | no findings |
| Save | `couch.pyfds` (PyFDS project) and `couch.fds` (written back) | |
| Run | `api.solvers.run_local(..., num_processes=4)`, one MPI process per mesh | `gui_run/` (not kept in git, 190 MB) |
| Results | `make_results.py`, `gui_viewer_shots.py` | `gui_results/hrr.png`, `summary.json`, `gui_viewer/*.png` |

Heat release rate: 63 kW at 5 s, 354 kW at 10 s, 518 kW at 15 s, 537 kW at 25 s (the couch has not burnt through yet).

Run everything again: `python examples/example-2/make_example2.py`, then `make_results.py` and the two `*_shots.py` scripts.

What importing this case taught PyFDS (all fixed and covered by tests):

* a mesh with `MULT_ID` is now several meshes for validation, the 3D view and the MPI process count
* an `&OBST` with no `SURF_ID` takes the `DEFAULT=.TRUE.` surface, and with no `COLOR` shows its surface's colour
* a `&PART` with a `SURF_ID` is written without `DIAMETER` (FDS stops with ERROR 213 otherwise)
* the results viewer reads `CELL_CENTERED` slices (one value per index, the first a ghost)
