"""Assemble user_manual_postprocessing.html from manual_template.html's styles, the viewer section of manual_body.html
and the screenshots in gui_viewer/.  Run gui_viewer_walkthrough.py and gui_play_demo.py first, then print the HTML to PDF."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "demo_room_fire"          # the first demo holds the template and the text this one is derived from
sys.path.insert(0, str(HERE))
import fine_text
template = (SRC / "manual_template.html").read_text(encoding="utf-8")
head = template[:template.index('<div class="wrap cover">')]
head = re.sub(r"<title>.*?</title>", "<title>PyFDS post-processing manual</title>", head, count=1, flags=re.S)
extra_css = (SRC / "make_manual.py").read_text(encoding="utf-8").split('extra_css = """')[1].split('"""')[0]

src = fine_text.apply((SRC / "manual_body.html").read_text(encoding="utf-8"))
sect = src[src.index('<h3>10a · Open the viewer</h3>'):src.index('<div class="wrap">\n<h2 id="files">')]
sect = re.sub(r'</div>\s*<div class="wrap">\s*', "\n", sect)             # one continuous page flow
sect = sect.rstrip()
if sect.endswith("</div>"):
    sect = sect[:-6].rstrip()

parts = {m.group(1): m.group(0) for m in re.finditer(r'<h3>(10[a-k]) · .*?(?=<h3>10[a-k] ·|\Z)', sect, flags=re.S)}
assert len(parts) == 11, sorted(parts)

PLAY = """<h3>Play the run</h3>
<div class="where"><span class="tag">Time bar</span>Play / Pause · &lt; and &gt; (one frame) · slider · speed (×1.00, ÷2, ×2) · Loop</div>
<p>Switch on the walls (<b>FDS Actual</b>), a slice and the flame, then press <b>Play</b> at the bottom left. The clock at the top left of the scene and the slider move together, the colours of the slice follow the fire, and the status bar shows <b>Playing</b>, the speed and the frame rate. Press <b>Pause</b> to stop on any frame; <b>&lt;</b> and <b>&gt;</b> then step one frame at a time. Change the speed with the <b>×</b> box or the <b>÷2</b> and <b>×2</b> buttons, and tick <b>Loop</b> to start again at the end.</p>
<div class="figrow">
<figure><img alt="The viewer before Play is pressed" src="%%gui_viewer/p1_before_play.png%%"><figcaption>Ready: walls (wireframe), the slice and the flame are on, the clock is at 0.</figcaption></figure>
<figure><img alt="The viewer while playing, clock at about 3 seconds" src="%%gui_viewer/p2_playing.png%%"><figcaption>Playing, a few seconds in: the Pause button, the moving clock and the frame rate in the status bar.</figcaption></figure>
</div>
<figure><img alt="The viewer a few seconds later, plume taller" src="%%gui_viewer/p3_playing_later.png%%"><figcaption>A few seconds later (t = 6.4 s): the plume has grown. Playback follows the real clock: if the computer cannot draw every frame in time, some frames are skipped, so the film does not run in slow motion.</figcaption></figure>
<div class="note"><b>Measured on this case</b>Walls + slice + flame play at about <b>1.5 to 2 frames per second</b> on an ordinary laptop with an Intel HD 4600 graphics chip. The fine mesh has four times the data per frame of the first demo (81 × 61 × 41 points instead of 41 × 31 × 21) and 864 flame frames, so it plays more slowly than the first demo; frames are skipped to keep up with the clock. Use ×2 or ×4 to get through the 20 s faster, or switch off what you do not need.</div>

"""

TROUBLE = """<h3>If playback is slow or seems stuck</h3>
<ul class="plain">
  <li><b>Smoke or flame on an older graphics card.</b> The viewer measures the first picture. If it needs more than a third of a second, it switches by itself to the <b>compatibility smoke renderer</b> (software, about 15 times faster on the laptop used for this manual) and says so in the status bar. You can also choose it yourself: Preferences &gt; Rendering… &gt; <b>Max Compatibility</b>.</li>
  <li><b>Too much on at once.</b> Switch off what you do not need to see (double-click it in the tree). A slice is cheap; a 3D smoke volume costs the most.</li>
  <li><b>Smaller window, faster picture.</b> Drawing time grows with the number of pixels. Make the viewer window smaller for playback, or set the picture size separately when you save a movie.</li>
  <li><b>Speed.</b> Raise the speed box to ×2 or ×4. Frames are skipped, not slowed down, and the clock stays honest.</li>
  <li><b>The window seems frozen after Play.</b> It is busy drawing one frame: wait a second, press Pause, and step with <b>&gt;</b>. If the frame rate in the status bar stays below 1 fps, apply the compatibility renderer above.</li>
