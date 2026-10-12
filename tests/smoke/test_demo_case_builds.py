"""The saved demo case (examples/demo_room_fire) still builds, validates and exports; its saved project loads."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from pyfds.api import FdsApi
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_room_fire"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_demo", DEMO / "build_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_builds_validates_and_places_devices():
    api = _load_builder().build()
    api.validation.gate()                                         # no errors
    assert api.meshes.project_stats()["total_cells"] == 24000
    assert len(api.holes.all()) == 2 and api.devices.get("HEAT_DET").z == 2.35
    text = FdsWriter().generate_content(api.project)
    assert "XYZ=0.0,0.0,0.0" not in text and "N_REACTIONS" not in text


def test_saved_demo_project_loads_and_matches_the_script():
    saved = FdsApi(Serializer().load(str(DEMO / "demo_room_fire.pyfds")))
    fresh = _load_builder().build()
    assert len(saved.obstructions.all()) == len(fresh.obstructions.all())
    assert [d.name for d in saved.devices.all()] == [d.name for d in fresh.devices.all()]
