"""Turns the text of the first demo's manual into the text for the fine-mesh case (same case, cells half the size).

Every replacement must match exactly once or more; ``apply`` raises if one no longer matches, so the manual cannot
silently keep a number from the coarse run.
"""
from __future__ import annotations

SRC = "demo_room_fire"

COMPARE = """<div class="wrap">
<h2 id="cmp">Fine mesh against the first demo</h2>
<p>This case is the first demo with one change: the cells are half the size (0.075 m instead of 0.15 m). Nothing else was touched: the room, the burner, the instruments and the 20 s run are the same. The table shows what the finer mesh changes.</p>
<div class="scroll"><table>
  <tr><th></th><th>First demo (0.15 m)</th><th>Fine mesh (0.075 m)</th></tr>
  <tr><td>Cells</td><td>40 × 30 × 20 = 24,000</td><td>80 × 60 × 40 = 192,000 (8 times as many)</td></tr>
  <tr><td>Fire resolution D*/dx</td><td>4.9</td><td>9.7</td></tr>
  <tr><td>Time steps for 20 s</td><td>679</td><td>1,891</td></tr>
  <tr><td>Computing time</td><td>160 s</td><td>3,090 s (51 min), 19 times longer</td></tr>
  <tr><td>Peak heat release rate</td><td>370 kW</td><td>377 kW</td></tr>
  <tr><td>Heat detector activates</td><td>9.7 s</td><td>7.9 s</td></tr>
  <tr><td>Thermocouple 0.6 m, at 20 s</td><td>707 °C</td><td>859 °C</td></tr>
  <tr><td>Thermocouple 1.2 m</td><td>432 °C</td><td>673 °C</td></tr>
  <tr><td>Thermocouple 1.8 m</td><td>302 °C</td><td>437 °C</td></tr>
  <tr><td>Thermocouple 2.3 m</td><td>280 °C</td><td>344 °C</td></tr>
  <tr><td>Probe 1.2 m above the burner</td><td>415 °C</td><td>460 °C</td></tr>
  <tr><td>Probe under the ceiling</td><td>229 °C</td><td>255 °C</td></tr>
  <tr><td>Probe in the doorway</td><td>45 °C</td><td>28 °C</td></tr>
  <tr><td>Slice read at the base of the plume (0.9 m up)</td><td>542 °C</td><td>815 °C</td></tr>
</table></div>
<div class="note heat"><b>What to take from it</b>The total heat release is the same (it is set by the burner), but the fine mesh resolves a narrower, hotter plume: the thermocouples near the flame read 150 to 240 °C higher, and the detector responds two seconds sooner. The coarse mesh smears the plume out. Neither is a validated prediction; the comparison shows how much the answer depends on the cell size, which is the reason to repeat a case on a finer mesh before relying on it.</div>
</div>

"""

