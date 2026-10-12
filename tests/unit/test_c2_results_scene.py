"""C2 - renderer-agnostic results scene: layers from the readers, timeline, clip, probe, playback, camera."""
from __future__ import annotations

import struct

import numpy as np
import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.core.viewport import CameraPreset, ViewportCamera
from pyfds.results import scene as sc
from pyfds.results import transfer
from pyfds.results.particle_reader import ParticleClass, ParticleFrame
from pyfds.results.playback import CameraPath, Playback, SavedViews
from pyfds.results.reader import BoundaryFrame, BoundaryHeader, BoundaryPatch, ReaderResult, SliceHeader
from pyfds.results.scene_data import ClipPlane, GridSurface, PointCloud, TriMesh, VolumeGrid, clip
from pyfds.smokeview.binary import IsosurfaceFile, IsosurfaceFrame


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 8, 5), xb=(0, 10, 0, 8, 0, 5), name="M")
    return a


def _slice(times=(0.0, 5.0, 10.0), shape=(11, 1, 6), y_index=4, quantity="TEMPERATURE"):
    base = np.arange(np.prod(shape), dtype=float).reshape(shape)
    data = np.stack([base + 100 * k for k in range(len(times))])
    hdr = SliceHeader(quantity, "temp", "C", 0, shape[0] - 1, y_index, y_index, 0, shape[2] - 1)
    return ReaderResult("x.sf", quantity, "C", np.array(times), data, {"header": hdr})


# -- slice layer ---------------------------------------------------------------------------------
def test_slice_layer_places_plane_in_real_coordinates(api):
    layer = sc.SliceLayer("T", _slice(), api.meshes.get("M"))
    (g,) = layer.primitives(0)
    assert isinstance(g, GridSurface) and g.axis == "y" and g.position == pytest.approx(4.0)   # j=4 of 8 cells over 8 m
    assert g.x.shape == (11, 6) and g.x[0, 0] == 0 and g.x[-1, 0] == 10
    assert g.z[0, -1] == 5 and np.all(g.y == 4.0)
    assert g.values.shape == (11, 6) and g.values[1, 0] == 6.0


def test_slice_without_mesh_uses_indices():
    (g,) = sc.SliceLayer("T", _slice()).primitives(1)
    assert g.x[-1, 0] == 10 and g.position == 4.0


def test_volume_slice_becomes_volume_grid(api):
    shape = (10, 8, 5)
    hdr = SliceHeader("DENSITY", "d", "kg/m3", 0, 9, 0, 7, 0, 4)
    r = ReaderResult("v.sf", "DENSITY", "kg/m3", np.array([0.0]), np.ones((1,) + shape), {"header": hdr})
    layer = sc.SliceLayer("V", r, api.meshes.get("M"))
    assert layer.kind == "volume"
    (v,) = layer.primitives(0)
    assert isinstance(v, VolumeGrid) and v.values.shape == shape and v.spacing == pytest.approx((1.0, 1.0, 1.0), abs=0.2)


def test_slice_probe(api):
    layer = sc.SliceLayer("T", _slice(), api.meshes.get("M"))
    hit = layer.sample((2.0, 4.1, 3.0), 1)
    assert hit["value"] == 100 + 2 * 6 + 3 and hit["units"] == "C" and hit["time"] == 5.0
    assert layer.sample((2.0, 6.0, 3.0), 0) is None          # off the plane
    assert layer.sample((50.0, 4.0, 3.0), 0) is None         # outside the mesh


def test_empty_slice_is_refused():
    r = ReaderResult("e", "T")
    with pytest.raises(ValueError):
        sc.SliceLayer("e", r)


