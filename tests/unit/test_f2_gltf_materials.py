"""F2 / APP-03: glTF materials become a look on each imported shape; the scene draws it; realistic mode is physically
based. All pure data (no display needed)."""
import base64
import json

import numpy as np
import pytest

from pyfds.api import FdsApi
from pyfds.core.viewport import VisibilityFlags
from pyfds.domain.model import PbrLook
from pyfds.gui.viewport_scene import build_scene
from pyfds.io.mesh_importers_more import gltf_look
from pyfds.io.serializer import Serializer

CUBE_V = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
CUBE_F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5),
          (0, 4, 7), (0, 7, 3)]


def make_gltf(tmp_path, materials=None, prim_materials=(None,), name="m.gltf"):
    """A glTF with one cube mesh per entry of *prim_materials* (a material index or None), side by side."""
    pos = np.array(CUBE_V, dtype="<f4")
    idx = np.array(CUBE_F, dtype="<u2").reshape(-1)
    blob = pos.tobytes() + idx.tobytes()
    meshes, nodes = [], []
    for i, m in enumerate(prim_materials):
        prim = {"attributes": {"POSITION": 0}, "indices": 1}
        if m is not None:
            prim["material"] = m
        meshes.append({"primitives": [prim]})
        nodes.append({"mesh": i, "translation": [2.0 * i, 0, 0]})
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes,
           "meshes": meshes,
           "buffers": [{"byteLength": len(blob), "uri": "data:application/octet-stream;base64,"
                        + base64.b64encode(blob).decode()}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": pos.nbytes},
                           {"buffer": 0, "byteOffset": pos.nbytes, "byteLength": idx.nbytes}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5123, "count": 36, "type": "SCALAR"}]}
    if materials is not None:
        doc["materials"] = materials
    f = tmp_path / name
    f.write_text(json.dumps(doc))
    return str(f)


@pytest.fixture
def api():
    return FdsApi()


METAL = {"name": "Red metal", "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.02, 0.02, 1.0],
                                                      "metallicFactor": 1.0, "roughnessFactor": 0.25}}
