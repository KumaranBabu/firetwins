# PyFDS deeper review: bugs, clean-up, GUI and missing features (2026-10-29)

Baseline: commit `f3568a4`, 452 source modules (71,845 lines), full suite 3,834 passed.
This pass covered the parts the 2026-10-28 review left out: `domain`, `engineering`, `tenability`, `agent`, the
FDS writer, and a dump of every menu, toolbar and panel in both windows (offscreen Qt). Nothing was changed.
How each finding was established is stated; "check" means the code was read but the result was not run.

## 1. Bugs (ranked)

| # | Severity | Where | Finding | Evidence |
|---|---|---|---|---|
| B1 | High | `gui/agent_panel.py` + `core/events.py` | The AI assistant runs its tool calls on a background `QThread`. Tools change the model, the event bus calls its subscribers synchronously, and the Project Explorer, panels and HVAC editor then rebuild Qt widgets **from that thread**. Qt widgets are not thread-safe: random crashes or corrupted trees when the assistant edits the model. | Read: `_SendWorker.run` -> `AgentSession.send` -> `dispatcher.call`; `EventBus.emit` loops over handlers directly; `ProjectExplorer._on_event` -> `refresh()` -> `clear()`. Not reproduced (needs an API key). |
| B2 | High | `io/fds_writer_head.py:92` | `&PRES VELOCITY_TOLERANCE=0.05` is written into every input. FDS's own default depends on the cell size, so this silently changes the pressure solver on every model whose user never set it (`MAX_PRESSURE_ITERATIONS=10` likewise always written). | Read: `_write_pres` has no "only if set" test; `PresParams.velocity_tolerance: float = 0.05`. |
| B3 | High | `api/mesh_ops.py:337` | **Open Mesh Boundaries** puts an OPEN vent on all six faces, including Z-min, so the floor is open to the outside. | Read: the loop runs over all three axes and both sides with no exception for the floor. |
| B4 | High | `io/fds_writer_hvac.py`, import | A fan shared by several ducts is written as one renamed copy per duct (known since 2026-10-28). Behaviour is the same only while the copies stay identical; editing one fan silently diverges them. | Noted in `test_fds_roundtrip_fidelity.py` limits. |
| B5 | Medium | `tenability/fed.py` | Check the constants against the reference before clients use FED results: CO uses `C^1.036 / 40,000`, which matches neither ISO 13571 (35,000 ppm·min) nor Purser's 3.317e-5·RMV/D at 25 L/min (~36,000); the CO₂ hyperventilation factor is applied to CO only (ISO 13571 applies it to the asphyxiants); heat is added to the gas FED instead of being kept as a separate FEC. | Read, not compared with the SFPE text. |
| B6 | Medium | Draw Room | Coordinates come out as values like `2.9999999` instead of `3.0`; they should be snapped to the grid before writing. | Known from the demos (validation report §5). |
| B7 | Low | `gui/extras.py:93`, `actions_import.py:132`, `run_monitor.py:158` | User messages say "Run > Run Simulation", but the menu is titled **Analysis** (`shell_bars.py` renames it). | Menu dump + grep. |
| B8 | Low | `agent/anthropic_loop.py:24` | `DEFAULT_MODEL = "claude-sonnet-5"` is a previous-generation model (corrected 2026-10-29: the id is valid, the first draft of this review wrongly said it would fail). The loop also ignored a `refusal` stop reason and capped replies at 4,096 tokens. | Read. |
| B9 | Low | `engineering/mesh_advisor.py:177` | `n_per` was a dead duplicate of `cells_per`, which the function does use (corrected: not a bug, removed as clean-up). | ruff F841. |
| B10 | Low | `io/fds_builders/spatial.py:149` | An unreadable `XYZ` is dropped with `except: pass`, no warning in the import report. | Read. |
| B11 | Low | `execution/runner.py`, `queue.py`, `core/selection.py` | Callback errors (progress, completion, observers) are swallowed with `pass`; a broken GUI callback disappears without a log line. 44 such silent handlers in all. | grep. |

