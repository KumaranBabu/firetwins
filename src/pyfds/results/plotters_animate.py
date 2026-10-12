"""Animations: slices and particles."""
from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np


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
