"""Assemble USER_MANUAL.html (one self-contained file) from manual_template.html's styles, manual_body.html and
the screenshots in gui/ and gui_results/.  Run after gui_walkthrough.py and make_gui_results.py."""
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
head = template[:template.index('<div class="wrap cover">')]        # <title>, fonts, <style>
extra_css = """
<style>
#cmp { break-before: page; }
.about { background: var(--surface); border-left: 4px solid var(--heat); border-radius: 4px; padding: 16px 20px 6px; margin: 26px 0 0; }
.about p { margin: 0 0 12px; }
.where { font-size: .92rem; margin: 0 0 10px; color: var(--muted); }
.where .tag { background: var(--heat-soft); color: var(--heat); }
.figrow figure, .shots figure { min-width: 0; }
.wrap > figure { margin-inline: auto; }
.wrap > figure img { width: auto; max-width: 100%; margin-inline: auto; }
.figrow img, .shots img { width: auto; max-width: 100%; margin-inline: auto; }
.figrow figure { display: flex; flex-direction: column; align-items: center; }
</style>
"""
body = fine_text.apply((SRC / "manual_body.html").read_text(encoding="utf-8"))


def embed(match: re.Match) -> str:
    rel = match.group(1)
    data = (HERE / f"{rel}").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


body = re.sub(r"%%([^%]+\.png)%%", embed, body)
assert "%%" not in body
html = head + extra_css + body
(HERE / "fine_mesh_manual.html").write_text(html, encoding="utf-8")
print(f"fine_mesh_manual.html  {len(html) // 1024} KB")