## 2. Code clean-up

| Item | Count / place | Suggestion |
|---|---|---|
| Unused imports (many are deliberate re-exports with `# noqa`) | 161 F401, 110 stale `noqa` | `ruff --fix` for the stale `noqa`; review the rest per module. |
| Unused locals | 9 (`hvac_solver.n_nodes`, `mesh_ops.hi2`, `report.times`, ...) | Delete; `hvac_solver.py:166` also has a dead `elif ... pass` branch. |
| Cyrillic letter in a function name | `tenability/fed.py:63` `_vcо2_factor` (the "о" is U+043E) | Rename; it cannot be typed or searched for normally. |
| Empty placeholder scaffolding | `gui/main_window/placeholders.py` (empty table, mixin still in `MainWindow`), `ActionSpec.placeholder` | Keep (corrected): five tests use the empty table as a guard that no menu entry is a "Coming soon" box. |
| Blind `except Exception` | 276 | Log at least `logger.exception` in the 44 silent ones; narrow where the error type is known. |
| `zip()` without `strict=` | 61 | Add `strict=True` where lengths must match (writer arrays, ramps). |
| Complex functions (McCabe > 10) | 85 | Leave unless touched; the file-size cap (400 lines) already keeps modules small. |
| Global singletons via `global` | config, event bus, registries (6) | Fine for an app; note for tests. |

## 3. GUI and menus

Menu dump (offscreen, both windows): no shortcut clashes, every entry has a status tip, no duplicate commands in the editor.

### 3.1 Menus to split or regroup
| Menu | Now | Proposal |
|---|---|---|
| Editor **Model** | 41 top-level entries (13 "Edit ...", 15 "Add ...", library items, checks, 4 submenus) | Keep the "Edit <Things>" block; move every "Add ..." into an **Add** submenu grouped Geometry / Physics / Controls; put Library, Typed Surface, Liquid Fuel and Complex Reaction under **Library**; move Validate / Auto-Fix / Model Checks into one **Check** block. Optionally a top-level **Geometry** menu (Draw, Floors, Convert to Blocks, Open Mesh Boundaries). |
| Checks spread over two menus | Model: Edit Model Checks, Run Model Checks, Validate Project, Auto-Fix. Tools: Validation, Find Errors, Mesh Diagnostics, Mesh Checker | Six commands for "check my model". Merge into Model > Check (Validate, Find Errors only, Mesh Checks, Auto-Fix, Edit Checks). Tools keeps Geometry Repair, Units, Calculator, Script Console, Plugins. |
| Editor **Results** | Open PyFDS Results, Results Viewer..., View Results of Last Run, Preview Model in Results | Three ways to open the viewer; keep "Open Results..." and "Results of Last Run". |
| Editor **Edit** | 24 flat entries | **Visibility** submenu (Hide/Show/Filter/Show All) and **Transform** submenu (Move/Rotate/Scale/Mirror/Snap). |
| Editor **View** | Four render modes as flat entries | A **Rendering Mode** submenu, as the Results window already has. |
| Editor **Devices** | 20 flat entries | Group into Detection, Measurement, Suppression, Special. |
| Results **File** | 21 entries | **Record** submenu (Save Movie, 360 Movie, Record, Pause, Stop); "Close" and "Exit" both present. |
| Results **View** | Section box items and four unit submenus flat | **Section Box** submenu; one **Units** submenu with Temperature / Concentration / Mass Fraction. |
| Help | "PyroSim User Manual (reference)" opens Thunderhead's PDF from `docs/` | Remove before delivery: that manual is not ours to ship, and `docs/` is not in git. |

