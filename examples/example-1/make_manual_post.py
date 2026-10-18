"""Assemble user_manual_postprocessing.html from manual_template.html's styles, the viewer section of manual_body.html
and the screenshots in gui_viewer/.  Run gui_viewer_walkthrough.py and gui_play_demo.py first, then print the HTML to PDF."""
from __future__ import annotations

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
template = (HERE / "manual_template.html").read_text(encoding="utf-8")
head = template[:template.index('<div class="wrap cover">')]
head = re.sub(r"<title>.*?</title>", "<title>PyFDS post-processing manual</title>", head, count=1, flags=re.S)
extra_css = (HERE / "make_manual.py").read_text(encoding="utf-8").split('extra_css = """')[1].split('"""')[0]

src = (HERE / "manual_body.html").read_text(encoding="utf-8")
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
<div class="note"><b>Measured on this case</b>Walls + slice + flame play at about <b>3 to 4 frames per second</b> on an ordinary laptop with an Intel HD 4600 graphics chip, and 1 s of film is 1 s of fire at ×1.00. Use ×2 or ×4 to get through the 20 s faster. The run has 655 flame frames; drawing every one at full size is not needed to follow the fire.</div>

"""

REC = """<h3>Record what you see, in real time</h3>
<div class="where"><span class="tag">Menu</span>File &gt; Record Movie (real time)… (F9) · Pause / Resume Recording (F10) · Stop Recording (Shift+F9)</div>
<p><b>Save Movie</b> draws every frame again, offline. <b>Record</b> is different: it films the 3D view as you use it, like a screen recorder for the scene only. Set up the picture, press <b>Record</b> (or F9) and choose the file name. Then play the run, orbit, pan, zoom, switch objects on and off: everything that happens in the 3D view goes into the film, including the clock in the corner.</p>
<p>The <b>Record</b>, <b>Pause</b> and <b>Stop</b> buttons sit in the bar above the 3D view, and the status bar shows a red <b>REC</b> with the seconds recorded so far. <b>Pause</b> (F10) stops the film without ending it; the time you spend paused is not in the film, so you can rearrange the scene and carry on. <b>Stop</b> (Shift+F9) closes the file.</p>
<div class="figrow">
<figure><img alt="File menu with the recording commands" src="%%gui_viewer/r1_file_menu.png%%"><figcaption>The recording commands in the File menu.</figcaption></figure>
<figure><img alt="The viewer while recording, REC 4.2 s in the status bar" src="%%gui_viewer/r2_recording.png%%"><figcaption>Recording while the run plays: the buttons above the scene, and REC with the running time at the bottom right.</figcaption></figure>
</div>
<figure><img alt="The viewer paused during recording" src="%%gui_viewer/r3_paused.png%%"><figcaption>Paused: the button now reads <b>Resume</b> and the status bar shows “REC paused”.</figcaption></figure>
<ul class="plain">
  <li><b>The film runs in real time.</b> It is written at 15 frames per second. If the computer draws fewer pictures than that, the last picture is repeated, so one second of film is one second on the clock and the film never runs fast. Slow drawing shows up as a less smooth film, not as a wrong speed.</li>
  <li><b>Size.</b> The film has the size of the 3D view when you press Record. Do not resize the window while recording; the film keeps its first size and crops or pads.</li>
  <li><b>Format.</b> MP4 (H.264) through the video encoder that comes with PyFDS. If no encoder is found, numbered PNG pictures are kept in a folder beside the chosen name instead.</li>
  <li><b>Closing the window</b> while recording ends the film cleanly; what was recorded is kept.</li>
</ul>
<div class="note"><b>Example</b>On this case a 5.9 s recording of the slice playing at ×1 gave 86 frames. It is saved as <code>gui_viewer/example_1_live.mp4</code>. Use <b>Save Movie</b> when you want an exact film of the whole run at a chosen frame rate and size, and <b>Record</b> when you want to show a walk-through of the scene.</div>

"""

TAB = """<h3>The viewer inside the main window</h3>
<div class="where"><span class="tag">Panel</span>Messages &gt; Results &gt; Open in Results Viewer · or Run Monitor &gt; Open Results Viewer</div>
<p>The viewer does not have to be a second window. The <b>Results</b> tab of the bottom <b>Messages</b> panel lists the result sets (<code>.smv</code>) of the last run, and opening one shows the 3D Results Viewer as a tab named <b>Results</b> beside the <b>Model</b> tab. The model, the Project Explorer and the Properties panel stay around it, so you can click <b>Model</b>, change something, and come back. Everything described in this manual works the same inside the tab. Close the tab with its x when you are done; it can be opened again at any time.</p>
<figure><img alt="The results viewer in a tab next to the Model tab" src="%%gui/15g_results_tab.png%%"><figcaption>The finished run in the Results tab of the main window.</figcaption></figure>

