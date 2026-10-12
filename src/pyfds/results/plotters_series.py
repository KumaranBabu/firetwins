"""Time-series plots: devices, HRR, interactive."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .plotters_common import _get_figure, _get_plt

logger = logging.getLogger(__name__)


def plot_device_timeseries(
    results: Dict[str, Any],
    device_names: Optional[Sequence[str]] = None,
    *,
    title: str = "Device Time-Series",
    xlabel: str = "Time (s)",
    ylabel: str = "",
    figsize: Tuple[float, float] = (10, 5),
    colors: Optional[Sequence[str]] = None,
    linestyles: Optional[Sequence[str]] = None,
) -> Any:
    """
    Plot device output time-series from a ``DeviceReader.read()`` result dict.

    Parameters
    ----------
    results : dict
        Mapping of ``device_name → ReaderResult`` as returned by
        ``DeviceReader.read()``.
    device_names : list[str], optional
        Which devices to plot. If None, all devices except "Time" are plotted.
    title : str
        Plot title.
    xlabel, ylabel : str
        Axis labels.
    figsize : (width, height)
        Figure size in inches.
    colors, linestyles : sequences, optional
        Cycle through these for each plotted line.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = _get_figure(figsize)

    # Determine which keys to plot
    if device_names is None:
        device_names = [k for k in results if k.lower() != "time"]

    _colors     = list(colors)     if colors     else None
    _linestyles = list(linestyles) if linestyles else ["-", "--", "-.", ":"]

    for i, name in enumerate(device_names):
        if name not in results:
            logger.warning("plotters: device %r not in results — skipped", name)
            continue
        rr = results[name]
        times = rr.times if rr.times is not None else np.arange(len(rr.data))
        data  = rr.data  if rr.data  is not None else rr.times
        kw: Dict[str, Any] = {"label": name, "linestyle": _linestyles[i % len(_linestyles)]}
        if _colors:
            kw["color"] = _colors[i % len(_colors)]
        ax.plot(times, data, **kw)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    elif device_names:
        first = results.get(device_names[0])
        if first and first.units:
            ax.set_ylabel(first.units)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_hrr(
    results: Dict[str, Any],
    hrr_key: str = "HRR",
    *,
    title: str = "Heat Release Rate",
    figsize: Tuple[float, float] = (10, 4),
) -> Any:
    """
    Convenience wrapper: plot the HRR channel from a device results dict.

    Tries *hrr_key* first; falls back to any key containing "HRR".
    """
    actual_key = hrr_key if hrr_key in results else next(
        (k for k in results if "HRR" in k.upper()), None
    )
    if actual_key is None:
        logger.warning("plotters.plot_hrr: no HRR channel found in results")
        fig, ax = _get_figure(figsize)
        ax.set_title(title + " (no data)")
        return fig

    return plot_device_timeseries(
        results,
        device_names=[actual_key],
        title=title,
        ylabel="kW",
        figsize=figsize,
    )


def plot_timeseries_interactive(
    results: Dict[str, Any],
    device_names: Optional[Sequence[str]] = None,
    *,
    title: str = "Interactive Device Time-Series",
    figsize: Tuple[float, float] = (11, 6),
) -> Any:
    """
    Device time-series with t-start / t-end sliders for interactive exploration.

    Two ``matplotlib.widgets.Slider`` widgets below the axes control the visible
    time window.  Call ``plt.show()`` after this function to activate interaction.

    Parameters
    ----------
    results : dict
        ``device_name → ReaderResult`` mapping from ``DeviceReader.read()``.
    device_names : list[str], optional
        Channels to plot.  Defaults to all non-Time channels.
    title : str
        Figure title.
    figsize : (width, height)

    Returns
    -------
    matplotlib.figure.Figure
    """
    plt = _get_plt()
    try:
        from matplotlib.widgets import Slider
    except ImportError as exc:
        raise ImportError("matplotlib is required. Install with: pip install matplotlib") from exc

    if device_names is None:
        device_names = [k for k in results if k.lower() != "time"]

    series = []
    all_times: List[float] = []
    for name in device_names:
        if name not in results:
            logger.warning("plot_timeseries_interactive: %r not in results — skipped", name)
            continue
        rr = results[name]
        t = rr.times if rr.times is not None else np.arange(len(rr.data))
        series.append((name, t, rr.data))
        all_times.extend(t.tolist() if hasattr(t, "tolist") else list(t))

    if not series:
        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title("No data")
        return fig

    t_min = float(np.min(all_times))
    t_max = float(np.max(all_times))

    fig, ax = plt.subplots(figsize=figsize)
    plt.subplots_adjust(bottom=0.22)

    for name, t, data in series:
        ax.plot(t, data, label=name)

    ax.set_xlim(t_min, t_max)
    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    ax_t0 = plt.axes([0.15, 0.11, 0.65, 0.03])
    ax_t1 = plt.axes([0.15, 0.05, 0.65, 0.03])
    s_t0 = Slider(ax_t0, "t start", t_min, t_max, valinit=t_min)
    s_t1 = Slider(ax_t1, "t end",   t_min, t_max, valinit=t_max)

    def _update(_val: Any) -> None:
        lo = min(s_t0.val, s_t1.val)
        hi = max(s_t0.val, s_t1.val)
        if hi <= lo:
            hi = lo + 1e-9
        ax.set_xlim(lo, hi)
        fig.canvas.draw_idle()

    s_t0.on_changed(_update)
    s_t1.on_changed(_update)

    # Keep slider refs alive (prevent GC from destroying callbacks)
    fig._pyfds_sliders = (s_t0, s_t1)

    return fig