# -- boundary ------------------------------------------------------------------------------------
def test_boundary_layer_patches(api):
    hdr = BoundaryHeader("WALL TEMPERATURE", "wt", "C", 2)
    patches = [BoundaryPatch(0, 0, 0, 8, 0, 5, 1), BoundaryPatch(0, 10, 0, 0, 0, 5, 1)]
    frames = [BoundaryFrame(t, [np.arange(9 * 6, dtype=float) + t, np.arange(11 * 6, dtype=float)]) for t in (0.0, 1.0)]
    layer = sc.BoundaryLayer("B", hdr, patches, frames, [api.meshes.get("M")])
    p0, p1 = layer.primitives(1)
    assert p0.axis == "x" and p0.position == 0 and p0.values.shape == (9, 6) and p0.values[0, 0] == 1.0
    assert p1.axis == "y" and p1.x[-1, 0] == 10
    assert layer.value_range() == (0.0, 66.0 - 1 + 0)
    bad = sc.BoundaryLayer("X", hdr, [BoundaryPatch(0, 3, 0, 3, 0, 3, 1)], [BoundaryFrame(0.0, [np.zeros(64)])])
    assert bad.primitives(0) == []                           # a block, not a face: skipped


# -- iso and particles ----------------------------------------------------------------------------
def test_iso_and_particle_layers():
    iso = IsosurfaceFile("a.iso", "TEMPERATURE", "t", "C")
    tri = np.array([[0, 1, 2]])
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    iso.frames = [IsosurfaceFrame(0.0, verts, tri), IsosurfaceFrame(2.0, verts + 1, tri, np.array([1.0, 2.0, 3.0]))]
    il = sc.IsoLayer("I", iso, level=200.0)
    m = il.primitives(1)[0]
    assert isinstance(m, TriMesh) and m.level == 200.0 and m.vertices[0, 0] == 1.0 and m.values.tolist() == [1, 2, 3]
    assert il.value_range() == (1.0, 3.0)
    pc = ParticleClass("WATER", ["DIAMETER"], ["um"], [
        ParticleFrame(0.0, np.zeros((2, 3)), np.array([1, 2]), {"DIAMETER": np.array([10.0, 20.0])}),
        ParticleFrame(1.0, np.ones((3, 3)), np.array([1, 2, 3]), {"DIAMETER": np.array([1.0, 2.0, 3.0])})])
    pl = sc.ParticleLayer("P", pc, "DIAMETER", 0.02)
    cloud = pl.primitives(1)[0]
    assert isinstance(cloud, PointCloud) and cloud.points.shape == (3, 3) and cloud.diameter == 0.02
    assert pl.value_range() == (1.0, 20.0) and pl.units == "um"
    with pytest.raises(KeyError):
        sc.ParticleLayer("Q", pc, "NOPE")
    assert sc.ParticleLayer("N", pc).primitives(0)[0].values is None


# -- volumes: smoke and fire ---------------------------------------------------------------------
def test_transfer_functions():
    rho = np.array([0.0, 1e-4, 1e-3, 1e-1])
    a = transfer.smoke_rgba(rho, 0.5)[..., 3]
    assert a[0] == 0 and np.all(np.diff(a) > 0) and a[-1] < 1.0 + 1e-9
    assert a[1] == pytest.approx(1 - np.exp(-8700 * 1e-4 * 0.5))
    assert transfer.smoke_rgba(rho, 0.5, opacity=0.5)[..., 3][-1] == pytest.approx(a[-1] * 0.5)
    f = transfer.fire_rgba(np.array([0.0, 100.0, 200.0, 1100.0, 5000.0]))
    assert f[0, 3] == 0 and f[1, 3] == 0 and f[2, 3] > 0 and f[-1, 3] == pytest.approx(1.0)
    assert f[2, 0] > f[2, 2] and f[-1, 2] > f[2, 2]                # red at the edge, paler yellow at full strength
    assert transfer.transmittance(np.array([1e-4, 1e-4]), 0.5) == pytest.approx(np.exp(-8700 * 2e-4 * 0.5))
    for bad in (lambda: transfer.smoke_rgba(rho, 0), lambda: transfer.smoke_rgba(rho, 1, opacity=2),
                lambda: transfer.fire_rgba(rho, cutoff=5, full=1), lambda: transfer.apply("lava", rho, 1)):
        with pytest.raises(ValueError):
            bad()