# (old, new) pairs applied in order
REPL = [
    ("examples/demo_room_fire/gui_walkthrough.py", "examples/fine_mesh_demo_room/gui_walkthrough.py"),
    ("demo_room_gui.pyfds", "fine_mesh_demo_room_gui.pyfds"),
    ("demo_room.pyfdsv", "fine_mesh_demo_room.pyfdsv"),
    ("demo_room.mp4", "fine_mesh_demo_room.mp4"),
    ("demo_room.smv", "fine_mesh_demo_room.smv"),
    ("demo_room.fds", "fine_mesh_demo_room.fds"),
    ("demo_room_hrr.csv", "fine_mesh_demo_room_hrr.csv"),
    ("demo_room_devc.csv", "fine_mesh_demo_room_devc.csv"),
    ("case ID demo_room", "case ID fine_mesh_demo_room"),
    ("case ID <code>demo_room</code>", "case ID <code>fine_mesh_demo_room</code>"),
    ("Case: demo_room", "Case: fine_mesh_demo_room"),
    ("PyFDS demo case “demo_room”. Screenshots taken from the running application on 11 and 12 October 2026",
     "PyFDS fine-mesh demo case “fine_mesh_demo_room”. Screenshots taken from the running application on 12 October 2026"),
    ("Run date: 11 Oct 2026", "Run date: 12 Oct 2026"),
    ("<h1>Room fire, from empty model to results</h1>", "<h1>Room fire on a fine mesh, from empty model to results</h1>"),
    ("One complete simulation in the PyFDS desktop application,", "The demo room fire again, with the cells made half the size: one complete simulation in the PyFDS desktop application,"),
    ("It is small and quick (about three minutes to compute) so every step can be shown end to end.",
     "It is the first demo repeated with cells of 0.075 m instead of 0.15 m. The solver now needs about 51 minutes instead of three, and a closing section compares the two."),
    # at a glance
    ("<b>370 kW</b>", "<b>377 kW</b>"),
    ("<b>≈ 10 s</b><span>heat detector activates (FDS reports 9.7 s)", "<b>≈ 8 s</b><span>heat detector activates (FDS reports 7.9 s)"),
    ("<b>707 °C</b><span>gas temperature 0.6 m above the floor at 20 s", "<b>859 °C</b><span>gas temperature 0.6 m above the floor at 20 s"),
    ("<b>160 s</b><span>time FDS took to run the 20 s of fire", "<b>51 min</b><span>time FDS took to run the 20 s of fire (3,090 s)"),
    ("40 × 30 × 20 cells of 0.15 m (24,000 cells)", "80 × 60 × 40 cells of 0.075 m (192,000 cells; the first demo used 0.15 m)"),
    # mesh
    ("divided into 40 × 30 × 20 cells, so each cell is 0.15 m. That size puts the room walls exactly on cell boundaries.",
     "divided into 80 × 60 × 40 cells, so each cell is 0.075 m: half the size of the first demo, with eight times as many cells. The 0.15 m walls are exactly two cells thick."),
    ("(40, 30 and 20 are)", "(80, 60 and 40 are)"),
    # check
    ("The fire-resolution ratio (D*/dx) is 4.9; 10 or more is recommended for results you rely on. Halving the cell size would reach that but takes about eight times as long to compute. Acceptable for a demonstration.",
     "The fire-resolution ratio (D*/dx) is 9.7: double the 4.9 of the first demo and now just under the recommended 10. The price was a run 19 times longer (51 minutes instead of 160 seconds)."),
    # run
    ("heat release near 357 kilowatts", "heat release near 340 kilowatts"),
    ("Message: Simulation complete, wall time 160 seconds", "Message: Simulation complete, wall time 3090 seconds"),
    ("This run took 160 s of computer time.", "This run took 3,090 s (51 minutes) of computer time."),
    # results
    ("hot plume of about 780 °C at its base; the probe reads 415 °C at 1.2 m above the burner", "hot plume of about 920 °C at its base; the probe reads 460 °C at 1.2 m above the burner"),
    ("<b>707 °C</b><span>thermocouple at 0.6 m, 20 s", "<b>859 °C</b><span>thermocouple at 0.6 m, 20 s"),
    ("<b>432 °C</b><span>thermocouple at 1.2 m, 20 s", "<b>673 °C</b><span>thermocouple at 1.2 m, 20 s"),
    ("<b>302 °C</b><span>thermocouple at 1.8 m, 20 s", "<b>437 °C</b><span>thermocouple at 1.8 m, 20 s"),
    ("<b>280 °C</b><span>thermocouple at 2.3 m, 20 s", "<b>344 °C</b><span>thermocouple at 2.3 m, 20 s"),
    ("FDS reports the heat detector activating at 9.7 s, when the fire was about 165 kW. The recorded link temperature (saved once per second) passes 74 °C between 10 and 11 s.",
     "FDS reports the heat detector activating at 7.9 s, when the fire was about 97 kW: nearly two seconds earlier than with the coarse mesh (9.7 s), because the finer cells resolve the narrow, hot plume under the ceiling. The recorded link temperature (saved once per second) passes 74 °C between 8 and 9 s."),
    ("<b>415 °C</b> 1.2 m above the burner, <b>229 °C</b> under the ceiling above it, <b>45 °C</b> in the doorway",
     "<b>460 °C</b> 1.2 m above the burner, <b>255 °C</b> under the ceiling above it, <b>28 °C</b> in the doorway"),
    # 3D viewer
    ("<code>TEMPERATURE = 541.9 C at (3.01, 2.40, 0.89) m</code>", "<code>TEMPERATURE = 814.8 C at (3.02, 2.40, 0.90) m</code>"),
    ("A click on the slice at 0.89 m above the floor: the status bar reads 541.9 °C at that point (t = 20 s).",
     "A click on the slice at 0.90 m above the floor: the status bar reads 814.8 °C at that point (t = 20 s)."),
    ("the status bar shows 541.9 C", "the status bar shows 814.8 C"),
    ("Colorbar settings for TEMPERATURE.", "Colorbar settings for TEMPERATURE. In this manual the range is fixed at 20 to 900 °C so that the narrow hot plume of the fine mesh uses the whole colour scale."),
    # files and limits
    ("(about four minutes, the window opens and operates itself)", "(about an hour, because the solver alone takes 51 minutes; the window opens and operates itself)"),
    ("Twenty seconds of a small fire in coarse cells shows the workflow. The fire is only borderline resolved (warning 1) and the room has not reached a steady state.",
     "Twenty seconds of a small fire shows the workflow. With cells of 0.075 m the fire is better resolved than in the first demo, but still just under the recommended D*/dx of 10 (warning 1), and the room has not reached a steady state."),
    ("Clicking an object in the 3D scene does not select it yet (use the tree), the animation is made frame by frame and not recorded live",
     "Smoke and flame volumes cannot be selected by clicking, the animation is made frame by frame and not recorded live"),
]


def apply(text: str) -> str:
    for old, new in REPL:
        if old not in text:
            raise ValueError(f"fine_text: no match for {old[:70]!r}")
        text = text.replace(old, new)
    marker = '<div class="wrap">\n<h2 id="s10">'
    if marker not in text:
        raise ValueError("fine_text: section 10 marker not found")
    text = text.replace(marker, COMPARE + marker, 1)
    text = text.replace('<li><a href="#s10">', '<li><a href="#cmp">Fine mesh against the first demo</a></li>\n      <li><a href="#s10">', 1)
    return text
