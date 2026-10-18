"""A mesh with MULT_ID is several meshes (validation, 3D view, run count), and an imported OBST keeps what FDS would give it."""
from __future__ import annotations

from pyfds.api import FdsApi
from pyfds.gui.viewport_scene import build_scene

_CASE = """&HEAD CHID='mm', TITLE='mult' /
&MESH IJK=10,10,10, XB=0,2,0,2,0,2, MULT_ID='m' /
&MULT ID='m', DX=2, DY=2, I_UPPER=1, J_UPPER=1 /
&TIME T_END=10 /
&SURF ID='WALL', DEFAULT=.TRUE., RGB=200,200,200 /
&SURF ID='FOAM', COLOR='PURPLE' /
&OBST XB=2.5,3.5,2.5,3.5,0,1 /
&OBST XB=0.5,1.5,0.5,1.5,0,1, SURF_ID='FOAM' /
&OBST XB=0.5,1.5,2.5,3.5,0,1, SURF_ID='INERT' /
&TAIL /
"""


def _api(tmp_path):
    f = tmp_path / "mm.fds"
    f.write_text(_CASE)
    api = FdsApi()
    api.session.open_project(str(f))
    return api


def test_a_multiplier_makes_one_mesh_per_copy(tmp_path):
    api = _api(tmp_path)
    mesh = api.project.meshes[0]
    copies = api.meshes.copies_of(mesh)
    assert len(copies) == 4 and api.meshes.run_count() == 4
    assert {(c.x_min, c.y_min) for c in copies} == {(0, 0), (2, 0), (0, 2), (2, 2)}
    assert all(c.mult_id is None for c in copies) and mesh.mult_id == "m"       # the project's own mesh is untouched
    assert [c.name for c in copies][0] == mesh.name and len(api.project.meshes) == 1


def test_objects_in_a_copy_are_not_reported_outside_the_meshes(tmp_path):
    api = _api(tmp_path)
    assert not [m for m in api.validate() if "outside" in m]


def test_the_mesh_still_round_trips_with_its_multiplier(tmp_path):
    api = _api(tmp_path)
    out = tmp_path / "out.fds"
    api.session.save_project(str(out))
    text = out.read_text()
    assert text.count("MULT_ID='m'") == 1 and "&MULT ID='m'" in text


def test_the_3d_view_draws_every_copy_but_selects_the_one_mesh(tmp_path):
    api = _api(tmp_path)
    meshes = [s for s in build_scene(api) if s.entity_kind == "mesh"]
    assert len(meshes) == 4 and {id(s.entity) for s in meshes} == {id(api.project.meshes[0])}


def test_obst_without_surface_takes_the_default_surface_and_colour_comes_from_its_surface(tmp_path):
    api = _api(tmp_path)
    plain, foam, inert = api.project.obstructions
    assert plain.surface_id == "WALL" and tuple(plain.rgb) == (200, 200, 200)   # no SURF_ID: the DEFAULT surface
    assert foam.surface_id == "FOAM" and foam.color == "PURPLE"                 # no COLOR: the surface's colour
    assert inert.surface_id == "INERT"                                           # said INERT: stays INERT


def test_a_particle_with_a_surface_is_written_without_a_diameter(tmp_path):
    """Real FDS stops with ERROR(213) when a &PART has both DIAMETER and SURF_ID (found importing Examples/Fires/couch.fds)."""
    f = tmp_path / "p.fds"
    f.write_text("&HEAD CHID='p' /\n&MESH IJK=4,4,4, XB=0,1,0,1,0,1 /\n&SURF ID='ign', TMP_FRONT=1000 /\n"
                 "&PART ID='ig', SURF_ID='ign', STATIC=.TRUE. /\n&PART ID='drop' /\n&TAIL /\n")
    api = FdsApi()
    api.session.open_project(str(f))
    lines = {ln.split("'")[1]: ln for ln in api.fds_text().splitlines() if ln.startswith("&PART")}
    assert "DIAMETER" not in lines["ig"] and "SURF_ID='ign'" in lines["ig"]
    assert "DIAMETER" in lines["drop"]
