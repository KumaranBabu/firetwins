"""api.viewer driven end-to-end against the real two-mesh FDS room-fire fixture."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from pyfds.api.facade import FdsApi
from pyfds.results.viz import model as vm

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
R = "root/FDS Results/"


@pytest.fixture()
def v(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(FIX, run)
    api = FdsApi()
    api.viewer.open_results(str(run / "rroom.smv"))
    return api.viewer


def test_open_results_builds_tree_and_default_path(v):
    assert v.run is not None and v.path.endswith("rroom.pyfdsv")
    assert v.node(R + "2D Slices").children
    with pytest.raises(KeyError):
        v.node("nope")


def test_activate_slice_and_frame(v):
    r = v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    assert r.activated
    assert len(v.timeline()) > 3
    fr = v.frame(3.0)
    assert fr.of_kind("slice2d") and fr.colorbars and fr.colorbars[0][0] == "TEMPERATURE"
    assert v.node_state(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1") != "off"


def test_geometry_and_sets(v):
    v.activate("geometry/fds_actual")
    assert v.frame(0.0).of_kind("geometry")
    with pytest.raises(ValueError):
        v.set_geometry_set("nonsense")
    v.set_rendering_mode("wireframe") if "wireframe" in vm.RENDER_MODES else None


def test_playback_survives_and_seek(v):
    v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    pb = v.playback
    assert pb is not None
    v.set_time(2.0)
    assert 1.5 <= v.time <= 2.5
    v.set_speed(4)
    assert v.playback.speed == 4
    with pytest.raises(ValueError):
        v.set_speed(0)


def test_colorbar_settings(v):
    v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    bar = v.colorbar("TEMPERATURE")
    assert bar.hi > bar.lo
    v.set_colorbar("TEMPERATURE", minimum=20.0, maximum=300.0, use_minimum=True, use_maximum=True) if \
        "use_minimum" in vm.ColorbarProps.__dataclass_fields__ else None
    with pytest.raises(AttributeError):
        v.set_colorbar("TEMPERATURE", bogus=1)
    with pytest.raises(KeyError):
        v.colorbar("NOT A QUANTITY")


def test_smoke_presets_and_validation(v):
    v.set_smoke3d(preset="fire_only") if "fire_only" in vm.SMOKE_PRESETS else None
    with pytest.raises(AttributeError):
        v.set_smoke3d(nonsense=1)


def test_save_and_reopen_keeps_settings_and_active(v, tmp_path):
    v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    v.set_units(temperature="F")
    out = v.save(str(tmp_path / "x.pyfdsv"))
    api2 = FdsApi()
    api2.viewer.open_visualization(out)
    assert api2.viewer.viz.units.temperature == "F"
    assert api2.viewer.active_leaves()
    assert api2.viewer.run is not None


def test_views_tours_and_section_box(v):
    v.new_view("Door")
    v.add_section_box()
    box = v.set_section_plane("x_min", 0.5)
    assert box.active()["x_min"] == 0.5
    v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    fr = v.frame(3.0)
    for _, s in fr.items:
        assert np.nanmin(s.x) >= 0.5 - 1e-6 if hasattr(s, "x") else True
    v.remove_section_box()
    t = v.new_tour("Orbit")
    v.add_keyframe(0.0)
    v.set_camera(vm.Viewpoint(position=(5, 5, 5)))
    v.add_keyframe(5.0)
    assert v.camera_for_time(2.5).position != (5, 5, 5)
    with pytest.raises(ValueError):
        v.set_keyframe(0, view="Door", transition="stationary")
    v.activate_view(None)


def test_standard_views(v):
    for n in ("top", "front", "side", "isometric"):
        vp = v.standard_view(n)
        assert vp.position != vp.target
    with pytest.raises(ValueError):
        v.standard_view("bottom")
    with pytest.raises(ValueError):
        v.set_projection("fisheye")
    v.set_projection("orthogonal")
    with pytest.raises(ValueError):
        v.set_navigation("roam")


def test_floors_and_annotations(v):
    v.set_floors([0.0, 1.5])
    with pytest.raises(ValueError):
        v.set_floor_layout(layout="diagonal")
    v.set_floor_layout(layout="horizontal", separation=1.0)
    v.activate("geometry/fds_actual")
    fr = v.frame(0.0)
    assert fr.items
    v.add_dimension((0, 0, 0), (1.5, 0, 0))
    v.add_label("Fire", (1, 1, 0))
    assert v.dimension_geometry(0).value == pytest.approx(1.5)
    v.remove_annotation("label", 0)


def test_data3d_objects(v):
    group = R + "3D Slices/TEMPERATURE"
    v.activate(R + "3D Slices/TEMPERATURE/T_3D/Mesh 1")
    p = v.add_data3d_point(group, (0.5, 1.0, 1.0))
    s = v.add_data3d_slice(group, (0.5, 1.0, 1.0), (0, 0, 1))
    i = v.add_data3d_isosurface(group, 100.0)
    t, vals = v.point_series(p.id)
    assert len(t) == len(vals) > 3
    leaf = next(l for l in v.tree.leaves() if l.kind == "data3d_slice")
    v.activate(leaf.id)
    assert v.frame(3.0).of_kind("data3d_slice")
    with pytest.raises(ValueError):
        v.add_data3d_point(group, (99, 99, 99))
    v.remove_data3d(i.id)
    with pytest.raises(KeyError):
        v.remove_data3d("Isosurface 77")


def test_csv_and_export(v, tmp_path):
    data = v.load_csv(str(v.run.directory / "rroom_hrr.csv"))
    ids = list(v.csv_series())
    assert any("HRR" in i for i in ids)
    hrr = next(i for i in ids if i.endswith("HRR"))
    n = v.export_data([hrr], str(tmp_path / "h.csv"))
    assert n > 3
    with pytest.raises(KeyError):
        v.time_history(["nope"])
    v.remove_csv(str(v.run.directory / "rroom_hrr.csv"))


def test_screenshots_and_movie_with_fake_renderer(v, tmp_path):
    v.activate(R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    calls = []

    def draw(path, size, t, view):
        calls.append((Path(path).name, t))
        Path(path).write_bytes(b"png")

    shots = v.screenshot_plan(str(tmp_path / "s" / "a.png"), "multiple", start=0, end=2, interval=1)
    assert len(v.render_screenshots(shots, draw)) == 3
    with pytest.raises(KeyError):
        v.render_screenshots(v.screenshot_plan(str(tmp_path / "b.png"), "single", view="ghost"), draw)
    from pyfds.results.viz import capture as cap
    plan = cap.movie_plan(str(tmp_path / "m.mp4"), 0, 1, fps=4)
    v.encode_frames = lambda *a, **k: 127              # pretend no encoder: frames must be kept
    res = v.render_movie(plan, draw)
    assert not res["encoded"] and Path(res["frames_dir"]).exists() and len(list(Path(res["frames_dir"]).glob("*.png"))) == 5


def test_refresh_and_unload(v):
    assert v.refresh()["reloaded"] in (True, False)
    v.unload_results()
    assert v.run is None and v.frame().items == []
