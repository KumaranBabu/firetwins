"""Unit tests — pyfds.io.fds_parser (FdsParser)."""
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


class TestPhase1Parser:
    """Tests for Phase 1 new parser features."""

    def test_parse_geom(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &GEOM ID='terrain', SURF_ID='INERT', IS_TERRAIN=.TRUE. /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.geoms) == 1
        assert p.geoms[0].name == "terrain"
        assert p.geoms[0].is_terrain is True

    def test_parse_geom_with_verts_faces(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &GEOM ID='tri', SURF_ID='INERT',
                  VERTS=0,0,0, 1,0,0, 0,1,0,
                  FACES=1,2,3 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.geoms) == 1
        g = p.geoms[0]
        assert g.verts is not None and len(g.verts) == 3
        assert g.faces is not None and len(g.faces) == 1

    def test_parse_pl3d(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &PL3D ID='temp_out', QUANTITY='TEMPERATURE' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.plot3ds) == 1
        assert p.plot3ds[0].quantity == "TEMPERATURE"

    def test_parse_trnx(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TRNX MESH_NUMBER=1, IDERIV=0, CC=0.5, PC=0.3 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.mesh_transforms) == 1
        t = p.mesh_transforms[0]
        assert t.direction == "X"
        assert t.cc == 0.5
        assert t.pc == 0.3

    def test_parse_trny(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TRNY MESH_NUMBER=1, IDERIV=0, CC=1.0, PC=0.5 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.mesh_transforms) == 1
        assert p.mesh_transforms[0].direction == "Y"

    def test_parse_trnz(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TRNZ MESH_NUMBER=2, CC=2.5, PC=0.8 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.mesh_transforms) == 1
        assert p.mesh_transforms[0].direction == "Z"

    def test_parse_mult_dx0(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &MULT ID='rep', DX=2.0, DX0=0.5, I_LOWER=0, I_UPPER=3 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.mults) == 1
        assert p.mults[0].dx0 == 0.5

    def test_parse_zone_leak_areas(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,4,0,4,0,3 /
            &ZONE ID='z1', XB=0,4,0,4,0,3, LEAK_AREAS=0.001,0.002 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.zones) == 1
        assert p.zones[0].leak_areas is not None
        assert len(p.zones[0].leak_areas) == 2

    def test_parse_reac_fuel_radcal_id(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &REAC ID='fire', FUEL='WOOD', HEAT_OF_COMBUSTION=17700, FUEL_RADCAL_ID='PROPANE' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.reactions) == 1
        assert p.reactions[0].fuel_radcal_id == "PROPANE"

    def test_parse_devc_quantity2(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &DEVC ID='flux01', XYZ=1,1,0.5, QUANTITY='RADIATIVE HEAT FLUX',
                   QUANTITY2='CONVECTIVE HEAT FLUX' /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.devices[0].quantity2 == "CONVECTIVE HEAT FLUX"

    def test_parse_ctrl_deadband(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &CTRL ID='thermo', FUNCTION_TYPE='DEADBAND', DEADBAND=18.0,22.0 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.controls) == 1
        c = p.controls[0]
        assert c.deadband is not None
        assert c.deadband == (18.0, 22.0)

    def test_parse_init_sphere(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,4,0,4,0,2 /
            &INIT ID='sp', XB=0,4,0,4,0,2, SHAPE='SPHERE', RADIUS=0.5,
                   XYZ=2.0,2.0,1.0 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.inits) == 1
        init = p.inits[0]
        assert init.shape == "SPHERE"
        assert init.radius == 0.5
        assert init.xyz_center == (2.0, 2.0, 1.0)

    def test_parse_mesh_cylindrical(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='cyl', IJK=10,10,20, XB=0,1,0,1,0,2, CYLINDRICAL=.TRUE. /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.meshes[0].cylindrical is True

    def test_parse_matl_n_reactions(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &MATL ID='wood', DENSITY=500, CONDUCTIVITY=0.1, SPECIFIC_HEAT=1.3,
                   N_REACTIONS=2,
                   A=1E10,2E8, E=1.5E5,1.2E5, HEAT_OF_REACTION=400,200 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert len(p.materials) == 1
        m = p.materials[0]
        assert m.n_reactions == 2
        assert len(m.reactions) == 2

    def test_parse_dump_plot3d_quantity(self, parser, tmp_path):
        path = write_fds(tmp_path, """
            &HEAD CHID='c' /
            &DUMP PLOT3D_QUANTITY(1)='TEMPERATURE', PLOT3D_QUANTITY(2)='U-VELOCITY' /
            &MESH ID='m', IJK=10,10,5, XB=0,2,0,2,0,1 /
            &TAIL /
        """)
        p = parser.parse(path)
        assert p.dump.plot3d_quantities is not None
        assert "TEMPERATURE" in p.dump.plot3d_quantities
