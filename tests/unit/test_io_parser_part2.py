"""Unit tests — pyfds.io.fds_parser (FdsParser). (part 1 of 1). (part 2 of 3)."""


from __future__ import annotations

import textwrap
import pytest
from pyfds.io.fds_parser import FdsParser
from pyfds.core.exceptions import FdsParseError


@pytest.fixture
def parser():
    return FdsParser()


class TestFdsParserFixture:
    def test_simple_room_meshes(self, parser, simple_room_fds_path):
        p = parser.parse(simple_room_fds_path)
        assert len(p.meshes) == 1
        assert p.meshes[0].name == "mesh_01"

    def test_simple_room_surfaces(self, parser, simple_room_fds_path):
        p = parser.parse(simple_room_fds_path)
        surf_names = {s.name for s in p.surfaces}
        assert "fire" in surf_names

    def test_simple_room_obstructions(self, parser, simple_room_fds_path):
        p = parser.parse(simple_room_fds_path)
        assert len(p.obstructions) >= 1

    def test_simple_room_devices(self, parser, simple_room_fds_path):
        p = parser.parse(simple_room_fds_path)
        devc_names = {d.name for d in p.devices}
        assert "tc_center" in devc_names

    def test_simple_room_ramps(self, parser, simple_room_fds_path):
        p = parser.parse(simple_room_fds_path)
        ramp = next((r for r in p.ramps if r.name == "tau_fire"), None)
        assert ramp is not None
        assert len(ramp.times) == 3
