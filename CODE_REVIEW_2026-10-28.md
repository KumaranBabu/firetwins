# PyFDS code review and GUI layout pass (2026-10-28)

Scope of this pass: the main-window layout (bottom panels, VTK viewport, window sizing) was measured and changed. The rest of the
codebase (about 480 modules) was **not** read line by line; the findings below are from targeted inspection of the GUI package.
Baseline: commit `81fa4d0`, working tree clean apart from untracked example outputs; nothing was committed.

## 1. Layout: before and after (offscreen Qt, 1920x1040 window, Run Monitor tab shown)

| Measure | Before | After |
|---|---|---|
| Messages dock height | 401 px | 168 px |
| 3D viewport height | 559 px (45 % of window area) | 792 px (64 %) |
| 3D viewport height with dock hidden | 966 px | 966 px (unchanged) |
| Messages dock minimum width | 1008 px | 390 px |
| Main window minimum height (dock hidden) | 625 px | 416 px |

Measured with `measure_layout.py` / `minsize.py` (scratchpad). The 3D area is blank in offscreen mode, so the numbers are widget
geometry, not a visual check of VTK output. **Not verified:** behaviour at real Windows display scaling (125 %/150 %) on a physical screen.

### Causes found
1. `RunMonitorPanel` stacked headline, bar, detail, a 170 px minimum-height plot, the log and a button vertically. Its minimum hint (385 px)
   overrode the `resizeDocks(..., 210)` call, so the dock always opened about 400 px high.
2. `resizeDocks` is ignored on a hidden dock, and the dock starts hidden.
3. The Run Monitor headline label and "Open Results Viewer" button set a 637 px minimum width for the whole dock.
4. The Tool Properties panel set a 323 px minimum height for the left column, so the window could not be shorter than 625 px.
5. Startup maximised only on the very first run; later runs used whatever geometry was saved.

## 2. Changes made

| File | Change |
|---|---|
| `gui/run_monitor.py` | One status row on top (headline, bar, detail, button); curve and log side by side in a splitter; plot minimum height 170 -> 70; labels may shrink instead of widening the dock; the `.out` file is read once per tick instead of twice; the log is only reset when its text changed (keeps scroll position/selection). New helper `progress_from_text`; `read_progress` keeps its signature. |
| `gui/main_window/panels.py` | Bottom dock is sized to 150 px the first time it becomes visible (`_MESSAGES_HEIGHT`). |
| `gui/main_window/layout_tools.py` | `_LAYOUT_VERSION` 3 -> 4 so previously saved 400 px dock states are discarded once. |
| `gui/main_window/__init__.py` | The window always starts maximised. |
| `gui/main_window/viewport_bars.py` | Tool Properties panel wrapped in a scroll area. |
| `gui/main_window/workspaces.py` | Removed `has_saved_geometry()` (no remaining references anywhere). |
| `gui/panels/{validation,results,output}_panel.py` | Tighter margins; long summary/path labels no longer widen the dock; flat inner tabs in Output. |
| `tests/unit/test_gui_panels.py` | Three new tests: compact dock height and panel widths, short-screen window height, log scroll kept when unchanged. |

All panels remain reachable (Validation, Run Monitor, Results, Output tabs); the dock is resizable and its size is saved between sessions.

## 3. Findings not changed (prioritised)

- **Medium - Project Explorer rebuilds the whole tree on every model event** (`gui/main_window/explorer.py`: `_on_event` -> `refresh` -> `clear()` + `expandAll()`).
  Cost grows with model size, and the user's collapsed folders and scroll position are lost. Recommended: coalesce with a zero-delay timer
  and remember expansion state. Not done because existing tests expect a synchronous refresh.
- **Medium - no per-object hide/isolate found.** Visibility is controlled by layer (Layers dock, with Show all/Hide all) and by category (Show menu); a quick search found no eye icon or "Hide/Isolate" on explorer rows or in its context menu. Not exhaustively checked. A per-row toggle would be the natural next UX step and needs a design decision.
- **Low - `Viewport3D.shutdown` closes the plotter but does not explicitly release render-window resources;** acceptable at app exit, worth checking if viewports are ever created and destroyed repeatedly (split views).
- **Low - `.out` polling reads the entire file every 500 ms;** fine for local runs, could be slow for very large outputs on network shares. A tail-read would fix it.
- Dead-code removal was limited to the one provably unreferenced method above. Plugin registrations and runtime-loaded modules were not audited, so no further removals are recommended yet.
- Not reviewed in this pass: `domain`, `io`, `meshing`, `engineering`, `tenability`, `agent`, `results` packages, signal-slot lifetime across the whole GUI, and the Results viewer window layout (`gui/results`).

## 4. Tests

- Baseline before edits: 44 GUI tests passed.
- Full suite (`pytest tests`, offscreen Qt, conda env `agent`): **3735 passed, 0 failed** (10 min). The command exited non-zero (code 9) with a
  "Logging error: I/O on closed file" message at interpreter teardown; its cause was not investigated.
- After the final edit (removal of `has_saved_geometry`), 625 GUI-related tests were re-run: all passed. The full suite was not re-run after that last edit.
- Not tested: a real (non-offscreen) launch with a GPU, Windows display scaling, or an actual FDS run.
