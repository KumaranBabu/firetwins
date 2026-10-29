# FireTwins client demos: validation report

**Date:** 2026-10-28
**Software:**
- PyFDS 0.3.0 (PySide6 6.12, PyVista 0.49, VTK 9.3.1)
- FDS 6.10.1 and Smokeview 6.10.1, from `fds_smv/`

**PC:** Windows 10 Pro 19045, screen 1360x768 at 100 % scaling.

Every result in this report comes from a run of the scripts in `client_demos/`:
- The scripts drive the real PyFDS windows on the desktop.
- They log each step's outcome to `documentation/screenshots/<example>/validation_log.json`.
- They capture every screenshot from the application with `QWidget.grab()`, and the Smokeview images with Smokeview's own renderer.

Nothing in the manual or the READMEs was typed in by hand from expectations. The numbers are read from the FDS output files (`.out`, `_hrr.csv`, `_devc.csv`).

## 1. Original condition of `examples/` (left unchanged)

| Item | Found | Assessment |
|---|---|---|
| `examples/example-1/` | A PyFDS project and FDS input for a room fire, plus GUI scripts, HTML manual templates and two PDF manuals from earlier work | The input ran, but did not match its own description (see below). |
| Example 1 burner | `&OBST ... SURF_ID='BURNER_SURF'` on a 0.6 x 0.6 x 0.15 m block | The 500 kW/m² surface was on all six faces, so the burning area was 0.36 + 4 x 0.09 = 0.72 m², about 360 kW instead of the intended 180 kW. |
| Example 1 mesh | 40x30x20 (0.15 m) | Matched the 360 kW fire (D*/dx ≈ 4.1). At the intended 180 kW, D*/dx = 3.2, below FDS's minimum of 4. |
| Example 1 T_END / yields | T_END 20 s; soot and CO yields 0 | The fire was still ramping up at 20 s (TAU_Q -15 s). With no soot, there was no visible smoke. |
| Example 1 boundaries | All six mesh faces OPEN, including the floor | The floor was open to the outside. |
| `examples/example-2/` | The same FDS couch case (`Examples/Fires/couch.fds`), run for 25 s on 4 MPI processes through the API and scripts, with a README, an HRR plot and viewer screenshots (63 / 354 / 518 / 537 kW at 5 / 10 / 15 / 25 s) | A working demo, but built by scripts rather than through the GUI. The client demo repeats it through the real GUI and the Run dialog. (An earlier version of this report said the folder held only an editor backup; that was wrong.) |

On 2026-10-29 `examples/` was trimmed to its sources (projects, FDS inputs, READMEs and the scripts); the run output, screenshots and the two old PDF manuals were removed and can be made again with those scripts.

## 2. Changes made for the client demos

The changes are listed with their reasons in `client_demos/example_1/README.md` and `client_demos/example_2/README.md`.

In short:
- **Example 1:**
  - The burner is now an INERT block with a 500 kW/m² vent on its top face, giving 180 kW.
  - The mesh is 0.1 m (60x45x30).
  - T_END is 60 s.
  - Soot and CO yields are 0.024 and 0.005.
  - A visibility slice was added at 1.5 m.
  - The floor is solid.
- **Example 2:** The original couch case, with T_END cut from 600 s to 25 s. No other physical parameter was changed.

The mesh refinement was made because PyFDS's pre-run check refused the 0.15 m mesh for the corrected 180 kW fire: "D*/dx 3.2 ... Minimum acceptable ratio is 4.0". That check behaved correctly, so the model was changed; the check was not relaxed.

## 3. Results

### Example 1: room fire, built from scratch in the GUI

| Step (log) | Outcome |
|---|---|
| A1 to G1: settings, mesh, room, burner, reaction, boundaries, detector, thermocouples, slices | ok, all done through the real dialogs; 36 screenshots |
| I1 validation | 0 errors; 1 warning: "Mesh 'DOMAIN': D*/dx ≈ 4.8, borderline resolution. Recommended ratio is ≥ 10.0." |
| K1 and K2 run from the Run dialog | ok: `STOP: FDS completed successfully`, 2396 s wall clock, 1 MPI process |
| R1 to R7 PyFDS Results | ok: 17 datasets, 7 views (temperature slices, 3D smoke, visibility, devices), HRR/DEVC plot, stills, MP4, `.pyfdsv` saved |
| R6 Smokeview script | ok: 3D smoke at 30 and 60 s, temperature slice at 30 and 60 s, plus a desktop capture of the Smokeview window |

Physical checks:

| Check | Expected | Measured | Verdict |
|---|---|---|---|
| Steady HRR (mean from 20 to 60 s) | 0.36 m² x 500 kW/m² = 180 kW | 179.9 kW | pass |
| HRR at the end of the t² ramp (15 s) | ≈ 180 kW | 177.5 kW | pass |
| Heat detector, 74 °C link at the ceiling over the fire | Activates in the first tens of seconds | 11.0 s | plausible for an RTI 5 detector in the plume |
| Thermocouple tree at 60 s (0.6 / 1.2 / 1.8 / 2.3 m) | Rising with height (hot layer) | 47 / 77 / 102 / 122 °C | pass, correctly stratified |

### Example 2: burning couch, imported FDS input, 4 MPI processes

