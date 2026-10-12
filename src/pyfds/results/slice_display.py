"""Slice display (RES-04): colour map, bounds and colour bar for slice planes, rendered to images.

``SliceDisplay`` holds the settings a colour-bar editor edits. ``render`` draws one frame of a slice
(``SliceReader.read`` result) as a coloured plane with its colour bar and writes a PNG; ``bounds``
gives the colour range, either of the frame or of ALL frames (so colours mean the same thing from
frame to frame - what you want for an animation). No pyplot: it draws on its own canvas, so it is
safe to call from a worker thread or inside a GUI.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, List, Optional, Tuple

import numpy as np

#: Colour maps offered in the editor (all ship with matplotlib)
COLORMAPS = ["turbo", "jet", "viridis", "plasma", "inferno", "magma", "cividis", "hot", "coolwarm",
             "rainbow", "gray", "bone"]
BOUND_MODES = ("all", "frame")

#: Starting colour map per quantity. Bounds are left to the data on purpose.
_QUANTITY_CMAP = {"TEMPERATURE": "turbo", "VISIBILITY": "turbo_r", "HRRPUV": "hot", "PRESSURE": "coolwarm",
                  "DENSITY": "viridis", "VELOCITY": "viridis", "VOLUME FRACTION": "plasma",
                  "MASS FRACTION": "plasma"}


@dataclass(frozen=True)
class SliceDisplay:
    colormap: str = "turbo"
    vmin: Optional[float] = None          # None = from the data
    vmax: Optional[float] = None
    levels: int = 20                      # number of colour steps
    colorbar: bool = True
    label: Optional[str] = None           # colour bar label; default "QUANTITY (units)"
    contour_lines: bool = False
    bounds_from: str = "all"              # "all" frames or this "frame"

    def problems(self) -> List[str]:
        out = []
        base = self.colormap[:-2] if self.colormap.endswith("_r") else self.colormap
        if base not in COLORMAPS:
            out.append(f"unknown colormap {self.colormap!r}; choose from {', '.join(COLORMAPS)} (add _r to reverse)")
        if self.vmin is not None and self.vmax is not None and not self.vmin < self.vmax:
            out.append("vmin must be smaller than vmax")
        if not isinstance(self.levels, int) or isinstance(self.levels, bool) or not 2 <= self.levels <= 256:
            out.append("levels must be a whole number from 2 to 256")
        if self.bounds_from not in BOUND_MODES:
            out.append(f"bounds_from must be one of {', '.join(BOUND_MODES)}")
        return out

    def checked(self) -> "SliceDisplay":
        bad = self.problems()
        if bad:
            raise ValueError("; ".join(bad))
        return self


def default_display(quantity: str) -> SliceDisplay:
    return SliceDisplay(colormap=_QUANTITY_CMAP.get((quantity or "").strip().upper(), "turbo"))


def _frames(result) -> np.ndarray:
    data = result.data
    if data is None or getattr(data, "size", 0) == 0 or len(result.times) == 0:
        raise ValueError("the slice has no data")
    return np.asarray(data)


def bounds(result, display: SliceDisplay, frame_index: int = -1) -> Tuple[float, float]:
    """The colour range: the user's vmin/vmax where set, else min/max over all frames or this frame."""
    display.checked()
    data = _frames(result)
    ref = data if display.bounds_from == "all" else data[frame_index]
    lo = float(np.nanmin(ref)) if display.vmin is None else display.vmin
    hi = float(np.nanmax(ref)) if display.vmax is None else display.vmax
    if hi <= lo:                                   # a flat field: widen so the bar is still drawn
        hi = lo + max(abs(lo) * 1e-6, 1e-9) if display.vmax is None else hi
        if hi <= lo:
            lo = hi - 1.0
    return lo, hi