def test_volume_layer_smoke_and_fire(api):
    vals = np.zeros((2, 10, 8, 5))
    vals[1, 2:4, 2:4, 0:2] = 0.01
    smoke = sc.VolumeLayer("S", vals, [0.0, 10.0], api.meshes.get("M"), "SOOT DENSITY", "kg/m3", "smoke")
    assert smoke.kind == "smoke" and smoke.spacing == pytest.approx((1.0, 1.0, 1.0))
    v0, v1 = smoke.primitives(0)[0], smoke.primitives(1)[0]
    assert v0.rgba[..., 3].max() == 0 and v1.rgba[3, 3, 1, 3] > 0.9 and v1.rgba[9, 7, 4, 3] == 0
    assert smoke.sample((2.5, 2.5, 0.5), 1)["value"] == 0.01 and smoke.sample((20, 0, 0), 1) is None
    fire = sc.VolumeLayer("F", vals * 1e5, [0.0, 10.0], api.meshes.get("M"), kind="fire" if False else "scalar", volume_kind="fire") \
        if False else sc.VolumeLayer("F", vals * 1e5, [0.0, 10.0], api.meshes.get("M"), "HRRPUV", "kW/m3", "fire", 0.5)
    assert fire.kind == "fire" and fire.primitives(1)[0].rgba[..., 3].max() <= 0.5 + 1e-9
    with pytest.raises(ValueError):
        sc.VolumeLayer("b", vals[0], [0.0], api.meshes.get("M"))
    with pytest.raises(ValueError):
        sc.VolumeLayer("b", vals, [0.0, 1.0], api.meshes.get("M"), volume_kind="lava")


# -- scene: timeline, frames, clip, probe ----------------------------------------------------------
def _scene(api):
    s = sc.ResultsScene()
    s.add(sc.SliceLayer("A", _slice((0.0, 5.0, 10.0)), api.meshes.get("M")))
    s.add(sc.SliceLayer("B", _slice((0.0, 2.0, 4.0), y_index=2, quantity="VELOCITY"), api.meshes.get("M")))
    return s


def test_timeline_is_the_union_and_layers_hold_their_last_frame(api):
    s = _scene(api)
    assert s.times.tolist() == [0.0, 2.0, 4.0, 5.0, 10.0] and s.n_frames == 5
    f = s.frame(4.5)
    a, b = f.of("A")[0], f.of("B")[0]
    assert a.values[0, 0] == 0.0 + 0                 # A: frame at t=0 still current (next is 5)
    assert b.values[0, 0] == 200.0                   # B ended at t=4: holds its last frame
    assert s.frame(-3).of("A")[0].values[0, 0] == 0  # before the start: first frame
    assert s.frame_index(-1).time == 10.0
    with pytest.raises(IndexError):
        s.frame_index(9)


def test_visibility_opacity_remove_and_duplicates(api):
    s = _scene(api)
    s.set_visible("A", False)
    assert [n for n, _ in s.frame(0).items] == ["B"]
    assert s.probe((2.0, 4.0, 2.0), 0) == []
    s.set_visible("A", True)
    s.set_opacity("A", 0.4)
    assert s.layer("A").opacity == 0.4
    with pytest.raises(ValueError):
        s.set_opacity("A", 3)
    with pytest.raises(ValueError):
        s.add(sc.SliceLayer("A", _slice(), None))
    s.remove("B")
    with pytest.raises(KeyError):
        s.layer("B")
    assert s.unique_name("A") == "A_2" and s.unique_name("Z") == "Z"


