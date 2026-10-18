"""The saved demo cases (examples/example-1) load, validate and export."""
from __future__ import annotations

from pathlib import Path

import pytest

from pyfds.api import FdsApi
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CASES = [
    ("example-1/example_1.pyfds", 24000),
]


@pytest.mark.parametrize("project, cells", CASES)
def test_saved_demo_project_loads_validates_and_exports(project, cells):
    api = FdsApi(Serializer().load(str(EXAMPLES / project)))
    api.validation.gate()                                         # no errors
    assert api.meshes.project_stats()["total_cells"] == cells
    assert len(api.obstructions.all()) >= 1 and api.devices.get("HEAT_DET").z == pytest.approx(2.35)
    text = FdsWriter().generate_content(api.project)
    assert "XYZ=0.0,0.0,0.0" not in text and "N_REACTIONS" not in text
