"""Field plots: slice contours, multi-quantity, particle positions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .plotters_common import _get_plt


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
