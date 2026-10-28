"""Golden images: the fixture room drawn off-screen in a few configurations must stay close to the stored pictures.

Regenerate after an intended change with ``PYFDS_UPDATE_GOLDEN=1 pytest tests/unit/test_viewer_golden.py``. The comparison
is a mean absolute pixel difference (0-255) with a tolerance, so small driver differences do not fail the test."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from pyfds.api.facade import FdsApi
from pyfds.gui.results.scene_adapter import SceneAdapter

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
GOLD = Path(__file__).parent.parent / "golden" / "results_viewer"
R = "root/FDS Results/"
TOL = 6.0
SIZE = (360, 240)

SCENES = {
    "slices_geometry": ["geometry/fds_actual", R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1", R + "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 2"],
    "isosurface_particles": [R + "Isosurfaces/TEMPERATURE/100/Mesh 1", R + "Particles/DROPS/Mesh 1", R + "Particles/DROPS/Mesh 2"],
    "smoke_and_slice": [R + "3D Smoke/SOOT DENSITY/Mesh 1", R + "2D Slices/TEMPERATURE/T_X (X = 1.05)/Mesh 1"],
}


def render(tmp_path, ids):
    shutil.copytree(FIX, tmp_path / "r")
    v = FdsApi().viewer
    v.open_results(str(tmp_path / "r" / "rroom.smv"))
    v.set_rendering(antialiasing="disabled", ambient_occlusion=False)
    for leaf in v.active_leaves():                   # a first open shows the geometry: each scene draws only its list
        v.deactivate(leaf.id)
    for i in ids:
        v.activate(i)
    v.standard_view("isometric")
    pl = pv.Plotter(off_screen=True, window_size=SIZE)
    ad = SceneAdapter(pl)
    ad.draw(v.frame(4.0), v.viz)
    ad.apply_camera(v.camera)
    img = pl.screenshot(return_img=True)
    pl.close()
    return img


@pytest.mark.parametrize("name", sorted(SCENES))
def test_scene_matches_golden(tmp_path, name):
    img = render(tmp_path, SCENES[name])
    path = GOLD / f"{name}.npy"
    if os.environ.get("PYFDS_UPDATE_GOLDEN") or not path.exists():
        GOLD.mkdir(parents=True, exist_ok=True)
        np.save(path, img)
        pytest.skip(f"golden image {name} written")
    ref = np.load(path)
    assert ref.shape == img.shape
    diff = float(np.abs(ref.astype(float) - img.astype(float)).mean())
    assert diff < TOL, f"{name}: mean pixel difference {diff:.2f} (limit {TOL}); regenerate with PYFDS_UPDATE_GOLDEN=1 if intended"
    assert img.std() > 5                                         # not a blank frame
