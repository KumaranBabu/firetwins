"""Timelines (phase V10): the global clock, FDS time offset and the time shown in the 3D view."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

import numpy as np

from .model import Timelines


def reference(tl: Timelines) -> datetime:
    try:
        return datetime.fromisoformat(tl.reference_time)
    except ValueError:
        raise ValueError(f"reference time must be ISO 8601 (2018-06-03T15:47:00), got {tl.reference_time!r}") from None


def set_reference(tl: Timelines, when: datetime) -> None:
    tl.reference_time = when.replace(microsecond=0).isoformat()


def clock(tl: Timelines, t: float) -> datetime:
    return reference(tl) + timedelta(seconds=float(t))


def format_clock(tl: Timelines, t: float) -> str:
    """The date and time at playback time *t* in the chosen display format."""
    when = clock(tl, t)
    if tl.display_format == "iso8601":
        return when.strftime("%Y-%m-%d %H:%M:%S")
    return when.strftime("%x %X")                   # regional: follows the operating system's locale


def format_elapsed(t: float) -> str:
    """``minutes:seconds`` as in the status bar (negative times keep their sign)."""
    sign = "-" if t < 0 else ""
    m, s = divmod(abs(t), 60.0)
    return f"{sign}{int(m)}:{s:04.1f}"


def overlay_text(tl: Timelines, mode: str, t: float) -> str:
    if mode == "none":
        return ""
    if mode == "date_time":
        return format_clock(tl, t)
    if mode == "time":
        return format_elapsed(t)
    raise ValueError("time display must be none, time or date_time")


def view_range(tl: Timelines, active_times: Optional[Tuple[float, float]], tour_range: Optional[Tuple[float, float]]
               ) -> Tuple[float, float]:
    """The global time range the slider covers: custom, else the active tour, else the union of active results."""
    if tl.view_timeline == "custom":
        if tl.end <= tl.begin:
            raise ValueError("a custom timeline needs End Time after Begin Time")
        return tl.begin, tl.end
    if tour_range is not None:
        return tour_range
    if active_times is not None:
        return active_times
    return (0.0, 0.0)


def check(tl: Timelines) -> list:
    out = []
    try:
        reference(tl)
    except ValueError as exc:
        out.append(str(exc))
    if tl.display_format not in ("regional", "iso8601"):
        out.append("display format must be regional or iso8601")
    if tl.view_timeline not in ("automatic", "custom"):
        out.append("view timeline must be automatic or custom")
    return out
