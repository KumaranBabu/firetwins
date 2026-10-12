"""Assemble USER_MANUAL.html (one self-contained file) from manual_template.html's styles, manual_body.html and
the screenshots in gui/ and gui_results/.  Run after gui_walkthrough.py and make_gui_results.py."""
from __future__ import annotations

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
template = (HERE / "manual_template.html").read_text(encoding="utf-8")
head = template[:template.index('<div class="wrap cover">')]        # <title>, fonts, <style>
extra_css = """
<style>
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
body = (HERE / "manual_body.html").read_text(encoding="utf-8")
body = body.replace("when the fire was about 165 kW", "when the fire was about 145 kW")


def embed(match: re.Match) -> str:
    rel = match.group(1)
    data = (HERE / f"{rel}").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


body = re.sub(r"%%([^%]+\.png)%%", embed, body)
assert "%%" not in body
html = head + extra_css + body
(HERE / "USER_MANUAL.html").write_text(html, encoding="utf-8")
print(f"USER_MANUAL.html  {len(html) // 1024} KB")
