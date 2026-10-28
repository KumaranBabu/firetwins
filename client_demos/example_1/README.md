# Example 1: Room fire with door, window and heat detector

A complete PyFDS workflow from an empty project:
1. Build a 4.8 x 3.3 x 2.4 m gypsum room with a door and a window, and add a 180 kW propane burner, a ceiling heat detector, a thermocouple tree and three slices.
2. Validate the model and run FDS 6.10.1 from the Run dialog.
3. Examine the results in the PyFDS Results window and in Smokeview.

The step-by-step instructions are in section 2 of `documentation/FireTwins_User_Manual.docx` (PDF beside it).

## Prerequisites
- FireTwins / PyFDS 0.3.0, with FDS 6.10.1 and Smokeview 6.10.1 (bundled in `fds_smv/`).
- Windows 10/11, a 1360x768 or larger screen, and about 2 GB of free RAM.
- About 40 minutes of computing time. The run took 2396 s wall clock on 1 process on the test PC.

## Files
| File | What it is |
|---|---|
| `example_1.pyfds` | The PyFDS project, built entirely through the GUI by `scripts/walkthrough.py` |
| `example_1.fds` | The FDS input written from that project |
| `example_1.pyfdsv` | The saved results visualization (views, colour bars, times) |
| `run/` | The FDS run: `.out`, `.smv`, `example_1_hrr.csv`, `example_1_devc.csv`, slices, 3D smoke, Smokeview renders |
| `results/` | Stills (`example_1_t30.png`, `example_1_t60.png`) and a movie (`example_1.mp4`) exported from PyFDS Results |
| `scripts/walkthrough.py` | Re-creates the project, validates it, runs FDS and takes the manual's screenshots |

The screen recordings are `documentation/videos/example_1_build_and_run.mp4` and `example_1_post_processing.mp4`.

## Procedure (summary)
1. **File > New**, then **Model > Project Settings**: set CHID `example_1`.
2. **Model > Simulation Parameters**: set T_END = 60 s.
3. **Model > Add Mesh**: set XB 0,6 / 0,4.5 / 0,3 and IJK 60,45,30. That gives 0.1 m cells, 81,000 cells in total.
4. **Library**: import `gypsum_wall_25mm`.
5. **Draw Room**: a 4.8 x 3.3 x 2.4 m room, with a door in the south wall (0.9 x 2.1 m) and a window in the east wall (1.2 x 1.05 m, sill at 0.9 m).
6. **Surface `BURNER_SURF`**: HRRPUA 500 kW/m² and TAU_Q -15 s.
7. **Burner**: add an INERT block of 0.6 x 0.6 x 0.15 m with a vent `BURNER_TOP` on its top face. 0.36 m² x 500 kW/m² gives 180 kW.
8. **Reaction**: PROPANE, with a soot yield of 0.024 and a CO yield of 0.005.
9. **Model > Open Mesh Boundaries**, then delete the floor vent so the floor stays solid.
10. Add the instruments and outputs:
    - a heat detector (library `heat_detector_74C`) at 3.0, 2.4, 2.35;
    - thermocouples at heights of 0.6, 1.2, 1.8 and 2.3 m;
    - slices: TEMPERATURE at Y = 2.4 and X = 3.0, and VISIBILITY at Z = 1.5.
11. **Model > Validate**: 0 errors and 1 warning (see below). Then save.
12. **Run > Run Simulation**: choose "This computer" and the folder `run/`.
13. **Results**: **File > Open** `run/example_1.smv`; show slices, 3D smoke, devices and the HRR plot; export stills and a movie.

## Expected results (from the validated run of 2026-10-28)
| Quantity | Value |
|---|---|
| Validation | 0 errors; 1 warning: "D*/dx ≈ 4.8, borderline resolution, recommended ≥ 10" |
| FDS end state | `STOP: FDS completed successfully`, wall clock 2396 s, 1 MPI process |
| HRR at 15 s (end of ramp) | 177 kW |
| Mean HRR from 20 to 60 s | 180 kW (design value 180 kW) |
| Heat detector reaches 74 °C (link temperature) | 11.0 s |
| Readings at 60 s | Heat detector link 124 °C; TC at 0.6 / 1.2 / 1.8 / 2.3 m: 47 / 77 / 102 / 122 °C |

Your timings will depend on the PC. The numbers should agree to within a few percent: FDS output is not bit-for-bit reproducible across machines.

## Changes from the original example (`examples/example-1`, left untouched)
| Change | Why |
|---|---|
| Burner: the 500 kW/m² surface was on every face of the 0.15 m block. It is now an INERT block with a 500 kW/m² vent on its top face only. | With the surface on every face the fire was about 360 kW, twice the 180 kW the example describes. |
| Mesh: 0.15 m cells (40x30x20) changed to 0.1 m cells (60x45x30). | At 0.15 m, D*/dx = 3.2. PyFDS's pre-run check correctly rejects that, because the minimum is 4. At 0.1 m, D*/dx = 4.8, which is accepted with a warning. Engineering use would need about 0.05 m (ratio ≥ 10). |
| T_END: 20 s changed to 60 s | The fire ramps up over 15 s (TAU_Q -15). 60 s shows the steady fire, the detector activation and the hot layer. |
| Soot yield 0 changed to 0.024, CO yield 0 changed to 0.005 | With no soot there is no visible smoke. These are the SFPE handbook values for propane. |
| Visibility slice added at Z = 1.5 m | Head-height visibility, the usual life-safety output. |
| Floor kept solid | "Open Mesh Boundaries" also opens the floor (ZMIN). The floor vent is deleted. |
| NUMBER_RADIATION_ANGLES: 100 changed to 104 | 104 is the FDS default. PyFDS's default is now 104 too. |

This is a demonstration case, not a design calculation. The mesh is coarser than recommended for engineering use; the manual's troubleshooting section explains how to refine it.