"""

TROUBLE = """<h3>If playback is slow or seems stuck</h3>
<ul class="plain">
  <li><b>Smoke or flame on an older graphics card.</b> The viewer measures the first picture. If it needs more than a third of a second, it switches by itself to the <b>compatibility smoke renderer</b> (software, about 15 times faster on the laptop used for this manual) and says so in the status bar. You can also choose it yourself: Preferences &gt; Rendering… &gt; <b>Max Compatibility</b>.</li>
  <li><b>Too much on at once.</b> Switch off what you do not need to see (double-click it in the tree). A slice is cheap; a 3D smoke volume costs the most.</li>
  <li><b>Smaller window, faster picture.</b> Drawing time grows with the number of pixels. Make the viewer window smaller for playback, or set the picture size separately when you save a movie.</li>
  <li><b>Speed.</b> Raise the speed box to ×2 or ×4. Frames are skipped, not slowed down, and the clock stays honest.</li>
  <li><b>The window seems frozen after Play.</b> It is busy drawing one frame: wait a second, press Pause, and step with <b>&gt;</b>. If the frame rate in the status bar stays below 1 fps, apply the compatibility renderer above.</li>
</ul>
<div class="note"><b>For the record</b>Before this was fixed the same scene took about 12 seconds per frame on that laptop: every smoke object made the graphics card draw the whole picture again (six times per frame), and the time stamps of all 655 frames were read from disk again for each frame. Now there is one picture per frame, the stamps are read once, and the software renderer is chosen automatically when the card is slow.</div>

"""

order = ["10a", "10b", "PLAY", "10c", "10d", "10e", "10f", "10g", "10h", "10i", "10j", "REC", "10k", "TAB", "TROUBLE"]
titles = {"10a": "Open the viewer", "10b": "Load the finished run", "PLAY": "Play the run", "10c": "Slices and the time bar",
          "10d": "3D smoke and flame", "10e": "Isosurfaces from Plot3D", "10f": "Select objects by clicking",
          "10g": "Colour bar and rendering quality", "10h": "Plots from the output files",
          "10i": "Views, section planes, dimensions and labels", "10j": "Screenshots and the animation", "REC": "Record what you see, in real time",
          "10k": "Save the visualization", "TAB": "The viewer inside the main window", "TROUBLE": "If playback is slow or seems stuck"}
body_parts = []
toc = []
for n, key in enumerate(order, 1):
    chunk = {"PLAY": PLAY, "REC": REC, "TAB": TAB, "TROUBLE": TROUBLE}.get(key) or parts[key]
    chunk = re.sub(r"<h3>(?:10[a-k] · )?(.*?)</h3>", lambda m, n=n: f'<h2 id="p{n}">{n} · {m.group(1)}</h2>', chunk, count=1)
    body_parts.append(chunk.strip())
    toc.append(f'<li><a href="#p{n}">{titles[key]}</a></li>')
body_text = "\n\n".join(body_parts)
body_text = (body_text.replace("the slices you asked for in step 5", "the slices requested in the model")
             .replace("The same curves as in 9b, now inside the viewer.", "The same curves FDS wrote to its output files, now inside the viewer."))

cover = f"""<div class="wrap cover">
  <div class="eyebrow">User manual · post-processing</div>
  <h1>Looking at the results: the 3D Results Viewer</h1>
  <p class="lede">How to open the finished demo room fire in 3D, play it like a film, cut it open, read values by clicking, plot the output files and save pictures and an MP4 animation, or record your own walk-through in real time. Every screenshot is the real window, working on the real run of the demo case.</p>
  <aside class="about">
    <div class="eyebrow" style="margin-bottom:8px">The demo case</div>
    <p><b>A gas burner is lit in the middle of a small room, and the run covers the first 20 seconds.</b> The room is 4.8 × 3.3 m and 2.4 m high with a door and a window. The burner grows to about 360 kW. FDS wrote two temperature slices, 3D smoke and flame data (655 frames), Plot3D files and two CSV files, in <code>examples/example-1/gui_run/</code>.</p>
    <p>Start the viewer from the main window with <b>Results &gt; View Results (3D)…</b>, then <b>File &gt; Open Results (.smv)…</b> and pick <code>gui_run/example_1.smv</code>. The ready-made setup <code>example_1.pyfdsv</code> opens the same picture in one step (File &gt; Open Results Visualization…).</p>
  </aside>
  <div class="meta"><span>Application: PyFDS desktop</span><span>Solver: FDS 6.10.1</span><span>Case: example_1</span><span>18 Oct 2026</span></div>
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
