"""Results-viewer data tools: views / tours / section boxes, floors, annotations, capture planning, CSV loading, (part 2 of 2)."""


from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from pyfds.results.viz import annotations as an
from pyfds.results.viz import capture as cap
from pyfds.results.viz import csvload as cl
from pyfds.results.viz import data3d as d3
from pyfds.results.viz import floors as fl
from pyfds.results.viz import model as vm
from pyfds.results.viz import timelines as tm
from pyfds.results.viz import views as vw
from pyfds.results.viz.primitives import RectilinearVolume

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


# -- Data3D ----------------------------------------------------------------------------------------------------
def sphere_volume(n=31, r=0.7):
    ax = np.linspace(-1, 1, n)
    X, Y, Z = np.meshgrid(ax, ax, ax, indexing="ij")
    return RectilinearVolume("v", "DIST", "m", ax, ax, ax, np.sqrt(X ** 2 + Y ** 2 + Z ** 2))


# -- timelines ---------------------------------------------------------------------------------------------------
def test_timelines_and_time_display():
    tl = vm.Timelines(reference_time="2018-06-03T15:47:00", display_format="iso8601")
    assert tm.format_clock(tl, 90) == "2018-06-03 15:48:30"
    assert tm.format_elapsed(125.5) == "2:05.5" and tm.format_elapsed(-3.0) == "-0:03.0"
    assert tm.overlay_text(tl, "none", 5) == "" and tm.overlay_text(tl, "time", 61) == "1:01.0"
    assert tm.overlay_text(tl, "date_time", 0).startswith("2018-06-03 15:47")
    tm.set_reference(tl, datetime(2003, 3, 23, 15, 0, 0))
    assert tl.reference_time == "2003-03-23T15:00:00"
    assert tm.view_range(tl, (0, 20), None) == (0, 20) and tm.view_range(tl, (0, 20), (5, 9)) == (5, 9)
    tl.view_timeline, tl.begin, tl.end = "custom", 2, 8
    assert tm.view_range(tl, (0, 20), (5, 9)) == (2, 8)
    tl.end = 1
    with pytest.raises(ValueError):
        tm.view_range(tl, None, None)
    assert tm.check(vm.Timelines(reference_time="soon", display_format="x", view_timeline="y")) and not tm.check(vm.Timelines())
    with pytest.raises(ValueError):
        tm.overlay_text(vm.Timelines(), "weird", 1)

def test_data3d_points_and_slices():
    v = sphere_volume()
    assert d3.sample_point(v, (0.5, 0, 0)) == pytest.approx(0.5, abs=0.01)
    assert math.isnan(d3.sample_point(v, (5, 0, 0))) and d3.inside(v, (0, 0, 0)) and not d3.inside(v, (2, 0, 0))
    assert d3.point_series([v, v], (0, 0, 0.3)).shape == (2,)
    with pytest.raises(ValueError):
        d3.sample_point(v, (0, 0))
    s = d3.slice_plane(v, (0, 0, 0), (0, 0, 1))
    assert s.axis == "z" and s.position == 0.0 and np.nanmin(s.values) < 0.05 and np.nanmax(s.values) > 1.2
    tilted = d3.slice_plane(v, (0, 0, 0), (1, 1, 1))
    assert tilted.axis is None and np.isfinite(tilted.values).any()
    assert d3.slice_plane(v, (0, 0, 5), (0, 0, 1)) is None
    with pytest.raises(ValueError):
        d3.slice_plane(v, (0, 0, 0), (0, 0, 0))

def test_isosurface_of_a_sphere_has_the_right_area_and_radius():
    v = sphere_volume(n=41)
    m = d3.isosurface(v, 0.7)
    assert len(m.faces) > 500 and m.level == 0.7
    r = np.linalg.norm(m.vertices, axis=1)
    assert r.min() > 0.67 and r.max() < 0.73
    tri = m.vertices[m.faces]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum()
    assert area == pytest.approx(4 * math.pi * 0.7 ** 2, rel=0.03)
    assert len(d3.isosurface(v, 99.0).faces) == 0 and len(d3.isosurface(v, -1.0).faces) == 0

def test_isosurface_on_the_real_fire_volume():
    from pyfds.results.viz.dataset import ResultsDataset
    from pyfds.results.viz.fds_run import parse_smv
    from pyfds.results.viz.tree import build_tree
    run = parse_smv(str(FIX / "rroom.smv"))
    viz = vm.ResultsVisualization()
    root = build_tree(run, viz)
    leaf = root.find("root/FDS Results/3D Slices/TEMPERATURE/T_3D/Mesh 1")
    (vol,) = ResultsDataset(run, viz, use_cache=False).primitives(leaf, 6.0)
    m = d3.isosurface(vol, 100.0)
    assert len(m.faces) > 50 and m.vertices[:, 2].min() >= 0 and m.vertices[:, 0].max() <= 1.5 + 1e-9
