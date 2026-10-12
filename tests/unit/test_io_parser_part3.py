"""Unit tests — pyfds.io.fds_parser (FdsParser). (part 1 of 1). (part 3 of 3)."""


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