| Step (log) | Outcome |
|---|---|
| A1 open `couch_original.fds` | ok: 1 MESH line with MULT, which expands to 4 meshes; 5 obstructions; surfaces UPHOLSTERY, WALL and ignitor; materials FABRIC, FOAM and GYPSUM PLASTER |
| B1 and B2 editors; T_END changed from 600 to 25 s | ok |
| C1 validation | 0 errors, 0 warnings |
| D1 and D2 run (Run dialog, "This computer, in parallel (MPI)", 4 processes) | ok: `STOP: FDS completed successfully`, 885 s wall clock, 4 MPI processes |
| R1 to R7 PyFDS Results | ok: 73 datasets, 8 views, HRR plot, stills, MP4, `.pyfdsv` saved |
| R6 Smokeview script | ok: 3D smoke at 15 and 25 s, and burning rate on the couch at 15 and 25 s |

HRR measured at 5, 10, 15, 20 and 25 s: 56, 300, 561, 544 and 543 kW. The fire spreads over the seat after ignition by the 1000 °C particle and levels off at about 550 kW. This matches the early part of the FDS example.

### Screen recordings (`documentation/videos/`)

| File | Content |
|---|---|
| `example_1_build_and_run.mp4` | Building the room through to the finished run. The run is shown as a time-lapse at one frame per 10 s. |
| `example_1_post_processing.mp4` | PyFDS Results and Smokeview |
| `example_2_open_and_run.mp4` | Opening the couch case, the editors and validation, and the 4-process run as a time-lapse |
| `example_2_post_processing.mp4` | PyFDS Results and Smokeview |

## 4. Defects found and fixed during this work (source changes)

| Area | Defect | Fix |
|---|---|---|
| Results viewer, software smoke renderer | When the GPU volume renderer is slow (as on this PC), PyFDS switches to VTK's software mapper. Its default sample distance is 1.0 world unit, ten 0.1 m cells per step, so 3D smoke was drawn as large grey triangles. | The sample distance is now locked to the grid spacing (`scene_adapter_extras._jitter`). Test: `test_software_smoke_renderer_samples_at_the_cell_size`. |
| Validation | Fuels FDS knows natively, such as PROPANE, were flagged as "fuel species not defined" | Built-in FDS fuels are accepted (`FuelSpeciesRule`); test added |
| Smokeview scripts | The builder wrote keywords Smokeview 6.10.1 rejects: SETRENDER, LOADSMOKE3D, LOADISOSURFACE, LOADPARTICLE | Now RENDERTYPE, LOAD3DSMOKE, LOADISO, LOADPARTICLES and LOADBOUNDARY [quantity], each checked against Smokeview 6.10.1 |
| Smokeview script builder (2026-10-29) | Commands Smokeview 6.10.1 does not know (SETCAMERA, SETCOLORMAP, SETFRAME, SHOWGEOM, STEP_FORWARD, LOADVECTOR, CLIP ...); RENDERSIZE ignored, so pictures were always 640x480; LOADSLICE cannot load cell-centred slices; LOADPLOT3D written with the wrong arguments; the runner could not move images to another drive | Camera, views, colour bar, clip planes, vectors and Plot3D now use XYZVIEW, VIEWXMIN.., SETCBAR, SETCLIPMODE/SETCLIPx, LOADSLCF and LOADPLOT3D mesh time, each checked by rendering with Smokeview 6.10.1; picture size and labels come from a small .ini the script loads (LOADINIFILE); cell-centred slices use LOADSLCF ... CELL_CENTERED=T; what scripts cannot do (colour bar range, labels on the image, frame stepping, hiding geometry, colours) raises SmokeviewScriptUnsupported. A test checks every keyword written against Smokeview's own keyword list. |
| Defaults | NUMBER_RADIATION_ANGLES default was 100 | 104, the FDS default |
| Run dialog | The dialog was about 890 px tall and mostly blank (hidden pages kept their size) | Sized to the visible page |

After these changes the full test suite passes: `pytest tests`, 3799 passed, 0 failed (offscreen Qt, 10 min, 2026-10-29).

## 5. Open issues (not fixed; recommended follow-ups)

1. **"Open Mesh Boundaries" opens the floor (ZMIN) too.** For a room on the ground this is rarely wanted. A default without the floor is recommended.
2. **Float noise in written inputs.** Draw Room wrote the window top as `1.9500000000000002` (0.9 + 1.05). FDS reads it correctly, but the value should be rounded where it is computed.
3. **PRES VELOCITY_TOLERANCE** is always written (0.05) even when it is not set. **DUMP DT_\*** values override NFRAMES.
4. **HVAC:** a fan shared by several ducts is copied into each duct; the DUCT_ID order on nodes is not preserved.
5. **Distribution:** `user_data` is read-only when installed under Program Files, and LICENSE and README are missing. Packaging is on hold by request.
6. **Resolution.** Example 1 runs at D*/dx = 4.8, accepted with a warning. A design-grade study of this fire needs about 0.05 m cells (ratio ≥ 10). That is about 650,000 cells, and the run is hours rather than minutes.

## 6. Reproducing

```
python client_demos/example_1/scripts/walkthrough.py     # about 45 min (FDS run about 40 min)
python client_demos/results_walkthrough.py example_1
python client_demos/example_2/scripts/walkthrough.py     # about 20 min (4 MPI processes)
python client_demos/results_walkthrough.py example_2
python documentation/build_manual.py                     # DOCX, plus PDF via Word
```

Each script uses the whole screen while it runs, so do not use the PC during the run.