def test_clip_planes_on_every_primitive():
    x = np.tile(np.arange(5.0)[:, None], (1, 3))
    g = GridSurface("g", "q", "u", x, np.zeros_like(x), np.zeros_like(x), x.copy())
    c = clip(g, ClipPlane("x", 2.0, "above"))
    assert np.isnan(c.values[:2]).all() and not np.isnan(c.values[2:]).any()
    assert clip(g, ClipPlane("x", 10.0)) is None and clip(g, ClipPlane("x", -1.0)) is g
    tm = TriMesh("t", "q", "u", np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [5, 0, 0], [6, 0, 0], [5, 1, 0]], float),
                 np.array([[0, 1, 2], [3, 4, 5]]))
    assert clip(tm, ClipPlane("x", 3.0)).faces.tolist() == [[3, 4, 5]]
    pc = PointCloud("p", "q", "u", np.array([[0, 0, 0], [5, 0, 0]], float), np.array([1.0, 2.0]))
    assert clip(pc, ClipPlane("x", 1.0, "below")).values.tolist() == [1.0]
    vg = VolumeGrid("v", "q", "u", (0, 0, 0), (1, 1, 1), np.ones((4, 2, 2)), np.ones((4, 2, 2, 4)))
    cv = clip(vg, ClipPlane("x", 2.0))
    assert np.isnan(cv.values[:2]).all() and cv.rgba[:2, ..., 3].max() == 0 and cv.rgba[2:, ..., 3].min() == 1
    with pytest.raises(ValueError):
        ClipPlane("w", 0)
    with pytest.raises(ValueError):
        ClipPlane("x", 0, "left")


def test_scene_clip_and_probe_respect_each_other(api):
    s = _scene(api)
    s.add_clip("x", 5.0, "above")
    xs = np.concatenate([p.x[~np.isnan(p.values)] for _, p in s.frame(0).items])
    assert xs.min() >= 5.0
    assert s.probe((2.0, 4.0, 2.0), 0) == []                      # inside the removed half
    hits = s.probe((7.0, 4.0, 2.0), 0)
    assert [h["layer"] for h in hits] == ["A"]
    s.clear_clips()
    assert len(s.probe((7.0, 2.0, 2.0), 0)) == 1 and s.probe((7.0, 2.0, 2.0), 0)[0]["layer"] == "B"
    with pytest.raises(ValueError):
        s.probe((1, 2), 0)


def test_summary(api):
    s = _scene(api)
    info = s.summary()
    assert info["frames"] == 5 and info["t_end"] == 10.0 and {l["name"] for l in info["layers"]} == {"A", "B"}
    assert sc.ResultsScene().summary()["t_start"] is None


# -- playback --------------------------------------------------------------------------------------
def test_playback_transport():
    p = Playback([0.0, 1.0, 2.0, 4.0])
    assert p.index == 0 and not p.playing and not p.tick(1.0)
    p.play()
    p.set_speed(2.0)
    assert p.tick(0.6) and p.index == 1 and p.time == pytest.approx(1.2)
    assert p.step(1) == 2 and not p.playing and p.step(-5) == 0 and p.step(99) == 3
    p.play()                                                      # at the end: restarts
    assert p.index == 0 and p.playing
    p.tick(10.0)                                                  # runs off the end -> stops there
    assert p.index == 3 and not p.playing and p.time == 4.0 and p.at_end
    p.set_loop(True)
    p.play()
    p.tick(3.0 / 2.0)
    assert p.playing and p.time == pytest.approx(3.0)      # 1.5 s at speed 2 -> 3 s
    p.tick(1000.0)
    assert 0.0 <= p.time <= 4.0 and p.playing
    assert p.toggle() is False and p.toggle() is True
    assert p.seek_time(2.5) == 2 and p.seek_progress(0.0) == 0 and p.seek_progress(1.0) == 3
    assert p.progress == pytest.approx(1.0) and p.seek_index(-1) == 3
    for bad in (lambda: p.set_speed(0), lambda: p.seek_index(9), lambda: p.seek_progress(2), lambda: p.tick(-1)):
        with pytest.raises((ValueError, IndexError)):
            bad()
    for times in ([], [0.0, 0.0]):
        with pytest.raises(ValueError):
            Playback(times)


