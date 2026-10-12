"""Colorbars: turn a ``ColorbarProps`` and a data range into colours and opacities.

Pure NumPy + matplotlib colour maps. The 3D view builds its lookup tables from these, so what the
FDS Preferences dialog edits is exactly what is drawn, and tests can check it without a GPU.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .model import ColorbarProps

COLORMAPS = ["turbo", "jet", "rainbow", "viridis", "plasma", "inferno", "magma", "cividis", "hot", "coolwarm",
             "gray", "bone", "gist_heat", "Spectral_r", "RdYlBu_r", "gnuplot2"]


def known_colormap(name: str) -> bool:
    base = name[:-2] if name.endswith("_r") else name
    return base in COLORMAPS or name in COLORMAPS


def _round_nice(lo: float, hi: float) -> Tuple[float, float]:
    """Round a range outwards to 2 significant digits of its span (what 'rounded' presets mean)."""
    span = hi - lo
    if span <= 0:
        return lo, lo + 1.0
    step = 10 ** np.floor(np.log10(span / 10.0))
    return float(np.floor(lo / step) * step), float(np.ceil(hi / step) * step)


def data_range(props: ColorbarProps, stats) -> Tuple[float, float]:
    """The (minimum, maximum) mapped to the ends of the colormap for these statistics.

    *stats* has ``min``, ``max``, ``p1``, ``p99`` (the middle 98 % of all values over all time)."""
    mode = props.range_mode
    if mode == "custom":
        if props.minimum is None or props.maximum is None:
            raise ValueError("a custom range needs minimum and maximum")
        return float(props.minimum), float(props.maximum)
    if mode in ("percentile", "percentile_rounded"):
        lo, hi = stats.p1, stats.p99
    else:
        lo, hi = stats.min, stats.max
    if mode.endswith("rounded"):
        lo, hi = _round_nice(lo, hi)
    if hi <= lo:
        hi = lo + max(abs(lo) * 1e-6, 1e-9)
    return float(lo), float(hi)


class ColorbarModel:
    """Maps data values to RGBA for one quantity."""

    def __init__(self, props: ColorbarProps, lo: float, hi: float) -> None:
        bad = props.problems()
        if bad:
            raise ValueError("; ".join(bad))
        if not hi > lo:
            raise ValueError("the data range must have maximum > minimum")
        self.props, self.lo, self.hi = props, float(lo), float(hi)

    # -- colour table ------------------------------------------------------------------------
    def _base_colors(self, n: int) -> np.ndarray:
        p = self.props
        if p.color_source == "constant":
            rgb = np.array(_hex(p.color), dtype=float)
            return np.tile(rgb, (n, 1))
        from matplotlib import colormaps
        name = p.colormap
        cmap = colormaps[name] if name in colormaps else colormaps["turbo"]
        t = np.linspace(0.0, 1.0, n)
        if p.invert:
            t = t[::-1]
        return cmap(t)[:, :3]

    def table(self) -> np.ndarray:
        """``(n_colors, 4)`` RGBA table across the data range (colour and opacity, highlight applied)."""
        p = self.props
        n = p.n_colors
        rgb = self._base_colors(n)
        frac = (np.arange(n) + 0.5) / n
        a = self._opacity(frac)
        rgba = np.column_stack([rgb, a])
        if p.highlight_enabled and p.highlight_width > 0:
            vals = self.lo + frac * (self.hi - self.lo)
            hit = abs(vals - p.highlight_value) <= p.highlight_width / 2
            rgba[hit, :3] = _hex(p.highlight_color)
        return np.clip(rgba, 0.0, 1.0)

    def _opacity(self, frac: np.ndarray) -> np.ndarray:
        p = self.props
        if p.opacity_source == "constant":
            return np.full(frac.shape, p.opacity)
        if p.opacity_source == "gradient":
            return p.opacity_at_min + frac * (p.opacity_at_max - p.opacity_at_min)
        thr = max(p.feather_threshold, 1e-9)
        if p.opacity_source == "feather_below":
            return np.clip(frac / thr, 0.0, 1.0) * p.opacity
        return np.clip((1.0 - frac) / thr, 0.0, 1.0) * p.opacity            # feather_above

    # -- applying it ---------------------------------------------------------------------------
    def normalise(self, values: np.ndarray) -> np.ndarray:
        return np.clip((np.asarray(values, dtype=float) - self.lo) / (self.hi - self.lo), 0.0, 1.0)

    def rgba(self, values: np.ndarray) -> np.ndarray:
        """RGBA per value; values hidden by *truncate* get alpha 0, NaN stays transparent."""
        v = np.asarray(values, dtype=float)
        tab = self.table()
        idx = np.minimum((self.normalise(np.nan_to_num(v, nan=self.lo)) * len(tab)).astype(int), len(tab) - 1)
        out = tab[idx]
        hidden = np.isnan(v)
        if self.props.truncate:
            if self.props.hide_below is not None:
                hidden |= v < self.props.hide_below
            if self.props.hide_above is not None:
                hidden |= v > self.props.hide_above
        out[hidden, 3] = 0.0
        return out

    def ticks(self, n: int = 6) -> List[Tuple[float, str]]:
        vals = np.linspace(self.lo, self.hi, n)
        return [(float(v), f"{v:.4g}") for v in vals]


def _hex(color: str) -> Tuple[float, float, float]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"colour must be #rrggbb, got {color!r}")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))      # type: ignore[return-value]


def highlight_at(props: ColorbarProps, lo: float, hi: float, fraction: float, width_fraction: float = 0.05) -> None:
    """What clicking the colorbar does: a highlight region (5 % of the range by default) centred there."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    props.highlight_enabled = True
    props.highlight_value = lo + fraction * (hi - lo)
    props.highlight_width = width_fraction * (hi - lo)


def resize_highlight(props: ColorbarProps, lo: float, hi: float, steps: int) -> None:
    """Mouse wheel over the colorbar: grow (+) or shrink (-) the highlight, 1 % of the range per step."""
    if not props.highlight_enabled:
        return
    props.highlight_width = float(np.clip(props.highlight_width + steps * 0.01 * (hi - lo), 0.002 * (hi - lo), hi - lo))


def clear_highlight(props: ColorbarProps) -> None:
    props.highlight_enabled = False
