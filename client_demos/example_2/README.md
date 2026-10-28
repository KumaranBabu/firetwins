# Example 2: Burning couch (FDS validation example, 4 MPI processes)

This example opens an existing FDS input: `Examples/Fires/couch.fds` from the FDS 6.10.1 distribution. You then:
1. inspect the case in the PyFDS editors;
2. shorten it to 25 s and validate it;
3. run it in parallel on 4 MPI processes;
4. examine the flame spread over the couch in PyFDS Results and in Smokeview.

It demonstrates FDS import, multi-mesh (MULT) handling, a parallel run, and pyrolysis results such as burning rate and particles.

The step-by-step instructions are in section 3 of `documentation/FireTwins_User_Manual.docx` (PDF beside it).

## Prerequisites
- FireTwins / PyFDS 0.3.0, with FDS 6.10.1 (including MPI) and Smokeview 6.10.1 (bundled in `fds_smv/`).
- A PC with 4 or more CPU cores.
- About 15 minutes of computing time: 885 s wall clock on 4 processes on the test PC.

## Files
| File | What it is |
|---|---|
| `couch_original.fds` | An unchanged copy of the FDS distribution's `couch.fds` |
| `couch.pyfds` | The project after opening it in PyFDS and setting T_END = 25 s |
| `couch.fds` | The FDS input written by PyFDS (the run input) |
| `couch.pyfdsv` | The saved results visualization |
| `run/` | The FDS run (4 meshes), plus the Smokeview script `couch_demo.ssf` and its renders |
| `results/` | Stills (`couch_t10.png`, `couch_t25.png`) and a movie (`couch.mp4`) exported from PyFDS Results |
| `scripts/walkthrough.py` | Opens, inspects, validates, runs, and takes the manual's screenshots |

The screen recordings are `documentation/videos/example_2_open_and_run.mp4` and `example_2_post_processing.mp4`.

## Procedure (summary)
1. **File > Open**: choose `couch_original.fds`. The Project Explorer shows:
   - 1 mesh definition with MULT, which expands to 4 meshes of 25x25x24 cells each (0.1 m);
   - 5 obstructions;
   - 3 surfaces: UPHOLSTERY, WALL and ignitor;
   - 3 materials: FABRIC, FOAM and GYPSUM PLASTER;
   - 1 ignitor particle.
2. Look at the case in **Model > Edit Meshes / Surfaces / Materials / Particles**. Nothing is changed.
3. **Model > Simulation Parameters**: change T_END from 600 s to 25 s.
4. **Model > Validate**: 0 errors, 0 warnings. Then **File > Save As** `couch.pyfds`.
5. **Run > Run Simulation**: "This computer, in parallel (MPI)" is preselected, with 4 processes (one mesh each, 15,000 cells per process).
6. **Results**: **File > Open** `run/couch.smv`. Show the temperature and HRRPUV slices, 3D smoke, burning rate and wall temperature on the couch, and the ignitor particle. Plot the HRR, and export stills and a movie.

## Expected results (from the validated run of 2026-10-28)
| Quantity | Value |
|---|---|
| Validation | 0 errors, 0 warnings |
| FDS end state | `STOP: FDS completed successfully`, wall clock 885 s, 4 MPI processes |
| HRR at 5 / 10 / 15 / 20 / 25 s | 56 / 300 / 561 / 544 / 543 kW |

## Changes from the original
- T_END was changed from 600 s to 25 s, for demo run time only. Nothing else in the physics was changed. The surface and material properties are the FDS example's own, which it labels as fabricated, illustrative values.
- On writing, PyFDS changes TITLE (descriptive only) and NUMBER_RADIATION_ANGLES from 100 to 104, the FDS default.
- `examples/example-2` contained only a backup project file (`couch.~bak.pyfds`). It was left untouched. This demo is built from the FDS distribution's original input.

## Known limitation shown by this example
- This case's slices are cell-centred (`CELL_CENTERED=.TRUE.`). Smokeview 6.10.1's script commands would not load them: LOADSLICE at X = 2.5, 2.55 and 2.6, LOADSLICEM and LOADSLCF were all tried, and each failed with "Slice files of type ... failed to load". For that reason the scripted Smokeview images for this example show 3D smoke and the burning rate on the couch. The temperature and HRRPUV slices are shown in PyFDS Results, and they can also be opened interactively in Smokeview from its Load/Unload menu.