GLASS = {"name": "Glass", "alphaMode": "BLEND", "doubleSided": True,
         "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.9, 1.0, 0.35], "metallicFactor": 0.0, "roughnessFactor": 0.05}}


# -- the look itself ------------------------------------------------------------------------------------------------
def test_look_validates_and_gives_a_display_colour():
    with pytest.raises(ValueError):
        PbrLook(metallic=1.5)
    with pytest.raises(ValueError):
        PbrLook(base_color=(1.2, 0, 0))
    look = PbrLook(base_color=(0.4, 0.0, 0.0), emissive=(0.2, 0.2, 0.0))
    assert look.display_color() == pytest.approx((0.6, 0.2, 0.0)) and look.hex() == "#993300"
    assert PbrLook(base_color=(1, 1, 1), emissive=(1, 1, 1)).hex() == "#ffffff"          # clipped, not overflowing


def test_gltf_factors_become_srgb_and_defaults_follow_the_spec():
    look = gltf_look(GLASS)
    assert look["name"] == "Glass" and look["opacity"] == pytest.approx(0.35) and look["double_sided"]
    assert look["base_color"][0] == pytest.approx(0.797, abs=0.01)             # linear 0.6 -> sRGB about 0.80
    bare = gltf_look({})                                                       # no material data: glTF defaults
    assert bare["metallic"] == 1.0 and bare["roughness"] == 1.0 and bare["base_color"] == pytest.approx((1, 1, 1))
    opaque = gltf_look({"pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 0.2]}})
    assert opaque["opacity"] == 1.0                                            # alpha counts only for BLEND / MASK
    sg = gltf_look({"extensions": {"KHR_materials_pbrSpecularGlossiness": {"diffuseFactor": [0.5, 0.5, 0.5, 1],
                                                                          "glossinessFactor": 0.8}}})
    assert (sg["metallic"], round(sg["roughness"], 3)) == (0.0, 0.2)
    assert gltf_look({"emissiveFactor": [1, 0.5, 0]})["emissive"][0] == pytest.approx(1.0)


# -- importing --------------------------------------------------------------------------------------------------------
def test_one_material_gives_one_shape_with_its_look(tmp_path, api):
    g = api.geom.import_file(make_gltf(tmp_path, [METAL], (0,)))
    assert g.name == "m" and g.look.name == "Red metal" and (g.look.metallic, g.look.roughness) == (1.0, 0.25)
    assert len(g.faces) == 12


def test_several_materials_give_one_shape_each_named_after_the_material(tmp_path, api):
    shapes = api.geom.import_file(make_gltf(tmp_path, [METAL, GLASS], (0, 1, 0)))
    assert sorted(s.name for s in shapes) == ["m_Glass", "m_Red_metal"]
    metal = next(s for s in shapes if "metal" in s.name)
    assert len(metal.faces) == 24 and metal.look.metallic == 1.0           # both meshes using material 0 are joined
    assert next(s for s in shapes if s.name == "m_Glass").look.opacity == pytest.approx(0.35)
    api.history.undo()
    assert api.geom.all() == []                                            # the whole import is one undo step


def test_no_material_means_no_look_and_unmaterialled_parts_are_separate(tmp_path, api):
    assert api.geom.import_file(make_gltf(tmp_path, None, (None,), "a.gltf")).look is None
    shapes = api.geom.import_file(make_gltf(tmp_path, [METAL], (0, None), "b.gltf"))
    assert sorted(s.name for s in shapes) == ["b_Red_metal", "b_default"]
    assert next(s for s in shapes if s.name == "b_default").look is None


def test_by_material_false_joins_everything_without_a_look(tmp_path, api):
    g = api.geom.import_file(make_gltf(tmp_path, [METAL, GLASS], (0, 1)), by_material=False)
    assert len(g.faces) == 24 and g.look is None


def test_odd_material_names_become_safe_ids(tmp_path, api):
    shapes = api.geom.import_file(make_gltf(tmp_path, [{"name": "Wall paint (matt)!"}, {"name": ""}], (0, 1)))
    assert sorted(s.name for s in shapes) == ["m_Wall_paint__matt__", "m_material1"]


# -- look on a shape ---------------------------------------------------------------------------------------------------
def test_look_api_reads_edits_clears_and_undoes(tmp_path, api):
    g = api.geom.import_file(make_gltf(tmp_path, [METAL], (0,)))
    assert api.geom.look(g)["roughness"] == 0.25
    api.geom.set_look(g, roughness=0.9, base_color=(0.1, 0.2, 0.3))
    assert g.look.roughness == 0.9 and g.look.metallic == 1.0 and g.look.name == "Red metal"
    with pytest.raises(ValueError):
        api.geom.set_look(g, opacity=3.0)
    assert g.look.roughness == 0.9
    api.history.undo()
    assert g.look.roughness == 0.25
    api.geom.clear_look(g)
    assert api.geom.look(g) is None
    with pytest.raises(ValueError):
        api.geom.clear_look(g)
    plain = api.geom.box([0, 1, 0, 1, 0, 1])
    api.geom.set_look(plain, base_color=(1, 0, 0))                          # a drawn shape can get a look too
    assert plain.look.base_color == (1, 0, 0)


def test_look_is_saved_with_the_project_and_never_written_to_fds(tmp_path, api):
    g = api.geom.import_file(make_gltf(tmp_path, [METAL], (0,)))
    path = tmp_path / "p.pyfds"
    Serializer().save(api.project, str(path))
    back = Serializer().load(str(path))
    reloaded = back.geoms[0] if hasattr(back, "geoms") else next(e for e in back.all_entities if type(e).__name__ == "Geom")
    assert reloaded.look.name == "Red metal" and (reloaded.look.metallic, reloaded.look.roughness) == (1.0, 0.25)
    assert isinstance(reloaded.look.base_color, tuple) and len(reloaded.look.base_color) == 3
    text = api.fds_text()
    assert "&GEOM" in text and "Red metal" not in text and "METALLIC" not in text.upper()


def test_property_schema_copes_with_a_nested_look(tmp_path, api):
    from pyfds.gui.property_schema import build_edit_schema
    g = api.geom.import_file(make_gltf(tmp_path, [METAL], (0,)))
    assert isinstance(build_edit_schema(g), dict)


# -- drawing -----------------------------------------------------------------------------------------------------------
def test_look_colour_and_opacity_show_in_every_render_mode(tmp_path, api):
    api.geom.import_file(make_gltf(tmp_path, [GLASS], (0,)))
    spec = next(s for s in build_scene(api) if s.entity_kind == "geom")
    g = api.geom.all()[0]
    assert spec.color == g.look.hex() and spec.opacity == pytest.approx(0.35) and spec.pbr is None
    api.viewport.set_render_mode("wireframe")
    assert next(s for s in build_scene(api) if s.entity_kind == "geom").style == "wireframe"


def test_realistic_mode_is_physically_based_with_the_looks_own_numbers(tmp_path, api):
    api.geom.import_file(make_gltf(tmp_path, [METAL, GLASS], (0, 1)))
    api.viewport.set_render_mode("realistic")
    pbr = {s.label: s.pbr for s in build_scene(api) if s.entity_kind == "geom"}
    assert pbr["m_Red_metal"] == (1.0, 0.25) and pbr["m_Glass"] == (0.0, 0.05)
    assert all(s.smooth for s in build_scene(api) if s.entity_kind == "geom")


def test_ordinary_objects_get_matte_pbr_in_realistic_mode_only(api):
    api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    api.geom.box([3, 4, 0, 1, 0, 1])
    api.viewport.set_render_mode("outlines")
    assert all(s.pbr is None for s in build_scene(api))
    api.viewport.set_render_mode("realistic")
    assert {s.entity_kind: s.pbr for s in build_scene(api)} == {"obstruction": (0.0, 0.7), "geom": (0.0, 0.7)}


def test_shapes_from_raw_vertices_carry_normals_so_they_are_lit(api):
    api.geom.box([0, 1, 0, 1, 0, 1])
    spec = next(s for s in build_scene(api) if s.entity_kind == "geom")
    assert "Normals" in spec.mesh.cell_data and spec.mesh.n_cells == 12


# -- lighting and environment ------------------------------------------------------------------------------------------------
def test_sky_cubemap_is_a_six_face_cube_map():
    from pyfds.gui.viewport_environment import sky_cubemap
    tex = sky_cubemap(8)
    assert tex.cube_map is True


def test_lights_and_environment_calls():
    from pyfds.gui.viewport_environment import Environment, set_lights

    class FakeRenderer:
        env_up = None

        def SetEnvironmentUp(self, *v):
            self.env_up = v

        def SetEnvironmentRight(self, *v):
            pass

    class FakePlotter:
        def __init__(self):
            self.calls, self.renderer = [], FakeRenderer()

        def remove_all_lights(self):
            self.calls.append("remove_lights")

        def enable_lightkit(self):
            self.calls.append("kit")

        def set_environment_texture(self, tex, **kw):
            self.calls.append(("env", kw))

        def remove_environment_texture(self):
            self.calls.append("remove_env")

    p = FakePlotter()
    set_lights(p)
    assert p.calls == ["remove_lights", "kit"]
    env = Environment()
    env.apply(p, False)
    assert p.calls[-1] == "remove_env"
    env.apply(p, True)
    assert p.calls[-1][0] == "env" and p.calls[-1][1]["show_background"] is False and p.renderer.env_up == (0.0, 0.0, 1.0)
    first = env._texture
    env.apply(p, True)
    assert env._texture is first                                              # built once, reused
