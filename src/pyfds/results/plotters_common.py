"""matplotlib access helpers for the plotters."""
from __future__ import annotations


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