# -- camera ----------------------------------------------------------------------------------------
def test_camera_path_interpolates_and_round_trips():
    a = ViewportCamera.from_preset(CameraPreset.FRONT, 10)
    b = ViewportCamera.from_preset(CameraPreset.TOP, 20)
    path = CameraPath(smooth=False)
    with pytest.raises(ValueError):
        path.at(0)
    path.add_key(10.0, b)
    path.add_key(0.0, a)
    assert path.at(-5) == a and path.at(99) == b
    mid = path.at(5.0)
    assert mid.position == pytest.approx((0, -5, 10)) and mid.target == pytest.approx((0, 0, 0))
    smooth = CameraPath(smooth=True)
    smooth.add_key(0, a)
    smooth.add_key(10, b)
    assert smooth.at(2.5).position[2] < path.at(2.5).position[2]        # eases in
    back = CameraPath.from_dict(path.to_dict())
    assert back.at(5.0).position == pytest.approx(mid.position) and not back.smooth
    path.add_key(0.0, b)                                                # replaces
    assert len(path.keys) == 2 and path.at(0) == b
    path.remove_key(0.0)
    with pytest.raises(KeyError):
        path.remove_key(123)


def test_saved_views_round_trip():
    v = SavedViews()
    cam = ViewportCamera.from_preset(CameraPreset.ISOMETRIC, 12)
    v.save("iso", cam)
    with pytest.raises(ValueError):
        v.save("iso", cam)
    v.save("iso", ViewportCamera(), overwrite=True)
    with pytest.raises(ValueError):
        v.save(" ", cam)
    v.save("front", ViewportCamera.from_preset(CameraPreset.FRONT))
    assert v.names() == ["front", "iso"]
    again = SavedViews.from_dict(v.to_dict())
    assert again.get("front").position == v.get("front").position
    v.delete("front")
    with pytest.raises(KeyError):
        v.get("front")
    with pytest.raises(KeyError):
        v.delete("front")


# -- manager with real files -------------------------------------------------------------------------
def _rec(b):
    return struct.pack("<i", len(b)) + b + struct.pack("<i", len(b))


def _write_sf(path, data, times, ijk):
    out = _rec(b"TEMPERATURE".ljust(30)) + _rec(b"temp".ljust(30)) + _rec(b"C".ljust(30)) + _rec(struct.pack("<6i", *ijk))
    for t, frame in zip(times, data):
        out += _rec(struct.pack("<f", t)) + _rec(frame.astype("<f4").tobytes(order="F"))
    path.write_bytes(out)


def _write_bf(path, times):
    out = _rec(b"WALL TEMPERATURE".ljust(30)) + _rec(b"wt".ljust(30)) + _rec(b"C".ljust(30)) + _rec(struct.pack("<i", 1))
    out += _rec(struct.pack("<7i", 0, 0, 0, 8, 0, 5, 1))
    for t in times:
        out += _rec(struct.pack("<f", t)) + _rec((np.arange(9 * 6, dtype="<f4") + t).tobytes())
    path.write_bytes(out)


def test_manager_builds_scene_from_a_results_directory(api, tmp_path):
    r = _slice(shape=(11, 1, 6))
    _write_sf(tmp_path / "case_1_1.sf", r.data, r.times, (0, 10, 4, 4, 0, 5))
    _write_bf(tmp_path / "case_1_1.bf", [0.0, 3.0])
    api.scene.open_results(str(tmp_path))
    (sl,) = api.scene.add_slices("TEMPERATURE")
    assert sl.mesh is api.meshes.get("M") and sl.n_frames == 3            # mesh found from the _1 in the file name
    (bl,) = api.scene.add_boundary()
    assert bl.n_frames == 2 and api.scene.scene.times.tolist() == [0.0, 3.0, 5.0, 10.0]
    assert api.scene.playback.n_frames == 4
    api.scene.playback.seek_time(5.0)
    assert api.scene.probe((2.0, 4.0, 3.0))[0]["value"] == 100 + 2 * 6 + 3        # at the playback time
    api.scene.add_slices("TEMPERATURE")                                    # same file again -> unique name
    assert len({l["name"] for l in api.scene.layers()}) == 3
    assert api.scene.playback.time == 5.0                                  # position survives layer changes
    with pytest.raises(LookupError):
        api.scene.add_slices("NOPE")
    with pytest.raises(LookupError):
        api.scene.add_particles()
    api.scene.remove(api.scene.layers()[-1]["name"])


