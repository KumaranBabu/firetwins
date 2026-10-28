"""V11: Preferences > Rendering has real effects (renderer options, disabled renderers, level of detail, frame cache)."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pyvista as pv
import pytest

from pyfds.api.facade import FdsApi
from pyfds.api import viz
from pyfds.gui.results import quality
from pyfds.gui.results.scene_adapter import SceneAdapter

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
R = "root/FDS Results/"
SL = R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"


@pytest.fixture()
def v(tmp_path):
    shutil.copytree(FIX, tmp_path / "r")
    api = FdsApi()
    api.viewer.open_results(str(tmp_path / "r" / "rroom.smv"))
    return api.viewer


def test_disabled_data3d_renderers_hide_those_results(v):
    g = R + "3D Slices/TEMPERATURE"
    v.activate(R + "3D Slices/TEMPERATURE/T_3D/Mesh 1")
    v.add_data3d_isosurface(g, 100.0)
    leaf = next(l for l in v.tree.leaves() if l.kind == "data3d_iso")
    v.activate(leaf.id)
    assert v.frame(5.0).of_kind("data3d_iso")
    v.set_rendering(data3d_renderer="disabled")
    assert not v.frame(5.0).of_kind("data3d_iso")
    v.set_rendering(data3d_renderer="hardware")
    assert v.frame(5.0).of_kind("data3d_iso")


def test_level_of_detail_thins_big_volumes():
    from pyfds.results.viz import transform as xf
    ax = np.linspace(0, 1, 120)
    vol = viz.RectilinearVolume("v", "Q", "u", ax, ax, ax, np.random.rand(120, 120, 120))
    small = xf.thin_volume(vol, max_nodes=400_000)
    assert small.values.size <= 400_000 and small.values.shape == (small.x.size, small.y.size, small.z.size)
    assert xf.thin_volume(vol, max_nodes=10 ** 9) is vol


def test_frame_cache_and_invalidation(v):
    v.activate(SL)
    n = v.cache_frames()
    assert n > 3 and len(v._pcache) >= n
    a = v.frame(2.0).items[0][1]
    assert v.frame(2.0).items[0][1] is a                      # served from memory
    v.set_units(temperature="F")
    assert v.frame(2.0).items[0][1] is not a                  # a setting changed: recomputed
    seen = []
    assert v.cache_frames(progress=lambda d, t: seen.append(d) or d < 2) == 2


def test_async_prefetch_runs_only_when_enabled(v):
    v.activate(SL)
    assert v.playback is not None
    v._pcache.clear()
    th = v.prefetch_async(4)
    th.join(30)
    assert len(v._pcache) == 4
    v.set_rendering(async_frames=False)
    assert v.prefetch_async(4) is None


def test_quality_options_reach_the_plotter():
    pl = pv.Plotter(off_screen=True, window_size=(120, 80))
    prefs = viz.model.RenderingPreferences()
    assert quality.apply_quality(pl, prefs)["antialiasing"] == "fxaa"
    prefs.antialiasing = "msaa_4"
    assert quality.apply_quality(pl, prefs)["antialiasing"] == "msaa_4"
    prefs.antialiasing = "disabled"
    assert quality.apply_quality(pl, prefs)["antialiasing"] == "disabled"
    assert quality.volume_mapper(viz.model.RenderingPreferences(smoke_renderer="compatibility")) == "fixed_point"
    assert quality.volume_mapper(prefs) == "smart"
    pl.close()


def test_max_compatibility_and_smoke_render_in_both_modes(v, tmp_path):
    v.activate(R + "3D Smoke/SOOT DENSITY/Mesh 1")
    v.activate(SL)
    for preset in ("max_quality", "max_compatibility"):
        v.set_rendering(preset=preset)
        pl = pv.Plotter(off_screen=True, window_size=(200, 140))
        ad = SceneAdapter(pl)
        assert ad.draw(v.frame(4.0), v.viz) >= 2
        assert ad.quality["antialiasing"] in ("msaa_16", "msaa_4", "unsupported", "disabled")
        pl.close()
    assert set(quality.APPLIED) == set(viz.model.RenderingPreferences.__dataclass_fields__)


def test_software_smoke_renderer_samples_at_the_cell_size():
    """The software volume mapper defaults to one sample per world unit (ten 0.1 m cells), which draws 3D smoke as
    large triangles; it must step at the grid spacing."""
    pl = pv.Plotter(off_screen=True)
    try:
        img = pv.ImageData(dimensions=(11, 11, 11), spacing=(0.1, 0.1, 0.1))
        img["a"] = np.linspace(0, 1, img.n_points)
        pl.add_volume(img, scalars="a", name="smoke", mapper="fixed_point", show_scalar_bar=False)
        SceneAdapter(pl)._jitter("smoke", viz.model.ResultsVisualization())
        assert pl.renderer.actors["smoke"].mapper.GetLockSampleDistanceToInputSpacing()
    finally:
        pl.close()
