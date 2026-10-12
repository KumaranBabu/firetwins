"""Playing a run must stay cheap: one render per redraw, time stamps read once, real time drives the clock."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyvista as pv

from pyfds.gui.results.scene_adapter import SceneAdapter
from pyfds.results.viz import streams

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


def test_draw_renders_nothing_itself_and_restores_the_flag():
    pl = pv.Plotter(off_screen=True)
    ad = SceneAdapter(pl)
    seen = []
    orig = pl.add_mesh
    pl.add_mesh = lambda *a, **k: (seen.append(pl.suppress_rendering), orig(*a, **k))[1]
    from pyfds.api.facade import FdsApi
    from pyfds.api.viewer import ViewerManager
    v = ViewerManager(FdsApi())
    ad.draw(v.frame(), v.viz)
    assert pl.suppress_rendering is False
    assert all(seen)                                  # every add_mesh inside draw ran with rendering suppressed
    pl.close()


def test_frame_times_are_cached_until_the_file_grows(monkeypatch):
    calls = []

    class S:
        n_records = 3

        def __init__(self):
            self.__dict__["x"] = 1

        @property
        @streams._times_cache
        def times(self):
            calls.append(1)
            return np.arange(self.n_records, dtype=float)

    s = S()
    assert list(s.times) == [0, 1, 2] and list(s.times) == [0, 1, 2]
    assert len(calls) == 1
    s.n_records = 5
    assert len(s.times) == 5 and len(calls) == 2
