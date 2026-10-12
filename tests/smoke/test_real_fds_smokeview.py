"""Real-solver smoke test: build a room fire with the API, run the real FDS, read the results back, and
render with the real Smokeview.

Needs the FDS/Smokeview install in ``fds_smv/`` at the repo root (or set ``PYFDS_FDS_HOME`` to a folder with
``FDS6/bin/fds.exe`` and ``SMV6/smokeview.exe``). Skipped when they are not there. Takes about a minute.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyfds.api import FdsApi

HOME = Path(os.environ.get("PYFDS_FDS_HOME", Path(__file__).resolve().parents[2] / "fds_smv"))
FDS = HOME / "FDS6" / "bin" / "fds.exe"
SMV = HOME / "SMV6" / "smokeview.exe"

pytestmark = pytest.mark.skipif(not (FDS.exists() and SMV.exists()), reason="FDS/Smokeview not installed")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("real_fds")
    api = FdsApi()
    api.project.chid = "room1"
    api.meshes.add_mesh(ijk=(20, 20, 15), xb=(0, 3, 0, 3, 0, 2.25), name="M")
    api.surfaces.add_typed("burner", name="FIRE", heat_release_rate=500.0)
    api.obstructions.add_obstruction([1.2, 1.8, 1.2, 1.8, 0, 0.1], surf_id="FIRE", name="BURNER")
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)
    api.meshes.open_boundaries()
    api.slices.add_slice("TEMPERATURE", plane="Y", position=1.5, name="SLY")
    api.config.configure_simulation(t_end=4.0)
    result = api.execution.run(str(out), fds_binary=str(FDS), timeout=600)
    return api, out, result


def test_fds_accepts_the_generated_input_and_finishes(run):
    api, out, result = run
    assert result.success, (result.error, result.return_code)
    log = (out / "room1.out").read_text(errors="replace")
    assert "STOP: FDS completed successfully" in log
    assert "ERROR" not in log


def test_expected_output_files_exist(run):
    _, out, _ = run
    names = {p.name for p in out.iterdir()}
    assert {"room1.smv", "room1_hrr.csv", "room1.out"} <= names
    assert any(n.endswith(".sf") for n in names)


def test_hrr_file_is_read_with_real_column_names(run):
    from pyfds.results.reader import DeviceReader
    _, out, _ = run
    d = DeviceReader.read(str(out / "room1_hrr.csv"))
    assert {"Time", "HRR", "Q_RADI"} <= set(d)                  # real FDS writes units first, names second
    assert d["HRR"].units == "kW"
    assert d["HRR"].data[-1] > 100                              # a 0.36 m2 burner at 500 kW/m2 ramps towards 180 kW+


def test_results_scene_over_real_slice_output(run):
    api, out, _ = run
    api.scene.open_results(str(out))
    (layer,) = api.scene.add_slices("TEMPERATURE")
    assert layer.mesh is api.meshes.get("M") and layer.n_frames >= 4
    lo, hi = layer.value_range()
    assert lo == pytest.approx(20.0, abs=1.0) and hi > 100            # ambient to flame temperature
    api.scene.playback.seek_time(4.0)
    above_fire = api.scene.probe((1.5, 1.5, 0.6))
    corner = api.scene.probe((0.1, 1.5, 0.1))
    assert above_fire and above_fire[0]["value"] > 100
    assert not corner or corner[0]["value"] < above_fire[0]["value"]
    png = api.scene.render_frame(4.0, str(out / "scene_t4.png"))
    assert open(png, "rb").read(4) == b"\x89PNG"


def test_real_smokeview_renders_screenshots(run):
    api, out, _ = run
    api.config.set("smv_binary", str(SMV))
    paths = api.smokeview.render_screenshots(str(out / "room1.smv"), [2.0, 4.0], "TEMPERATURE", str(out / "shots"))
    assert len(paths) == 2
    for p in paths:
        assert Path(p).exists() and Path(p).stat().st_size > 1000, p
        assert open(p, "rb").read(4) == b"\x89PNG"


def test_real_smokeview_movie_frames_and_encoder_result(run):
    import shutil
    api, out, _ = run
    api.config.set("smv_binary", str(SMV))
    rc = api.smokeview.render_movie(str(out / "room1.smv"), str(out / "movies" / "temp.mp4"), "TEMPERATURE")
    frames = sorted((out / "movies").glob("temp_*.png"))
    assert len(frames) >= 4                                  # one image per saved slice frame
    if shutil.which("ffmpeg"):
        assert rc == 0 and (out / "movies" / "temp.mp4").stat().st_size > 1000
    else:
        assert rc == 127                                     # no encoder installed: frames are kept, rc says so
