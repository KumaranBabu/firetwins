"""Screenshots and movies (phase V9): what to render, with which file names, and the command-line options.

Pure planning: this module decides *which* images at *which* times from *which* views, names the files like
PyroSim Results (``name_time_viewname.ext``) and parses the ``-screenshot`` / ``-movie`` command lines. The
3D window does the drawing.
"""
from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

CURRENT = "<current view>"


@dataclass
class Shot:
    path: str
    time: float
    view: str = CURRENT


def safe_name(name: str) -> str:
    """Characters not allowed in file names become underscores (a view called ``"Floor 0"`` keeps its space)."""
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _stem(path: str) -> Tuple[Path, str, str]:
    p = Path(path)
    return p.parent, p.stem, p.suffix or ".png"


def single(path: str, time: float, view: str = CURRENT) -> List[Shot]:
    return [Shot(path, float(time), view)]


def multiple(path: str, start: float, end: float, interval: float, views: Sequence[str] = (CURRENT,),
             tour_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> List[Shot]:
    """One image per time between *start* and *end* per view (``name_time_viewname.ext``). A view with a tour only
    gets images at times inside the tour."""
    if interval <= 0:
        raise ValueError("the time interval must be positive")
    if end < start:
        raise ValueError("end time must not be before start time")
    folder, stem, ext = _stem(path)
    n = int(np.floor((end - start) / interval + 1e-9)) + 1
    times = [start + i * interval for i in range(n)]
    out: List[Shot] = []
    for t in times:
        for v in views:
            rng = (tour_ranges or {}).get(v)
            if rng is not None and not rng[0] <= t <= rng[1]:
                continue
            tail = "" if v == CURRENT else f"_{safe_name(v)}"
            out.append(Shot(str(folder / f"{stem}_{t:07.3f}{tail}{ext}"), t, v))
    return out


def parse_tsv(text: str) -> List[Tuple[float, List[str]]]:
    """``time<TAB>view<TAB>view...`` rows. A view name with a tab is quoted, or the tab is escaped with a backslash."""
    rows = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        cells = _split_tabs(raw)
        try:
            t = float(cells[0])
        except ValueError:
            raise ValueError(f"the first column must be a time, got {cells[0]!r}") from None
        rows.append((t, [c for c in cells[1:] if c]))
    return rows


def _split_tabs(line: str) -> List[str]:
    cells, cur, quoted, i = [], "", False, 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] in "\t\"":
            cur += line[i + 1]
            i += 2
            continue
        if ch == '"':
            quoted = not quoted
        elif ch == "\t" and not quoted:
            cells.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur)
    return [c.strip() for c in cells]


