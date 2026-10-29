# Example 1 - room fire with door, window and heat detector (original version)

The first demo case: a 4.8 x 3.3 x 2.4 m gypsum room with a door, a window, a propane burner, a ceiling heat detector,
a thermocouple tree and two temperature slices, on a 0.15 m mesh for 20 s.

> The client-ready version, with the burner corrected to 180 kW, a 0.1 m mesh, 60 s, a step-by-step manual and screen
> recordings, is in `client_demos/example_1/` (see its README for what was changed and why).

| File | What it is |
|---|---|
| `example_1.pyfds` | The project (also loaded by `tests/smoke/test_demo_case_builds.py`) |
| `example_1.pyfdsv` | A saved results visualization for its run |
| `gui_walkthrough.py` | Builds the case in the editor, runs FDS into `gui_run/` and saves screenshots to `gui/` |
| `make_gui_results.py` | Chart, probes and Smokeview pictures from `gui_run/` into `gui_results/` |
| `gui_viewer_walkthrough.py`, `gui_play_demo.py`, `gui_record_demo.py`, `gui_panels_walkthrough.py` | Results-window and panel screenshots and films into `gui_viewer/` and `gui/` |

The run output, screenshots and the two PDF manuals made by these scripts are no longer kept in git (trimmed
2026-10-29); run `gui_walkthrough.py` first to make them again. The current manual is
`documentation/FireTwins_User_Manual.pdf`.
