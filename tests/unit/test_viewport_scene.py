"""
Unit tests — pure scene-building logic (src/pyfds/gui/viewport_scene.py).

No Qt, no VTK render window, no display required — pyvista mesh
construction (pv.Box, pv.Sphere) is plain numpy bookkeeping, safe under any
platform including the offscreen QPA one this whole test suite runs under.
The actual pyvistaqt.QtInteractor widget (viewport_3d.py) is NOT imported
here — see that module's docstring for why it can only be verified by a
live desktop launch, never inside pytest.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pyvista")

from pyfds.api import FdsApi
from pyfds.core.viewport import VisibilityFlags


def _make_api():
    return FdsApi()


def test_build_scene_empty_project_returns_nothing():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    assert build_scene(api) == []


def test_build_scene_includes_mesh_as_wireframe():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")

    specs = build_scene(api)
    mesh_specs = [s for s in specs if s.entity_kind == "mesh"]
    assert len(mesh_specs) == 1
    assert mesh_specs[0].style == "wireframe"
    assert mesh_specs[0].label == "m1"


def test_build_scene_obstruction_uses_color_and_opacity():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1", color="RED")

    specs = build_scene(api)
    obst_specs = [s for s in specs if s.entity_kind == "obstruction"]
    assert len(obst_specs) == 1
    assert obst_specs[0].color == "#c0392b"
    assert obst_specs[0].opacity == 1.0  # transparency unset (0.0) -> FDS-default opaque
    assert obst_specs[0].style == "surface"


def test_build_scene_unmapped_color_falls_back_to_gray():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1", color="NOT_A_REAL_FDS_COLOR")

    specs = build_scene(api)
    assert specs[0].color == "#9a9a9a"


def test_build_scene_respects_explicit_transparency():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1", transparency=0.3)

    specs = build_scene(api)
    assert specs[0].opacity == 0.3


def test_build_scene_degenerate_vent_axis_still_produces_geometry():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    # z_min == z_max — a vent flush against a horizontal surface.
    api.vents.add_vent(xb=[0, 1, 0, 1, 2, 2], name="v1")

    specs = build_scene(api)
    vent_specs = [s for s in specs if s.entity_kind == "vent"]
    assert len(vent_specs) == 1
    assert vent_specs[0].mesh.n_points > 0
    assert vent_specs[0].mesh.bounds[5] > vent_specs[0].mesh.bounds[4]  # z_max > z_min after thickening


def test_build_scene_excludes_disabled_entities():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    keep = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    drop = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    drop.enabled = False

    specs = build_scene(api)
    labels = [s.label for s in specs if s.entity_kind == "obstruction"]
    assert labels == ["a"]


def test_build_scene_holes_are_wireframe_and_have_their_own_flag():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 2, 0, 2, 0, 2], name="wall")
    api.holes.add_hole(xb=[0.5, 1.0, 0, 2, 0, 2], name="door")

    specs = build_scene(api)
    hole_specs = [s for s in specs if s.entity_kind == "hole"]
    assert len(hole_specs) == 1
    assert hole_specs[0].style == "wireframe"

    api.viewport.set_visibility(VisibilityFlags.OBSTRUCTIONS, False)
    kinds = {s.entity_kind for s in build_scene(api)}
    assert "obstruction" not in kinds and "hole" in kinds           # holes follow their own flag now
    api.viewport.set_visibility(VisibilityFlags.HOLES, False)
    assert not [s for s in build_scene(api) if s.entity_kind in ("obstruction", "hole")]


def test_build_scene_all_obstructions_rendered_not_just_first():
    # Regression: an earlier draft had a stray `break` that silently
    # dropped every obstruction after the first one.
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")
    api.obstructions.add_obstruction(xb=[4, 5, 0, 1, 0, 1], name="c")

    specs = build_scene(api)
    obst_labels = sorted(s.label for s in specs if s.entity_kind == "obstruction")
    assert obst_labels == ["a", "b", "c"]


def test_build_scene_device_renders_as_sphere_at_xyz():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.devices.add_thermocouple(xyz=[1, 2, 3], devc_id="tc1")

    specs = build_scene(api)
    device_specs = [s for s in specs if s.entity_kind == "device"]
    assert len(device_specs) == 1
    assert device_specs[0].mesh.n_points > 8  # a sphere, not a degenerate box


def test_build_scene_init_region_renders_as_translucent_box():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.inits.add_init(xb=[0, 2, 0, 2, 0, 2], temperature=25.0, name="init1")

    specs = build_scene(api)
    init_specs = [s for s in specs if s.entity_kind == "init"]
    assert len(init_specs) == 1
    assert init_specs[0].opacity == 0.3
    assert init_specs[0].mesh.n_points > 0


def test_build_scene_profile_renders_as_sphere_at_xyz():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.profs.add_profile(quantity="INSIDE WALL TEMPERATURE", xyz=[1.0, 2.0, 0.0], name="prof1")

    specs = build_scene(api)
    prof_specs = [s for s in specs if s.entity_kind == "profile"]
    assert len(prof_specs) == 1
    assert prof_specs[0].mesh.n_points > 8  # a sphere, not a degenerate box


def test_build_scene_particle_class_has_no_geometry():
    # Particle classes (&PART) are non-spatial definitions referenced by
    # name — nothing should ever be drawn for them.
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.particles.add_particle_class(diameter=200.0, name="water_droplet")

    specs = build_scene(api)
    assert not [s for s in specs if s.entity_kind == "particle"]


def test_build_scene_visibility_flags_hide_init_and_profiles():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.inits.add_init(xb=[0, 1, 0, 1, 0, 1], name="init1")
    api.profs.add_profile(quantity="INSIDE WALL TEMPERATURE", xyz=[0, 0, 0], name="prof1")

    api.viewport.set_visibility(VisibilityFlags.INIT_REGIONS, False)
    api.viewport.set_visibility(VisibilityFlags.PROFILES, False)
    specs = build_scene(api)

    kinds = {s.entity_kind for s in specs}
    assert "init" not in kinds
    assert "profile" not in kinds


def test_build_scene_wireframe_override_applies_to_obstructions_and_vents():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    api.vents.add_vent(xb=[0, 1, 0, 1, 0, 0], name="v1")

    api.viewport.toggle_wireframe()
    specs = build_scene(api)

    assert all(s.style == "wireframe" for s in specs if s.entity_kind in ("obstruction", "vent"))


def test_build_scene_visibility_flags_hide_entity_kinds():
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")
    api.devices.add_thermocouple(xyz=[1, 1, 1], devc_id="tc1")

    api.viewport.set_visibility(VisibilityFlags.DEVICES, False)
    specs = build_scene(api)

    kinds = {s.entity_kind for s in specs}
    assert "mesh" in kinds
    assert "device" not in kinds


def test_scene_bbox_none_for_empty_project():
    from pyfds.gui.viewport_scene import scene_bbox
    assert scene_bbox(_make_api()) is None


def test_scene_bbox_unions_all_entity_kinds():
    from pyfds.gui.viewport_scene import scene_bbox
    api = _make_api()
    api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")
    api.obstructions.add_obstruction(xb=[-1, 0, 0, 1, 0, 1], name="box1")

    bbox = scene_bbox(api)
    assert bbox == (-1.0, 4.0, 0.0, 4.0, 0.0, 2.0)


def test_preset_distance_scales_with_scene_size():
    from pyfds.gui.viewport_scene import preset_distance
    small_api = _make_api()
    small_api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 1, 0, 1, 0, 1], name="m1")

    big_api = _make_api()
    big_api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 100, 0, 100, 0, 20], name="m1")

    assert preset_distance(big_api) > preset_distance(small_api)


def test_preset_distance_default_for_empty_project():
    from pyfds.gui.viewport_scene import preset_distance
    assert preset_distance(_make_api()) == 15.0


def test_actor_spec_carries_manager_attr_and_entity_for_picking():
    # Needed so Viewport3D can resolve a picked actor back to exactly the
    # (attr, entity) pair ProjectExplorer.selected() returns.
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    mesh = api.meshes.add_mesh(ijk=[10, 10, 5], xb=[0, 4, 0, 4, 0, 2], name="m1")
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")
    vent = api.vents.add_vent(xb=[0, 1, 0, 1, 0, 0], name="v1")
    hole = api.holes.add_hole(xb=[0, 1, 0, 1, 0, 1], name="h1")
    device = api.devices.add_thermocouple(xyz=[1, 1, 1], devc_id="tc1")
    init = api.inits.add_init(xb=[0, 1, 0, 1, 0, 1], name="i1")
    prof = api.profs.add_profile(quantity="INSIDE WALL TEMPERATURE", xyz=[0, 0, 0], name="p1")

    by_kind = {s.entity_kind: s for s in build_scene(api)}

    assert (by_kind["mesh"].manager_attr, by_kind["mesh"].entity) == ("meshes", mesh)
    assert (by_kind["obstruction"].manager_attr, by_kind["obstruction"].entity) == ("obstructions", obst)
    assert (by_kind["vent"].manager_attr, by_kind["vent"].entity) == ("vents", vent)
    assert (by_kind["hole"].manager_attr, by_kind["hole"].entity) == ("holes", hole)
    assert (by_kind["device"].manager_attr, by_kind["device"].entity) == ("devices", device)
    assert (by_kind["init"].manager_attr, by_kind["init"].entity) == ("inits", init)
    assert (by_kind["profile"].manager_attr, by_kind["profile"].entity) == ("profs", prof)


def test_build_scene_tags_each_mesh_with_its_field_data_entity_key():
    # Regression: picking used to key a lookup dict by id(picked_actor), but
    # VTK's picker does not reliably hand back the same Python actor wrapper
    # add_mesh() returned — confirmed empirically the lookup silently failed
    # in the live app (highlight worked, tree selection did not). field_data
    # travels with the underlying VTK dataset itself, so it survives
    # regardless of Python wrapper identity across the picker boundary.
    from pyfds.gui.viewport_scene import FIELD_DATA_KEY, build_scene, entity_key
    api = _make_api()
    obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="box1")

    spec = build_scene(api)[0]

    assert FIELD_DATA_KEY in spec.mesh.field_data
    assert str(spec.mesh.field_data[FIELD_DATA_KEY][0]) == entity_key("obstructions", obst)


def test_entity_key_is_unique_per_entity_instance():
    from pyfds.gui.viewport_scene import entity_key
    api = _make_api()
    a = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="a")
    b = api.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="b")

    assert entity_key("obstructions", a) != entity_key("obstructions", b)
    assert entity_key("obstructions", a) == entity_key("obstructions", a)


def test_build_scene_geom_sphere_renders_as_real_trimesh():
    # Geom entities (Draw > Sphere/Cylinder/Cone, or an imported STL) carry
    # their own verts/faces — this was previously not rendered at all
    # (build_scene had no branch for api.geom.all()), so a drawn shape
    # would silently never appear.
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.geom.sphere(center=(1, 2, 3), radius=0.5, name="ball")

    specs = build_scene(api)
    geom_specs = [s for s in specs if s.entity_kind == "geom"]
    assert len(geom_specs) == 1
    assert geom_specs[0].mesh.n_points > 8
    assert geom_specs[0].mesh.n_cells > 0
    assert geom_specs[0].manager_attr == "geom"


def test_build_scene_geom_with_no_verts_is_skipped_not_crashed():
    from pyfds.gui.viewport_scene import build_scene
    from pyfds.domain.model import Geom
    api = _make_api()
    api.project.add_entity(Geom(name="empty_geom"))  # verts/faces both None

    specs = build_scene(api)
    assert not [s for s in specs if s.entity_kind == "geom"]


def test_build_scene_visibility_flag_hides_geom():
    from pyfds.core.viewport import VisibilityFlags
    from pyfds.gui.viewport_scene import build_scene
    api = _make_api()
    api.geom.cylinder(center_base=(0, 0, 0), radius=0.5, height=2.0, name="pipe")

    api.viewport.set_visibility(VisibilityFlags.GEOMETRY, False)
    specs = build_scene(api)
    assert not [s for s in specs if s.entity_kind == "geom"]


def test_geom_bbox_computed_from_verts():
    from pyfds.domain.model import Geom
    g = Geom(
        name="tri",
        verts=[(0.0, 0.0, 0.0), (2.0, 3.0, 0.0), (1.0, 1.0, 5.0)],
        faces=[(0, 1, 2)],
    )
    assert g.bbox() == (0.0, 2.0, 0.0, 3.0, 0.0, 5.0)


def test_geom_bbox_none_without_verts():
    from pyfds.domain.model import Geom
    assert Geom(name="empty").bbox() is None


def test_scene_bbox_includes_geom_extent():
    from pyfds.gui.viewport_scene import scene_bbox
    api = _make_api()
    api.geom.sphere(center=(10, 10, 10), radius=1.0, name="far_ball")

    bbox = scene_bbox(api)
    assert bbox is not None
    assert bbox[1] >= 11.0  # x_max reaches the sphere's far edge