def from_file(path: str, tsv_text: str, tour_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> List[Shot]:
    folder, stem, ext = _stem(path)
    out = []
    for t, views in parse_tsv(tsv_text):
        for v in views:
            rng = (tour_ranges or {}).get(v)
            if rng is not None and not rng[0] <= t <= rng[1]:
                continue
            out.append(Shot(str(folder / f"{stem}_{t:07.3f}_{safe_name(v)}{ext}"), t, v))
    return out


# -- movies -------------------------------------------------------------------------------------------------------
@dataclass
class MoviePlan:
    path: str
    times: List[float]                   # playback time of each frame
    fps: int
    speed: float
    size: Tuple[int, int]


def movie_plan(path: str, begin: float, end: float, fps: int = 30, speed: float = 1.0,
               size: Tuple[int, int] = (1920, 1080)) -> MoviePlan:
    """Frame times for a movie: *speed* x real time at *fps* frames per second (2x plays twice as fast)."""
    if end <= begin:
        raise ValueError("end must be after begin")
    if fps < 1 or speed <= 0:
        raise ValueError("fps must be at least 1 and speed positive")
    if size[0] < 16 or size[1] < 16:
        raise ValueError("the movie size is too small")
    step = speed / fps
    n = int(np.floor((end - begin) / step + 1e-9)) + 1
    return MoviePlan(path, [begin + i * step for i in range(n)], fps, speed, (size[0] - size[0] % 2, size[1] - size[1] % 2))


def movie360_plan(path: str, begin: float, end: float, fps: int = 30, speed: float = 1.0, width: int = 3840) -> MoviePlan:
    """A 360 movie: like :func:`movie_plan` but always 2:1 (equirectangular), *width* a multiple of 4."""
    from .panorama import movie_size
    return movie_plan(path, begin, end, fps, speed, movie_size(width))


def frame_path(frames_dir: str, stem: str, index: int) -> str:
    return str(Path(frames_dir) / f"{stem}_{index:05d}.png")


# -- command line -------------------------------------------------------------------------------------------------
_FLAGS_VALUE = {"-ssname": "ssname", "-sswidth": "sswidth", "-ssheight": "ssheight", "-ssview": "ssview",
                "-ssviews": "ssviews", "-sstime": "sstime", "-sstbegin": "sstbegin", "-sstend": "sstend",
                "-ssdt": "ssdt", "-sstsv": "sstsv", "-mvname": "mvname", "-mvwidth": "mvwidth", "-mvheight": "mvheight",
                "-mvframerate": "mvframerate", "-mvspeed": "mvspeed", "-mvview": "mvview", "-mvbegin": "mvbegin",
                "-mvend": "mvend", "-mvencoder": "mvencoder", "-mvencoderpreset": "mvencoderpreset",
                "-mvencoderbitrate": "mvencoderbitrate", "-mvencoderkeyframeinterval": "mvencoderkeyframeinterval"}
_FLAGS_BOOL = {"-screenshot": "screenshot", "-movie": "movie", "-mvlod": "mvlod", "-mvhideoverlays": "mvhideoverlays", "-mv360": "mv360"}
_NUMERIC = {"sswidth": int, "ssheight": int, "sstime": float, "sstbegin": float, "sstend": float, "ssdt": float,
            "mvwidth": int, "mvheight": int, "mvframerate": int, "mvspeed": float, "mvbegin": float, "mvend": float,
            "mvencoderpreset": int, "mvencoderbitrate": int, "mvencoderkeyframeinterval": int}


@dataclass
class CliRequest:
    visualization: str = ""
    screenshot: bool = False
    movie: bool = False
    options: Dict[str, object] = field(default_factory=dict)


def parse_cli(argv: Sequence[str]) -> CliRequest:
    """The Results-compatible options (``-screenshot -ssname x.png -sswidth 1280 ... path.pyfdsv``)."""
    req = CliRequest()
    it = iter(argv)
    for a in it:
        if a in _FLAGS_BOOL:
            setattr(req, _FLAGS_BOOL[a], True) if a in ("-screenshot", "-movie") else req.options.__setitem__(_FLAGS_BOOL[a], True)
        elif a in _FLAGS_VALUE:
            key = _FLAGS_VALUE[a]
            try:
                raw = next(it)
            except StopIteration:
                raise ValueError(f"{a} needs a value") from None
            try:
                req.options[key] = _NUMERIC[key](raw) if key in _NUMERIC else raw
            except ValueError:
                raise ValueError(f"{a} needs a number, got {raw!r}") from None
        elif a.startswith("-"):
            raise ValueError(f"unknown option {a}")
        else:
            req.visualization = a
    if req.screenshot and req.movie:
        raise ValueError("-screenshot and -movie cannot be combined")
    return req


def plan_from_cli(req: CliRequest, base_dir: str, default_view_times: Tuple[float, float],
                  tour_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> List[Shot]:
    """Screenshots a ``-screenshot`` request asks for (single, multiple or from a tsv file)."""
    o = req.options
    name = str(o.get("ssname") or (Path(req.visualization).stem + ".png"))
    path = name if os.path.isabs(name) else str(Path(base_dir) / name)
    if "sstsv" in o:
        tsv = o["sstsv"]
        tsv = str(tsv) if os.path.isabs(str(tsv)) else str(Path(base_dir) / str(tsv))
        return from_file(path, Path(tsv).read_text(encoding="utf-8"), tour_ranges)
    if "sstbegin" in o or "sstend" in o or "ssdt" in o:
        views = [v.strip() for v in str(o.get("ssviews", CURRENT)).split(",")]
        return multiple(path, float(o.get("sstbegin", default_view_times[0])), float(o.get("sstend", default_view_times[1])),
                        float(o.get("ssdt", 1.0)), views, tour_ranges)
    return single(path, float(o.get("sstime", default_view_times[0])), str(o.get("ssview", CURRENT)))