### 3.2 Panels and windows
| Item | Proposal |
|---|---|
| Project Explorer rebuilds the whole tree on every model event (still open from 2026-10-28) | Coalesce with a 0 ms timer, keep expansion and scroll; add a **search box** to filter the tree by name. |
| Engineering calculators exist only in the API and the AI assistant (`engineering/`: plume, fire growth, zone model, tunnel, mesh advisor; `tenability/`: FED, layer height, visibility) | A **Fire Engineering** menu or dock: hand-calculation panel with inputs, results and references; "suggest mesh" button in the mesh editor using `mesh_advisor`. |
| `results/comparator.py` (two runs, device by device) has no GUI | **Compare Runs** in the Results window: pick a second `.smv`, overlay device curves, table of differences. |
| `results/report.py` has no GUI | **Generate Report** (HTML/PDF) from the Results window. |
| Tenability results | **Analysis > Tenability (ASET)** in the Results window: FED, visibility and layer height at chosen devices, time to limit, ASET/RSET margin. |
| Run Monitor | Show estimated time to finish from the time-step rate (the data is already read). |
| Properties dock | Show the written FDS line for the selected object (read-only), so users see what goes into the input. |

## 4. Features missing against FDS 6.10

Typed editors exist for 33 namelists. `CSVF`, `CLIP`, `COMB`, `TABL`, `CATF` and `TRNX/Y/Z` details are kept as text on
import (nothing lost) but cannot be edited. Worth adding first: **CLIP** (temperature/density limits, common in
validation cases) and **TABL** (spray patterns for sprinklers). Not measured: which of these the client's cases use.

## 5. Suggested order

1. **Writer correctness** (B2, B3, B4, B6) with exact-line tests. About half a day.
2. **AI assistant safety** (B1, B8): run tool calls on the GUI thread (queued call from the worker), fix the model id.
3. **FED check** (B5) against SFPE / ISO 13571 before any client relies on tenability numbers.
4. **Menu regrouping** (§3.1): Model and the check commands first; one test per menu for its new structure.
5. **New panels** (§3.2): Fire Engineering calculators, Tenability and Compare Runs in Results, Explorer search.
6. Clean-up (§2) and the small bugs (B7, B9-B11), in the same commits as nearby work.
7. CLIP and TABL editors.

## 6. Not covered

- Behaviour of the GUI on a real screen (only offscreen dumps were taken in this pass).
- `meshing` engines (optional packages, not installed), the plugin loader and the CLI were not read line by line.
- No finding here was reproduced by a failing test yet; each fix should start with one.

## 7. Status after the fix run (2026-10-29)

| Item | Commit | Result |
|---|---|---|
| B2 &PRES defaults, SOLVER now written; B3 floor stays closed; B6 number noise | `6384374` | Fixed; old projects migrate on load |
| B4 shared fan / air coil / filter | `86c1db9` | One object with `more_duct_ids` / `more_node_ids` |
| B1 AI tool calls on the GUI thread; B8 loop (model `claude-opus-5-5`, server-side fallback, refusal) | `33b4d2c` | Fixed; B8's "invalid id" claim was wrong and is corrected above |
| B5 FED constants; B7 "Run >" messages | `46a06ff` | FED now uses FDS 6.10's constants (eq. 22.42-22.49); heat dose separate |
| B9-B11, clean-up | `634afb1` | Silent listener errors logged; dead code removed; B9 was not a bug |
| 3.1 menus | `9ab4cab`, `2dc53fc` | Model 41 -> 30 entries; checks grouped; Visibility / Transform / Rendering Mode / Movie / Section Box / Units submenus; PyroSim manual removed from Help |
| 3.2 Explorer | `dd19aec` | Filter box; collapsed folders, scroll and filter survive rebuilds |
| 3.2 Fire Engineering calculators | `24f755d` | New dialog; **found five calculations that never worked** (four `api.engineering` wrappers, `detector_response_time`), which also broke five AI-assistant tools |
| 3.2 Tenability | `a61e8ba` | Analysis > Tenability (FED) in the Results window |
| 3.2 Compare Runs | `08a0fc3` | Analysis > Compare Runs; comparator reported baseline `Time` as a channel (precedence bug) |

Not done in this run: Explorer refresh coalescing (tests rely on a synchronous rebuild), Run Monitor time-to-finish,
the FDS line in the Properties dock, Devices menu grouping, the three "open results" entries in the editor's Results
menu, and CLIP / TABL editors (section 4).
