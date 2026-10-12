"""``python -m pyfds.gui.results.cli [-screenshot|-movie] options case.pyfdsv|case.smv``: scripted images and movies.

Runs without a window. Options follow PyroSim Results (``-ssname``, ``-sswidth``, ``-sstime``, ``-sstsv``,
``-mvname``, ``-mvframerate``, ``-mvspeed`` ...), see ``pyfds.results.viz.capture``. Exit status is 0 on
success and 1 with a one-line message otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from pyfds.api.viz import capture as cap

from .scene_adapter import make_offscreen_renderer, make_panorama_renderer


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        req = cap.parse_cli(argv)
        if not req.visualization:
            raise ValueError("give a .pyfdsv or .smv file")
        if not (req.screenshot or req.movie):
            raise ValueError("choose -screenshot or -movie")
        from pyfds.api.facade import FdsApi
        viewer = FdsApi().viewer
        src = Path(req.visualization)
        if not src.exists():
            raise FileNotFoundError(f"{src} not found")
        (viewer.open_visualization if src.suffix == ".pyfdsv" else viewer.open_results)(str(src))
        if viewer.run is None:
            raise ValueError("the visualization has no results loaded")
        base = str(src.parent)
        o = req.options
        size = (int(o.get("sswidth" if req.screenshot else "mvwidth", 1920)),
                int(o.get("ssheight" if req.screenshot else "mvheight", 1080)))
        render = viewer.renderer = make_offscreen_renderer(viewer)
        lo, hi = viewer.time_range()
        if req.screenshot:
            shots = cap.plan_from_cli(req, base, (lo, hi), viewer._tour_ranges())
            done = viewer.render_screenshots(shots, render, size)
            print(f"wrote {len(done)} screenshot(s)")
        else:
            name = str(o.get("mvname") or src.with_suffix(".mp4").name)
            path = name if Path(name).is_absolute() else str(Path(base) / name)
            if o.get("mv360"):
                plan = cap.movie360_plan(path, float(o.get("mvbegin", lo)), float(o.get("mvend", hi)),
                                         int(o.get("mvframerate", 30)), float(o.get("mvspeed", 1.0)), int(o.get("mvwidth", 3840)))
                render = make_panorama_renderer(viewer)
            else:
                plan = cap.movie_plan(path, float(o.get("mvbegin", lo)), float(o.get("mvend", hi)), int(o.get("mvframerate", 30)),
                                      float(o.get("mvspeed", 1.0)), size)
            res = viewer.render_movie(plan, render, str(o.get("mvview", cap.CURRENT)))
            print(f"wrote {res['path']}" if res["encoded"] else f"no encoder: frames kept in {res['frames_dir']}")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
