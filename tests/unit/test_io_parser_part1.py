"""Unit tests — pyfds.io.fds_parser (FdsParser). (part 1 of 1). (part 1 of 3)."""


from __future__ import annotations

import textwrap
import pytest
from pyfds.io.fds_parser import FdsParser
from pyfds.core.exceptions import FdsParseError


@pytest.fixture
def parser():
    return FdsParser()

def write_fds(tmp_path, content: str, name: str = "test.fds") -> str:
    """Write content to a temp .fds file and return the path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return str(p)


class TestFdsParserBasic:
    def test_parse_nonexistent_file_raises(self, parser):
        with pytest.raises(FdsParseError):
            parser.parse("/nonexistent/path/test.fds")

    def test_parse_simple_room_fixture(self, parser, simple_room_fds_path):
        project = parser.parse(simple_room_fds_path)
        assert project.chid == "simple_room"

    def test_parse_returns_fds_project(self, parser, simple_room_fds_path):
        from pyfds.domain.model import FdsProject
        project = parser.parse(simple_room_fds_path)
        assert isinstance(project, FdsProject)

    def test_parse_head(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='my_case', TITLE='My Test' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.chid == "my_case"
        assert p.title == "My Test"

    def test_parse_time(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &TIME T_END=120.0, T_BEGIN=5.0 /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.params.t_end == 120.0
        assert p.params.t_begin == 5.0

    def test_parse_mesh(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='mesh_01', IJK=20,20,10, XB=0,4,0,4,0,2 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.meshes) == 1
        m = p.meshes[0]
        assert m.name == "mesh_01"
        assert m.cell_count[0] == 20 and m.cell_count[1] == 20 and m.cell_count[2] == 10

    def test_parse_multiple_meshes(self, parser, multi_mesh_fds_path):
        p = parser.parse(multi_mesh_fds_path)
        assert len(p.meshes) == 2

    def test_parse_surf(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &SURF ID='burner', HRRPUA=500.0, TAU_Q=-1.0 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.surfaces) > 0
        fire_surf = next((s for s in p.surfaces if s.name == "burner"), None)
        assert fire_surf is not None
        assert fire_surf.heat_release_rate == 500.0

    def test_parse_obst(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &OBST ID='floor', XB=0,2,0,2,0,0.1, SURF_ID='INERT' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.obstructions) == 1
        assert p.obstructions[0].name == "floor"

    def test_parse_vent(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &VENT ID='top', XB=0,2,0,2,1,1, SURF_ID='OPEN' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.vents) == 1
        assert p.vents[0].name == "top"

    def test_parse_devc(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &DEVC ID='tc01', XYZ=1.0,1.0,0.9, QUANTITY='TEMPERATURE' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.devices) == 1
        assert p.devices[0].quantity == "TEMPERATURE"

    def test_parse_ramp_accumulation(self, parser, tmp_path):
        """Multiple &RAMP lines with same ID should merge into one Ramp object."""
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &RAMP ID='q_ramp', T=0.0, F=0.0 /
            &RAMP ID='q_ramp', T=30.0, F=1.0 /
            &RAMP ID='q_ramp', T=60.0, F=1.0 /
            &TAIL /
        """)
        p = parser.parse(path)
        ramp = next((r for r in p.ramps if r.name == "q_ramp"), None)
        assert ramp is not None
        assert len(ramp.times) == 3
        assert len(ramp.values) == 3

    def test_parse_slcf(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &SLCF PBZ=0.5, QUANTITY='TEMPERATURE' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.slices) == 1

    def test_parse_bndf(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &BNDF QUANTITY='WALL TEMPERATURE' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.bndfs) == 1

    def test_parse_misc(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MISC TMPA=25.0, HUMIDITY=60.0 /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.misc.tmpa == 25.0

    def test_comment_lines_ignored(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            ! This is a comment line
            &HEAD CHID='c' /  ! inline comment
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /  ! another comment
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.chid == "c"
        assert len(p.meshes) == 1

    def test_warnings_list_accessible(self, parser, simple_room_fds_path):
        parser.parse(simple_room_fds_path)
        assert isinstance(parser.warnings, list)

    def test_parse_does_not_crash_on_unknown_namelist(self, parser, tmp_path):
        """Parser should skip unknown namelists, not crash."""
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &UNKNOWNNAMELIST FOO=1.0 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.chid == "c"