</ul>
<div class="note"><b>For the record</b>Before this was fixed the first demo's scene took about 12 seconds per frame on that laptop: every smoke object made the graphics card draw the whole picture again (six times per frame), and the time stamps of all 655 frames were read from disk again for each frame. Now there is one picture per frame, the stamps are read once, and the software renderer is chosen automatically when the card is slow.</div>

"""

order = ["10a", "10b", "PLAY", "10c", "10d", "10e", "10f", "10g", "10h", "10i", "10j", "10k", "TROUBLE"]
titles = {"10a": "Open the viewer", "10b": "Load the finished run", "PLAY": "Play the run", "10c": "Slices and the time bar",
          "10d": "3D smoke and flame", "10e": "Isosurfaces from Plot3D", "10f": "Select objects by clicking",
          "10g": "Colour bar and rendering quality", "10h": "Plots from the output files",
          "10i": "Views, section planes, dimensions and labels", "10j": "Screenshots and the animation",
          "10k": "Save the visualization", "TROUBLE": "If playback is slow or seems stuck"}
body_parts = []
toc = []
for n, key in enumerate(order, 1):
    chunk = {"PLAY": PLAY, "TROUBLE": TROUBLE}.get(key) or parts[key]
    chunk = re.sub(r"<h3>(?:10[a-k] · )?(.*?)</h3>", lambda m, n=n: f'<h2 id="p{n}">{n} · {m.group(1)}</h2>', chunk, count=1)
    body_parts.append(chunk.strip())
    toc.append(f'<li><a href="#p{n}">{titles[key]}</a></li>')
body_text = "\n\n".join(body_parts)
body_text = (body_text.replace("the slices you asked for in step 5", "the slices requested in the model")
             .replace("The same curves as in 9b, now inside the viewer.", "The same curves FDS wrote to its output files, now inside the viewer."))

cover = f"""<div class="wrap cover">
  <div class="eyebrow">User manual · post-processing</div>
  <h1>Looking at the results: the 3D Results Viewer</h1>
  <p class="lede">How to open the finished fine-mesh demo room fire in 3D, play it like a film, cut it open, read values by clicking, plot the output files and save pictures and an MP4 animation. Every screenshot is the real window, working on the real run of the demo case.</p>
  <aside class="about">
    <div class="eyebrow" style="margin-bottom:8px">The fine-mesh demo case</div>
    <p><b>A gas burner is lit in the middle of a small room, and the run covers the first 20 seconds.</b> The room is 4.8 × 3.3 m and 2.4 m high with a door and a window. The burner grows to about 360 kW. The mesh has 192,000 cells of 0.075 m (half the size of the first demo's). FDS wrote two temperature slices, 3D smoke and flame data (864 frames), Plot3D files and two CSV files, in <code>examples/fine_mesh_demo_room/gui_run/</code>.</p>
    <p>Start the viewer from the main window with <b>Results &gt; View Results (3D)…</b>, then <b>File &gt; Open Results (.smv)…</b> and pick <code>gui_run/fine_mesh_demo_room.smv</code>. The ready-made setup <code>fine_mesh_demo_room.pyfdsv</code> opens the same picture in one step (File &gt; Open Results Visualization…).</p>
  </aside>
  <div class="meta"><span>Application: PyFDS desktop</span><span>Solver: FDS 6.10.1</span><span>Case: fine_mesh_demo_room</span><span>12 Oct 2026</span></div>
  <nav class="toc" aria-label="Contents"><strong>Contents</strong><ol>
    {chr(10).join(toc)}
  </ol></nav>
</div>

<div class="wrap">
"""
body = cover + body_text + "\n</div>\n"


def embed(match: re.Match) -> str:
    return "data:image/png;base64," + base64.b64encode((HERE / match.group(1)).read_bytes()).decode()


body = re.sub(r"%%([^%]+\.png)%%", embed, body)
assert "%%" not in body
html = head + "<style>" + extra_css.replace("<style>", "").replace("</style>", "") + "</style>\n" + body + "\n</body></html>\n"
(HERE / "user_manual_postprocessing.html").write_text(html, encoding="utf-8")
print(f"user_manual_postprocessing.html  {len(html) // 1024} KB, {len(order)} sections")
