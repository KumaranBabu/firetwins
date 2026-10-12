"""V13: 360 degree movies (cube faces -> equirectangular), motion blur, and the skybox actually being drawn."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv
from PIL import Image

from pyfds.api.facade import FdsApi
from pyfds.gui.results import cli
from pyfds.gui.results.scene_adapter import (SceneAdapter, _blur_times, make_offscreen_renderer, make_panorama_renderer,
                                             render_cube_faces)
from pyfds.results.viz import capture as cap
from pyfds.results.viz import panorama as pan

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
SL = "root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"


def direction_faces(n: int) -> dict:
    """Faces whose colour is the viewing direction itself, so the stitched panorama can be compared with the exact answer."""
    faces = {}
    g = (np.arange(n) / (n - 1)) * 2 - 1
    X, Y = np.meshgrid(g, -g)                                    # x = right, y = up (row 0 = top)
    for name, (d, up) in pan.FACES.items():
        f, u = np.asarray(d, float), np.asarray(up, float)
        r = np.cross(f, u)
        vec = f + X[..., None] * r + Y[..., None] * u
        vec /= np.linalg.norm(vec, axis=-1, keepdims=True)
        faces[name] = ((vec + 1) / 2 * 255).round().astype(np.uint8)
    return faces


def test_equirect_matches_the_exact_direction_everywhere():
    w, h = 256, 128
    img = pan.equirect(direction_faces(200), w, h).astype(float)
    lon = math.pi - 2 * math.pi * np.arange(w) / (w - 1)
    lat = math.pi / 2 - math.pi * np.arange(h) / (h - 1)
    LON, LAT = np.meshgrid(lon, lat)
    d = np.stack([np.cos(LAT) * np.cos(LON), np.cos(LAT) * np.sin(LON), np.sin(LAT)], -1)
    exact = (d + 1) / 2 * 255
    assert np.abs(img - exact).mean() < 1.5 and np.abs(img - exact).max() < 12


def test_picture_orientation_forward_left_up():
    w, h = 400, 200
    img = pan.equirect(direction_faces(256), w, h).astype(float)
    cx, cy = w // 2, h // 2
    fwd = (img[cy, cx] / 255) * 2 - 1
    assert fwd[0] > 0.97                                         # the middle looks along +X
    left = (img[cy, cx - w // 4] / 255) * 2 - 1
    assert left[1] > 0.95                                        # a quarter to the left of centre is +Y
    assert ((img[0, cx] / 255) * 2 - 1)[2] > 0.95 and ((img[-1, cx] / 255) * 2 - 1)[2] < -0.95
    back = (img[cy, 0] / 255) * 2 - 1
    assert back[0] < -0.97


def test_cross_cubemap_roundtrip_and_errors():
    n = 8
    faces = {k: np.full((n, n, 3), i * 30, np.uint8) for i, k in enumerate(pan.ORDER)}
    cross = np.zeros((3 * n, 4 * n, 3), np.uint8)
    pos = {"+z": (0, 1), "+y": (1, 0), "+x": (1, 1), "-y": (1, 2), "-x": (1, 3), "-z": (2, 1)}
    for k, (r, c) in pos.items():
        cross[r * n:(r + 1) * n, c * n:(c + 1) * n] = faces[k]
    back = pan.cross_to_faces(cross)
    assert all((back[k] == faces[k]).all() for k in pan.ORDER)
    with pytest.raises(ValueError):
        pan.cross_to_faces(np.zeros((10, 10, 3)))
    with pytest.raises(ValueError):
        pan.equirect({k: v for k, v in faces.items() if k != "-z"}, 64)
    with pytest.raises(ValueError):
        pan.equirect({**faces, "+x": np.zeros((n + 1, n + 1, 3), np.uint8)}, 64)
    assert pan.movie_size(1001) == (1000, 500)
    with pytest.raises(ValueError):
        pan.movie_size(10)
    assert cap.movie360_plan("m.mp4", 0, 1, 2, 1.0, 2050).size == (2048, 1024)


@pytest.fixture()
def v(tmp_path):
    shutil.copytree(FIX, tmp_path / "r")
    viewer = FdsApi().viewer
    viewer.open_results(str(tmp_path / "r" / "rroom.smv"))
    viewer.activate(SL)
    viewer.activate("geometry/fds_actual")
    return viewer


def test_cube_faces_and_panorama_render_the_room(v, tmp_path):
    v.set_camera(type(v.camera)(position=(0.7, 0.9, 1.2), target=(1.5, 0.9, 1.2)))
    faces = render_cube_faces(v, 4.0, 64)
    assert set(faces) == set(pan.ORDER) and faces["+x"].shape == (64, 64, 3)
    assert not np.array_equal(faces["+y"], faces["-y"])         # the slice at Y = 1.5 is only in front of the +y view
    assert faces["+y"].reshape(-1, 3).std(axis=0).max() > 10
    out = tmp_path / "pano.png"
    make_panorama_renderer(v)(str(out), (256, 128), 4.0, cap.CURRENT)
    img = np.asarray(Image.open(out))
    assert img.shape == (128, 256, 3) and img.std() > 8


def test_360_movie_through_the_api_and_cli(v, tmp_path):
    plan = cap.movie360_plan(str(tmp_path / "p.mp4"), 0, 1, fps=2, width=128 + 0)
    res = v.render_movie(plan, make_panorama_renderer(v))
    assert res["frames"] == 3 and (Path(res["path"]).exists() or len(list(Path(res["frames_dir"]).glob("*.png"))) == 3)
    smv = tmp_path / "r" / "rroom.smv"
    assert cli.main(["-movie", "-mv360", "-mvname", str(tmp_path / "c.mp4"), "-mvwidth", "128", "-mvframerate", "2", str(smv)]) == 0
    assert (tmp_path / "c.mp4").exists() or (tmp_path / "c_frames").exists()
    assert cap.parse_cli(["-movie", "-mv360", "x"]).options["mv360"] is True


def test_motion_blur_averages_shutter_times(v, tmp_path):
    v.viz.motion_blur = False
    v.motion_blur_span = 3.0
    assert _blur_times(v, 4.0) == [4.0]
    v.set_motion_blur(True)
    assert _blur_times(v, 4.0) == pytest.approx([2.5, 3.25, 4.0, 4.75, 5.5])
    v.motion_blur_span = 0.0
    assert _blur_times(v, 4.0) == [4.0]
    sharp, blurred = tmp_path / "s.png", tmp_path / "b.png"
    v.set_motion_blur(False)
    make_offscreen_renderer(v)(str(sharp), (200, 140), 4.0, cap.CURRENT)
    v.set_motion_blur(True)
    plan = cap.movie_plan(str(tmp_path / "m.mp4"), 3.0, 5.0, fps=1, speed=2.0, size=(200, 140))   # 2 s per frame
    seen = []
    res = v.render_movie(plan, lambda path, size, t, view: seen.append(v.motion_blur_span) or
                         make_offscreen_renderer(v)(path, size, t, view))
    assert all(s == pytest.approx(1.0) for s in seen) and v.motion_blur_span == 0.0
    make_offscreen_renderer(v)(str(blurred), (200, 140), 4.0, cap.CURRENT)           # span reset: identical to sharp
    assert np.array_equal(np.asarray(Image.open(sharp)), np.asarray(Image.open(blurred)))
    v.motion_blur_span = 2.0
    make_offscreen_renderer(v)(str(blurred), (200, 140), 4.0, cap.CURRENT)
    v.motion_blur_span = 0.0
    assert not np.array_equal(np.asarray(Image.open(sharp)), np.asarray(Image.open(blurred)))


def _png(path: Path, color, size=(64, 32)) -> str:
    Image.fromarray(np.full((size[1], size[0], 3), color, np.uint8)).save(path)
    return str(path)


def test_skybox_is_drawn_for_every_kind(v, tmp_path):
    def draw():
        pl = pv.Plotter(off_screen=True, window_size=(160, 100))
        ad = SceneAdapter(pl)
        ad.draw(v.frame(4.0), v.viz)
        img = pl.screenshot(return_img=True)
        pl.close()
        return ad.skybox_state, img

    state, none_img = draw()
    assert state == "none"
    v.set_skybox("predefined")
    state, grad = draw()
    assert state == "gradient" and not np.array_equal(grad, none_img)
    v.set_skybox("image360", [_png(tmp_path / "sky.png", (200, 60, 60))], z_rotation=30)
    state, sky = draw()
    assert state == "texture"
    cross = np.zeros((24, 32, 3), np.uint8)
    cross[:] = (40, 120, 200)
    Image.fromarray(cross).save(tmp_path / "cross.png")
    v.set_skybox("cubemap", [str(tmp_path / "cross.png")])
    assert draw()[0] == "texture"
    faces = [_png(tmp_path / f"f{i}.png", (30 * i, 90, 160), (16, 16)) for i in range(6)]
    v.set_skybox("split_cubemap", faces)
    assert draw()[0] == "texture"
    v.set_skybox("image360", [_png(tmp_path / "sky2.png", (1, 2, 3))], show=False)
    assert draw()[0] == "none"
    v.set_skybox("none")
    v.viz.skybox.kind, v.viz.skybox.files = "image360", [str(tmp_path / "gone.png")]     # file removed behind our back
    assert draw()[0].startswith("error")


def test_image_based_lighting_flag_is_applied_with_a_skybox(v, tmp_path):
    v.set_skybox("image360", [_png(tmp_path / "s.png", (90, 90, 200))])
    v.set_rendering(image_based_lighting=True)
    pl = pv.Plotter(off_screen=True, window_size=(120, 80))
    ad = SceneAdapter(pl)
    ad.draw(v.frame(4.0), v.viz)
    assert ad.skybox_state == "texture"
    pl.close()