def test_manager_errors_and_extras(api, tmp_path):
    with pytest.raises(RuntimeError):
        api.scene.add_slices()
    with pytest.raises(FileNotFoundError):
        api.scene.open_results(str(tmp_path / "nope"))
    layer = api.scene.add_slice_result(_slice(), mesh="M")
    assert layer.mesh is api.meshes.get("M")
    with pytest.raises(KeyError):
        api.scene.add_slice_result(_slice(), mesh="NOPE")
    api.scene.add_volume(np.zeros((1, 10, 8, 5)), [0.0], "M", kind="smoke", name="smoke")
    api.meshes.add_mesh(ijk=(2, 2, 2), xb=(20, 22, 0, 2, 0, 2), name="M2")
    with pytest.raises(ValueError):                                   # two meshes: it cannot guess which one
        api.scene.add_volume(np.zeros((1, 2, 2, 2)), [0.0], None)
    out = api.scene.render_frame(5.0, str(tmp_path / "f.png"))
    assert open(out, "rb").read(4) == b"\x89PNG"
    api.scene.clear()
    assert api.scene.layers() == []
    with pytest.raises(LookupError):
        api.scene.render_frame(0, str(tmp_path / "g.png"))


def test_views_and_camera_through_api(api):
    api.viewport.set_camera(ViewportCamera.from_preset(CameraPreset.TOP, 30))
    api.scene.save_view("top")
    api.viewport.set_camera(ViewportCamera.from_preset(CameraPreset.FRONT))
    assert api.scene.apply_view("top").position == (0, 0, 30)
    assert api.viewport.state.camera.position == (0, 0, 30)
    api.scene.add_slice_result(_slice(), mesh="M")
    api.scene.camera_path.add_key(0, ViewportCamera.from_preset(CameraPreset.FRONT))
    api.scene.camera_path.add_key(10, ViewportCamera.from_preset(CameraPreset.TOP))
    api.scene.playback.seek_time(10)
    assert api.scene.camera_at().position == (0, 0, 15.0)


def test_agent_tools(api, tmp_path):
    r = _slice()
    _write_sf(tmp_path / "c_1_1.sf", r.data, r.times, (0, 10, 4, 4, 0, 5))
    d = AgentToolDispatcher(api)
    d.call("scene_open_results", {"source": str(tmp_path)})
    (name,) = d.call("scene_add_slices", {"quantity": "TEMPERATURE"})
    assert d.call("scene_summary", {})["frames"] == 3
    assert d.call("scene_seek", {"time": 5.0})["index"] == 1
    assert d.call("scene_seek", {"step": 1})["index"] == 2
    assert d.call("scene_probe", {"point": [2, 4, 3]})[0]["layer"] == name
    assert d.call("scene_add_clip", {"axis": "x", "position": 5}) == 1
    assert d.call("scene_probe", {"point": [2, 4, 3]}) == []
    assert d.call("scene_add_clip", {"clear": True}) == 0
    d.call("scene_set_layer", {"name": name, "opacity": 0.5, "visible": False})
    assert api.scene.layers()[0]["visible"] is False and api.scene.layers()[0]["opacity"] == 0.5
    assert len(d.call("scene_layers", {})) == 1
    d.call("scene_save_view", {"name": "v"})
    d.call("scene_set_layer", {"name": name, "remove": True})
    assert d.call("scene_layers", {}) == []
    with pytest.raises(ValueError):
        d.call("scene_add_clip", {})
