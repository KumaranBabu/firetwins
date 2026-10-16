"""glTF base-colour textures (APP-03): image and per-vertex UVs are imported, kept in the project, and drawn."""
import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

from pyfds.api import FdsApi
from pyfds.gui.viewport_scene import build_scene
from pyfds.io.gltf_textures import MAX_IMAGE_BYTES, base_color_image
from pyfds.io.serializer import Serializer
from tests.unit.test_f2_gltf_materials import make_gltf


def png_bytes(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


def textured_gltf(tmp_path, *, external=False, texcoord=True, image=None, name="t.gltf"):
    """The cube of make_gltf with one textured material (image as a data URI, or a file beside the glTF)."""
    path = make_gltf(tmp_path, [{"name": "Brick", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}], (0,), name)
    doc = json.loads(open(path).read())
    blob = base64.b64decode(doc["buffers"][0]["uri"].split(",", 1)[1])
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0), (1, 0), (1, 1), (0, 1)], dtype="<f4")
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob + uv.tobytes()).decode()
    doc["buffers"][0]["byteLength"] = len(blob) + uv.nbytes
    doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": uv.nbytes})
    doc["accessors"].append({"bufferView": 2, "componentType": 5126, "count": 8, "type": "VEC2"})
    if texcoord:
        doc["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"] = 2
    data = image if image is not None else png_bytes()
    if external:
        (tmp_path / "brick.png").write_bytes(data)
        doc["images"] = [{"uri": "brick.png"}]
    else:
        doc["images"] = [{"uri": "data:image/png;base64," + base64.b64encode(data).decode()}]
    doc["textures"] = [{"source": 0}]
    (tmp_path / name).write_text(json.dumps(doc))
    return str(tmp_path / name)


@pytest.fixture
def api():
    return FdsApi()


def test_texture_and_uvs_are_imported_unwelded(tmp_path, api):
    g = api.geom.import_file(textured_gltf(tmp_path))
    assert g.look.texture and base64.b64decode(g.look.texture)[:4] == b"\x89PNG"
    assert len(g.look.uvs) == len(g.verts) == 8                       # no welding: every vertex keeps its UV
    assert g.look.uvs[2] == (1.0, 0.0)                                # glTF v runs down, the view's runs up: flipped


def test_image_beside_the_file_is_read(tmp_path, api):
    g = api.geom.import_file(textured_gltf(tmp_path, external=True))
    assert g.look.texture


def test_missing_uvs_are_padded_not_fatal(tmp_path, api):
    g = api.geom.import_file(textured_gltf(tmp_path, texcoord=False))
    assert g.look.uvs == [(0.0, 1.0)] * 8


def test_unreadable_images_leave_a_plain_look(tmp_path, api):
    g = api.geom.import_file(textured_gltf(tmp_path, image=b"not an image"))
    assert g.look.texture is None and g.look.uvs is None and g.look.name == "Brick"
    big = png_bytes() + b"\0" * (MAX_IMAGE_BYTES + 1)
    assert api.geom.import_file(textured_gltf(tmp_path, image=big, name="b.gltf")).look.texture is None


def test_helper_ignores_materials_without_textures():
    assert base_color_image({}, [], None, None) is None
    assert base_color_image({}, [], None, {"pbrMetallicRoughness": {}}) is None
    assert base_color_image({"textures": []}, [], None, {"pbrMetallicRoughness": {"baseColorTexture": {"index": 3}}}) is None


def test_glb_embedded_image_by_buffer_view():
    data = png_bytes()
    doc = {"textures": [{"source": 0}], "images": [{"bufferView": 0}],
           "bufferViews": [{"buffer": 0, "byteOffset": 2, "byteLength": len(data)}]}
    mat = {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0, "texCoord": 1}}}
    got = base_color_image(doc, [b"xx" + data + b"yy"], None, mat)
    assert got == (base64.b64encode(data).decode(), 1)


def test_scene_carries_texture_coordinates(tmp_path, api):
    api.geom.import_file(textured_gltf(tmp_path))
    spec = next(s for s in build_scene(api) if s.entity_kind == "geom")
    assert spec.texture and spec.mesh.active_texture_coordinates.shape == (8, 2)


def test_stale_uvs_are_ignored(tmp_path, api):
    g = api.geom.import_file(textured_gltf(tmp_path))
    g.look.uvs = g.look.uvs[:5]                                       # the shape was edited: counts no longer match
    assert next(s for s in build_scene(api) if s.entity_kind == "geom").texture is None


def test_texture_survives_save_and_load_and_stays_out_of_fds(tmp_path, api):
    api.geom.import_file(textured_gltf(tmp_path))
    out = str(tmp_path / "p.pyfds")
    Serializer().save(api.project, out)
    back = Serializer().load(out)
    g = next(e for e in back.all_entities if type(e).__name__ == "Geom")
    assert g.look.texture and len(g.look.uvs) == 8
    assert "TEXCOORD" not in api.fds_text().upper() and g.look.texture[:20] not in api.fds_text()
