"""
PyFDS Result Plotters
=====================
Matplotlib-based visualisation helpers for FDS post-processing data.

All functions return ``matplotlib.figure.Figure`` objects so callers can
embed them in GUIs, save to disk, or further customise.  Matplotlib is
treated as an optional dependency — import errors produce a clear message.

Functions
---------
plot_device_timeseries   — line chart of one or more device channels
plot_hrr                 — HRR vs time convenience wrapper
plot_slice_contour       — filled 2-D contour plot of a slice frame
plot_multi_quantity      — grid of subplots, one per Plot3D quantity
plot_particle_positions  — 3-D scatter of particle positions at one frame
animate_slice            — animated contour over all time frames
animate_particles        — animated particle scatter over all time frames

Usage::

    from pyfds.results.plotters import plot_device_timeseries, animate_slice
    from pyfds.results.reader import DeviceReader

    results = DeviceReader.read("case_devc.csv")
    fig = plot_device_timeseries(results, ["tc01", "tc02"], title="Thermocouples")
    fig.savefig("tc_plot.png", dpi=150)

    anim = animate_slice(slice_result, interval=200)
    anim.save("slice.mp4", dpi=100)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


def _get_plt():
    """Lazy-import matplotlib.pyplot with a helpful error on missing install."""
    try:
        import matplotlib.pyplot as plt
        return plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for plotting. "
            "Install it with: pip install matplotlib"
        ) from exc


def _get_figure(figsize):
    plt = _get_plt()
    fig, ax = plt.subplots(figsize=figsize)
    return fig, ax


# ---------------------------------------------------------------------------
# Device time-series
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Slice contour plot
# ---------------------------------------------------------------------------

def plot_slice_contour(
    reader_result: Any,
    frame_index: int = -1,
    *,
    title: Optional[str] = None,
    cmap: str = "hot",
    figsize: Tuple[float, float] = (8, 6),
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    colorbar: bool = True,
) -> Any:
    """
    Filled contour plot of one frame from a ``SliceReader.read()`` result.

    The slice plane orientation is inferred automatically: the dimension
    with size 1 is collapsed and the remaining two are plotted.

    Parameters
    ----------
    reader_result : ReaderResult
        Returned by ``SliceReader.read()``.
    frame_index : int
        Which time frame to plot (default: last frame).
    title : str, optional
        Plot title. Defaults to ``<quantity> @ t=<time>s``.
    cmap : str
        Matplotlib colormap name.
    figsize : (width, height)
        Figure size in inches.
    vmin, vmax : float, optional
        Colour-scale limits. If None, derived from data.
    colorbar : bool
        Whether to draw a colour bar.

    Returns
    -------
    matplotlib.figure.Figure
    """
    plt = _get_plt()
    fig, ax = plt.subplots(figsize=figsize)

    data3d = reader_result.data      # shape (n_frames, ni, nj, nk)
    times  = reader_result.times

    if data3d is None or data3d.size == 0:
        ax.set_title("No data")
        return fig

    frame = data3d[frame_index]       # shape (ni, nj, nk)
    t_val = float(times[frame_index]) if times is not None and len(times) > 0 else 0.0

    # Squeeze out the singleton dimension to get a 2-D array
    squeeze_dims = [i for i, s in enumerate(frame.shape) if s == 1]
    if squeeze_dims:
        frame2d = np.squeeze(frame, axis=tuple(squeeze_dims))
    else:
        # No singleton dim — take a mid-slice along last axis
        frame2d = frame[:, :, frame.shape[2] // 2]

    # Ensure 2-D
    if frame2d.ndim != 2:
        frame2d = frame2d.reshape(frame2d.shape[0], -1)

    cf = ax.contourf(frame2d.T, cmap=cmap, vmin=vmin, vmax=vmax, levels=20)
    if colorbar:
        cb = fig.colorbar(cf, ax=ax)
        cb.set_label(reader_result.units or "")

    qty = reader_result.quantity or "Quantity"
    ax.set_title(title or f"{qty} @ t={t_val:.1f}s")
    ax.set_xlabel("i-index")
    ax.set_ylabel("j-index")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Plot3D multi-quantity grid
# ---------------------------------------------------------------------------

def plot_multi_quantity(
    plot3d_result: Any,
    frame_index: int = -1,
    *,
    slice_axis: int = 2,
    slice_position: Optional[int] = None,
    cmap: str = "viridis",
    figsize: Optional[Tuple[float, float]] = None,
) -> Any:
    """
    Grid of subplot contour plots — one per quantity in a ``Plot3DResult``.

    Parameters
    ----------
    plot3d_result : Plot3DResult
        Returned by ``Plot3DReader.read()``.
    frame_index : int
        Time frame to visualise.
    slice_axis : int
        Axis to slice through (0=i, 1=j, 2=k).
    slice_position : int, optional
        Index along *slice_axis*. Defaults to the midpoint.
    cmap : str
        Matplotlib colormap.
    figsize : (width, height), optional
        Defaults to auto-sized based on n_quantities.

    Returns
    -------
    matplotlib.figure.Figure
    """
    plt = _get_plt()
    n_qty = plot3d_result.n_quantities
    if n_qty == 0:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.set_title("No quantities")
        return fig

    ncols = min(n_qty, 3)
    nrows = (n_qty + ncols - 1) // ncols
    if figsize is None:
        figsize = (5 * ncols, 4 * nrows)

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)

    frame = plot3d_result.data[frame_index]   # (n_qty, ni, nj, nk)
    t_val = float(plot3d_result.times[frame_index])

    for qi in range(n_qty):
        row, col = divmod(qi, ncols)
        ax = axes[row][col]
        vol = frame[qi]                       # (ni, nj, nk)

        sp = slice_position if slice_position is not None else vol.shape[slice_axis] // 2
        sl: List[Any] = [slice(None)] * 3
        sl[slice_axis] = sp
        plane = vol[tuple(sl)]                # 2-D

        cf = ax.contourf(plane.T, cmap=cmap, levels=16)
        fig.colorbar(cf, ax=ax, fraction=0.046, pad=0.04)
        ax.set_title(f"{plot3d_result.quantities[qi]}\nt={t_val:.1f}s")
        ax.set_xlabel("axis-a")
        ax.set_ylabel("axis-b")

    # Hide unused subplots
    for qi in range(n_qty, nrows * ncols):
        row, col = divmod(qi, ncols)
        axes[row][col].set_visible(False)

    fig.suptitle(f"Plot3D — {plot3d_result.source_file}", fontsize=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Particle positions scatter
# ---------------------------------------------------------------------------

def plot_particle_positions(
    particle_class: Any,
    frame_index: int = -1,
    *,
    color_quantity: Optional[str] = None,
    cmap: str = "plasma",
    title: Optional[str] = None,
    figsize: Tuple[float, float] = (8, 6),
    markersize: float = 3.0,
) -> Any:
    """
    2-D scatter plot of particle X-Y positions at one time frame.

    Parameters
    ----------
    particle_class : ParticleClass
        One entry from ``ParticleResult.classes``.
    frame_index : int
        Which time frame to plot.
    color_quantity : str, optional
        Name of a scalar quantity to use for colour-coding particles.
        If None, all particles use the same colour.
    cmap : str
        Colormap used when *color_quantity* is set.
    title : str, optional
    figsize : (width, height)
    markersize : float
        Scatter marker size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    plt = _get_plt()
    fig, ax = plt.subplots(figsize=figsize)

    frames = particle_class.frames
    if not frames:
        ax.set_title(title or f"{particle_class.name} (no frames)")
        return fig

    frame = frames[frame_index]
    if frame.n_particles == 0:
        ax.set_title(title or f"{particle_class.name} @ t={frame.time:.1f}s (empty)")
        return fig

    x = frame.positions[:, 0]
    y = frame.positions[:, 1]

    sc_kw: Dict[str, Any] = {"s": markersize ** 2, "alpha": 0.7}
    if color_quantity and color_quantity in frame.quantities:
        c_data = frame.quantities[color_quantity]
        sc = ax.scatter(x, y, c=c_data, cmap=cmap, **sc_kw)
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label(color_quantity)
    else:
        ax.scatter(x, y, **sc_kw)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title(title or f"{particle_class.name} @ t={frame.time:.1f}s  "
                          f"n={frame.n_particles}")
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Slice animation
# ---------------------------------------------------------------------------

