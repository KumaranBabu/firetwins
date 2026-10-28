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

from .plotters_common import (  # noqa: F401  (re-exported)
    _get_figure,
    _get_plt,
)
from .plotters_series import (  # noqa: F401  (re-exported)
    plot_device_timeseries,
    plot_hrr,
    plot_timeseries_interactive,
)
from .plotters_fields import (  # noqa: F401  (re-exported)
    plot_multi_quantity,
    plot_particle_positions,
    plot_slice_contour,
)
from .plotters_animate import (  # noqa: F401  (re-exported)
    animate_particles,
    animate_slice,
)



logger = logging.getLogger(__name__)
