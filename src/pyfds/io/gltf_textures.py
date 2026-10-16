"""Base-colour textures of glTF materials (APP-03): the image bytes and the per-vertex texture coordinates.

Only the base-colour map is read (that is what makes an imported model look like itself); the image is kept
as base64 PNG/JPEG data inside the shape's ``PbrLook`` so a saved project carries it. Editor data, never FDS.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional, Tuple

MAX_IMAGE_BYTES = 6 * 1024 * 1024       # larger images are skipped rather than bloating the project file


def base_color_image(doc: dict, bufs: list, base: Path, mat: Optional[dict]) -> Optional[Tuple[str, int]]:
    """(base64 image data, TEXCOORD set) of the material's base-colour texture, or ``None`` when it has none or
    the image cannot be read (missing file, too large, not PNG/JPEG)."""
    if not mat:
        return None
    info = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if info is None:
        sg = mat.get("extensions", {}).get("KHR_materials_pbrSpecularGlossiness", {})
        info = sg.get("diffuseTexture")
    if info is None:
        return None
    try:
        tex = doc["textures"][info["index"]]
        img = doc["images"][tex["source"]]
        if "bufferView" in img:
            bv = doc["bufferViews"][img["bufferView"]]
            off = bv.get("byteOffset", 0)
            data = bufs[bv["buffer"]][off: off + bv["byteLength"]]
        elif str(img.get("uri", "")).startswith("data:"):
            data = base64.b64decode(img["uri"].split(",", 1)[1])
        elif img.get("uri"):
            data = (base / img["uri"].replace("%20", " ")).read_bytes()
        else:
            return None
    except (KeyError, IndexError, OSError, ValueError):
        return None
    if len(data) > MAX_IMAGE_BYTES or not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"):
        return None
    return base64.b64encode(data).decode("ascii"), int(info.get("texCoord", 0))