def animate_slice(
    reader_result: Any,
    *,
    interval: int = 100,
    cmap: str = "hot",
    figsize: Tuple[float, float] = (8, 6),
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    repeat: bool = True,
) -> Any:
    """
    Animated contour plot cycling through all time frames in a slice result.

    Parameters
    ----------
    reader_result : ReaderResult
        Returned by ``SliceReader.read()``.
    interval : int
        Delay between frames in milliseconds.
    cmap : str
        Matplotlib colormap.
    figsize : (width, height)
    vmin, vmax : float, optional
        Fixed colour-scale limits.  If None, derived from the full dataset.
    repeat : bool
        Whether the animation loops.

    Returns
    -------
    matplotlib.animation.FuncAnimation
        Call ``.save("out.mp4")`` or ``.save("out.gif")`` to export.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
    except ImportError as exc:
        raise ImportError("matplotlib is required. Install with: pip install matplotlib") from exc

    data3d = reader_result.data   # (n_frames, ni, nj, nk)
    times  = reader_result.times

    if data3d is None or data3d.size == 0:
        raise ValueError("animate_slice: no data in reader_result")

    n_frames = data3d.shape[0]

    # Determine colour scale from full dataset
    global_vmin = float(np.nanmin(data3d)) if vmin is None else vmin
    global_vmax = float(np.nanmax(data3d)) if vmax is None else vmax

    def _to_2d(frame):
        squeeze_dims = [i for i, s in enumerate(frame.shape) if s == 1]
        if squeeze_dims:
            f2d = np.squeeze(frame, axis=tuple(squeeze_dims))
        else:
            f2d = frame[:, :, frame.shape[2] // 2]
        return f2d.reshape(f2d.shape[0], -1) if f2d.ndim != 2 else f2d

    fig, ax = plt.subplots(figsize=figsize)
    first = _to_2d(data3d[0])
    cf = ax.contourf(first.T, cmap=cmap, vmin=global_vmin, vmax=global_vmax, levels=20)
    cbar = fig.colorbar(cf, ax=ax)
    cbar.set_label(reader_result.units or "")
    qty = reader_result.quantity or "Quantity"
    title_obj = ax.set_title(f"{qty} @ t=0.0s")
    ax.set_xlabel("i-index")
    ax.set_ylabel("j-index")
    fig.tight_layout()

    def _update(frame_idx):
        ax.cla()
        f2d = _to_2d(data3d[frame_idx])
        ax.contourf(f2d.T, cmap=cmap, vmin=global_vmin, vmax=global_vmax, levels=20)
        t_val = float(times[frame_idx]) if times is not None and len(times) > frame_idx else 0.0
        ax.set_title(f"{qty} @ t={t_val:.1f}s")
        ax.set_xlabel("i-index")
        ax.set_ylabel("j-index")
        return []

    anim = animation.FuncAnimation(
        fig, _update, frames=n_frames,
        interval=interval, blit=False, repeat=repeat,
    )
    return anim


# ---------------------------------------------------------------------------
# Particle animation
# ---------------------------------------------------------------------------

def animate_particles(
    particle_class: Any,
    *,
    interval: int = 100,
    color_quantity: Optional[str] = None,
    cmap: str = "plasma",
    figsize: Tuple[float, float] = (8, 6),
    markersize: float = 3.0,
    xlim: Optional[Tuple[float, float]] = None,
    ylim: Optional[Tuple[float, float]] = None,
    repeat: bool = True,
) -> Any:
    """
    Animated scatter plot cycling through all particle frames.

    Parameters
    ----------
    particle_class : ParticleClass
        One entry from ``ParticleResult.classes``.
    interval : int
        Delay between frames in milliseconds.
    color_quantity : str, optional
        Quantity name to use for colour-coding.
    cmap : str
        Colormap for colour-coded scatter.
    figsize : (width, height)
    markersize : float
    xlim, ylim : (lo, hi), optional
        Fixed axis limits.  If None, auto-ranged from the first frame.
    repeat : bool
        Whether the animation loops.

    Returns
    -------
    matplotlib.animation.FuncAnimation
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
    except ImportError as exc:
        raise ImportError("matplotlib is required. Install with: pip install matplotlib") from exc

    frames = particle_class.frames
    if not frames:
        raise ValueError("animate_particles: particle_class has no frames")

    fig, ax = plt.subplots(figsize=figsize)

    # Determine axis limits from all frames if not given
    if xlim is None or ylim is None:
        all_x, all_y = [], []
        for fr in frames:
            if fr.n_particles > 0:
                all_x.extend(fr.positions[:, 0].tolist())
                all_y.extend(fr.positions[:, 1].tolist())
        if all_x:
            xlim = xlim or (min(all_x), max(all_x))
            ylim = ylim or (min(all_y), max(all_y))
        else:
            xlim = xlim or (0.0, 1.0)
            ylim = ylim or (0.0, 1.0)

    scat = ax.scatter([], [], s=markersize**2, alpha=0.7)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    title_obj = ax.set_title(f"{particle_class.name}")
    fig.tight_layout()

    def _update(frame_idx):
        fr = frames[frame_idx]
        if fr.n_particles > 0:
            xy = fr.positions[:, :2]
            scat.set_offsets(xy)
            if color_quantity and color_quantity in fr.quantities:
                scat.set_array(fr.quantities[color_quantity])
                scat.set_cmap(cmap)
        else:
            scat.set_offsets(np.empty((0, 2)))
        title_obj.set_text(
            f"{particle_class.name} @ t={fr.time:.1f}s  n={fr.n_particles}"
        )
        return scat, title_obj

    anim = animation.FuncAnimation(
        fig, _update, frames=len(frames),
        interval=interval, blit=True, repeat=repeat,
    )
    return anim


# ---------------------------------------------------------------------------
# Interactive time-series with slider
# ---------------------------------------------------------------------------

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
