"""&PROF: FDS takes the face as IOR and only solid-phase quantities (the writer used to emit DIRECTION and TEMPERATURE)."""
from __future__ import annotations

import pytest

from pyfds.api.facade import FdsApi
from pyfds.domain.prof_orient import prof_direction, prof_ior


@pytest.mark.parametrize("text,ior", [("Z+", 3), ("z-", -3), ("X", 1), ("Y-", -2), ("+X", 1), ("-Y", -2), ("2", 2), ("-1", -1), ("", 3), ("?", 3)])
def test_orientation_to_ior(text, ior):
    assert prof_ior(text) == ior


@pytest.mark.parametrize("fields,text", [({"IOR": "3"}, "Z+"), ({"IOR": "-1"}, "X-"), ({"DIRECTION": "Z"}, "Z+"), ({"DIRECTION": "'Y-'"}, "Y-"), ({}, "Z+")])
def test_ior_back_to_orientation(fields, text):
    assert prof_direction(fields) == text


def test_written_with_ior_and_round_trips(tmp_path):
    from pyfds.domain.model import FdsProject, Prof
    from pyfds.io.fds_parser import FdsParser
    from pyfds.io.fds_writer import FdsWriter
    project = FdsProject()
    project.add_entity(Prof(name="t1", quantity="INSIDE WALL TEMPERATURE", x=1.0, y=2.0, z=0.5, direction="X-"))
    text = FdsWriter().generate_content(project)
    line = next(l for l in text.splitlines() if l.startswith("&PROF"))
    assert "IOR=-1" in line and "DIRECTION" not in line and "INSIDE WALL TEMPERATURE" in line
    path = tmp_path / "p.fds"
    path.write_text(text, encoding="utf-8")
    prof = FdsParser().parse(str(path)).profs[0]
    assert (prof.direction, prof.quantity) == ("X-", "INSIDE WALL TEMPERATURE")


def test_gas_quantity_is_not_a_profile_quantity():
    api = FdsApi()
    with pytest.raises(ValueError):
        api.profs.add_profile("TEMPERATURE", [0, 0, 0])