def _plane(frame: np.ndarray, header, mesh) -> Tuple[np.ndarray, Tuple[float, float, float, float], str, str]:
    """2-D array (rows = vertical axis), its extent and axis labels."""
    shape = frame.shape
    singleton = [i for i, n in enumerate(shape) if n == 1]
    if not singleton:
        raise ValueError("this slice is a volume; pick a plane (one dimension of size 1)")
    drop = singleton[0]
    keep = [i for i in range(3) if i != drop]
    arr = np.squeeze(frame, axis=drop)                 # axes in `keep` order
    if mesh is not None and header is not None:
        lo = (mesh.x_min, mesh.y_min, mesh.z_min)
        hi = (mesh.x_max, mesh.y_max, mesh.z_max)
        n = mesh.cell_count
        idx = [(header.i1, header.i2), (header.j1, header.j2), (header.k1, header.k2)]
        ext = []
        for a in keep:
            step = (hi[a] - lo[a]) / n[a]
            ext += [lo[a] + idx[a][0] * step, lo[a] + idx[a][1] * step]
        labels = [f"{'xyz'[a]} (m)" for a in keep]
    else:
        ext = []
        for a in keep:
            ext += [0, shape[a] - 1]
        labels = [f"{'ijk'[a]} index" for a in keep]
    # imshow: rows = second kept axis (vertical), columns = first kept axis
    return arr.T, (ext[0], ext[1], ext[2], ext[3]), labels[0], labels[1]


def render(result, filepath: Optional[str], frame_index: int = -1, display: Optional[SliceDisplay] = None,
           mesh: Any = None, dpi: int = 100, size: Tuple[float, float] = (7.0, 5.5)):
    """Draw one frame to a PNG (or any matplotlib-supported extension) and return *filepath*;
    with ``filepath=None`` return the PNG as ``bytes`` instead (for a viewer that shows it on screen)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    display = (display or default_display(result.quantity)).checked()
    data = _frames(result)
    n = data.shape[0]
    if not -n <= frame_index < n:
        raise IndexError(f"frame {frame_index} out of range (the slice has {n} frames)")
    lo, hi = bounds(result, display, frame_index)
    header = (result.metadata or {}).get("header")
    arr, extent, xl, yl = _plane(data[frame_index], header, mesh)
    t = float(result.times[frame_index])

    fig = Figure(figsize=size, dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    from matplotlib import colormaps
    cmap = colormaps[display.colormap].resampled(display.levels)
    im = ax.imshow(arr, origin="lower", extent=extent, cmap=cmap, vmin=lo, vmax=hi, aspect="equal",
                   interpolation="nearest")
    if display.contour_lines:
        ax.contour(np.linspace(extent[0], extent[1], arr.shape[1]), np.linspace(extent[2], extent[3], arr.shape[0]),
                   arr, levels=np.linspace(lo, hi, display.levels + 1)[1:-1], colors="k", linewidths=0.4)
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    qty = result.quantity or "slice"
    ax.set_title(f"{qty}   t = {t:.1f} s")
    if display.colorbar:
        cb = fig.colorbar(im, ax=ax)
        cb.set_label(display.label if display.label is not None else
                     f"{qty} ({result.units})" if result.units else qty)
    fig.tight_layout()
    if filepath is None:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, dpi=dpi, format="png")
        return buf.getvalue()
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    fig.savefig(filepath, dpi=dpi)
    return filepath


def render_frames(result, outdir: str, prefix: str = "slice", frames: Optional[List[int]] = None,
                  display: Optional[SliceDisplay] = None, mesh: Any = None, dpi: int = 100) -> List[str]:
    """Render several frames (default all) to ``<outdir>/<prefix>_0000.png`` ... with ONE colour range."""
    display = (display or default_display(result.quantity)).checked()
    data = _frames(result)
    lo, hi = bounds(result, display)
    fixed = replace(display, vmin=lo, vmax=hi)
    idx = list(range(data.shape[0])) if frames is None else list(frames)
    return [render(result, os.path.join(outdir, f"{prefix}_{i % data.shape[0]:04d}.png"), i, fixed, mesh, dpi)
            for i in idx]
