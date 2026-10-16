"""glTF / GLB and COLLADA (DAE) importers (IMP-02). Registered by ``mesh_importers``."""
from __future__ import annotations

import base64
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .gltf_textures import base_color_image
from .mesh_importers import IMPORTERS, _finish

_CT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


# -- glTF --------------------------------------------------------------------------------------
def _read_gltf(p: Path):
    raw = p.read_bytes()
    glb_bin: Optional[bytes] = None
    if raw[:4] == b"glTF":
        length = struct.unpack_from("<I", raw, 8)[0]
        off, doc = 12, None
        while off < min(length, len(raw)):
            clen, ctype = struct.unpack_from("<II", raw, off)
            chunk = raw[off + 8: off + 8 + clen]
            if ctype == 0x4E4F534A:
                doc = json.loads(chunk.decode("utf-8"))
            elif ctype == 0x004E4942 and glb_bin is None:
                glb_bin = chunk
            off += 8 + clen
        if doc is None:
            raise ValueError(f"{p.name}: GLB has no JSON chunk")
        return doc, glb_bin
    return json.loads(raw.decode("utf-8")), None


def _buffers(doc, glb_bin, base: Path) -> List[bytes]:
    out = []
    for b in doc.get("buffers", []):
        uri = b.get("uri")
        if uri is None:
            if glb_bin is None:
                raise ValueError("glTF buffer has no data")
            out.append(glb_bin)
        elif uri.startswith("data:"):
            out.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            out.append((base / uri.replace("%20", " ")).read_bytes())
    return out


def _accessor(doc, bufs, index: int) -> np.ndarray:
    a = doc["accessors"][index]
    n, nc = a["count"], _NC[a["type"]]
    dt = np.dtype(_CT[a["componentType"]])
    if "bufferView" not in a:
        return np.zeros((n, nc), dtype=dt)
    bv = doc["bufferViews"][a["bufferView"]]
    data = bufs[bv["buffer"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or dt.itemsize * nc
    if stride == dt.itemsize * nc:
        arr = np.frombuffer(data, dtype=dt, count=n * nc, offset=start).reshape(n, nc)
    else:
        arr = np.stack([np.frombuffer(data, dtype=dt, count=nc, offset=start + i * stride) for i in range(n)])
    return arr.astype(float) if a["componentType"] == 5126 else arr.astype(np.int64)


def _node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T          # column-major
    m = np.eye(4)
    s = node.get("scale", [1, 1, 1])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m[:3, :3] = r * np.array(s)
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def _srgb(c: float) -> float:
    """glTF colour factors are linear; the viewport draws sRGB."""
    c = max(0.0, min(1.0, float(c)))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def gltf_look(mat: dict) -> dict:
    """Fields of a ``PbrLook`` from one glTF material (metallic-roughness, or the older specular-glossiness
    extension). Missing values take glTF's defaults."""
    pbr = mat.get("pbrMetallicRoughness", {})
    sg = mat.get("extensions", {}).get("KHR_materials_pbrSpecularGlossiness")
    if sg is not None and "pbrMetallicRoughness" not in mat:
        base = sg.get("diffuseFactor", [1, 1, 1, 1])
        metallic, roughness = 0.0, 1.0 - float(sg.get("glossinessFactor", 1.0))
    else:
        base = pbr.get("baseColorFactor", [1, 1, 1, 1])
        metallic, roughness = float(pbr.get("metallicFactor", 1.0)), float(pbr.get("roughnessFactor", 1.0))
    alpha = float(base[3]) if len(base) > 3 and mat.get("alphaMode", "OPAQUE") != "OPAQUE" else 1.0
    return {"name": str(mat.get("name", "")), "base_color": tuple(_srgb(c) for c in base[:3]),
            "opacity": max(0.0, min(1.0, alpha)), "metallic": max(0.0, min(1.0, metallic)),
            "roughness": max(0.0, min(1.0, roughness)),
            "emissive": tuple(_srgb(c) for c in mat.get("emissiveFactor", [0, 0, 0])[:3]),
            "double_sided": bool(mat.get("doubleSided", False))}


def _safe_id(text: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in text.strip())
    return out or "material"


class GltfImporter:
    @staticmethod
    def load(path: str, *, surf_id: str = "INERT", name: Optional[str] = None, units: str = "m",
             up_axis: str = "Y", translate: Optional[Sequence[float]] = None, scale: float = 1.0,
             by_material: bool = True):
        """glTF 2.0 / GLB triangle meshes with node transforms. glTF is Y-up, so *up_axis* defaults to Y.

        Each material becomes its own shape carrying a ``look`` (colour, opacity, metallic, roughness, emissive), so
        an imported model keeps its appearance; a file with several materials returns a list. ``by_material=False``
        joins everything into one shape without a look."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"glTF file not found: {p}")
        doc, glb_bin = _read_gltf(p)
        bufs = _buffers(doc, glb_bin, p.parent)
        nodes = doc.get("nodes", [])
        scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else {}
        roots = scene.get("nodes", list(range(len(nodes))) if not doc.get("scenes") else [])
        groups: dict = {}                     # material index (or None) -> (verts, faces)
        uv_groups: dict = {}                  # material index -> [(u, v)] per vertex, for textured materials
        materials = doc.get("materials", [])
        textured: dict = {}                   # material index -> (image data, TEXCOORD set)
        if by_material:
            for mi, mt in enumerate(materials):
                found = base_color_image(doc, bufs, p.parent, mt)
                if found:
                    textured[mi] = found

        def visit(i, parent, depth=0):
            if depth > 64:
                return
            node = nodes[i]
            m = parent @ _node_matrix(node)
            if "mesh" in node:
                for prim in doc["meshes"][node["mesh"]].get("primitives", []):
                    mode = prim.get("mode", 4)
                    if mode not in (4, 5, 6) or "POSITION" not in prim.get("attributes", {}):
                        continue
                    pos = _accessor(doc, bufs, prim["attributes"]["POSITION"])
                    pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
                    idx = (_accessor(doc, bufs, prim["indices"]).reshape(-1) if "indices" in prim
                           else np.arange(len(pos)))
                    if mode == 4:
                        tris = idx[: len(idx) // 3 * 3].reshape(-1, 3)
                    elif mode == 5:
                        tris = np.array([(idx[k], idx[k + 1], idx[k + 2]) if k % 2 == 0
                                         else (idx[k + 1], idx[k], idx[k + 2]) for k in range(len(idx) - 2)])
                    else:
                        tris = np.array([(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)])
                    key = prim.get("material") if by_material else None
                    verts, faces = groups.setdefault(key, ([], []))
                    base = len(verts)
                    if key in textured:
                        uv_name = f"TEXCOORD_{textured[key][1]}"
                        uv = (_accessor(doc, bufs, prim["attributes"][uv_name]) if uv_name in prim["attributes"]
                              else np.zeros((len(pos), 2)))
                        uv_groups.setdefault(key, []).extend((float(a), 1.0 - float(b)) for a, b in uv[:, :2])
                    verts.extend(tuple(map(float, q)) for q in pos)
                    faces.extend((int(a) + base, int(b) + base, int(c) + base) for a, b, c in tris.reshape(-1, 3))
            for c in node.get("children", []):
                visit(c, m, depth + 1)

        for r in roots:
            visit(r, np.eye(4))
        stem = name or p.stem
        out = []
        for key, (verts, faces) in groups.items():
            mat = materials[key] if key is not None and key < len(materials) else None
            label = stem if len(groups) == 1 else f"{stem}_{_safe_id(str(mat.get('name') or f'material{key}')) if mat else 'default'}"
            uvs = uv_groups.get(key) if key in textured else None
            g = _finish(verts, faces, p, surf_id=surf_id, name=label, units=units, up_axis=up_axis,
                        translate=translate, scale=scale, weld=uvs is None)    # welding would renumber the vertices
            if mat is not None:
                from pyfds.domain.model import PbrLook
                g.look = PbrLook(**gltf_look(mat))
                if uvs is not None and len(uvs) == len(g.verts or []):
                    g.look.texture, g.look.uvs = textured[key][0], uvs
            out.append(g)
        if not out:
            raise ValueError(f"{p.name}: no triangles found")
        return out[0] if len(out) == 1 else out


# -- COLLADA -----------------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _floats(text: str) -> List[float]:
    return [float(t) for t in (text or "").split()]


class DaeImporter:
    @staticmethod
    def load(path: str, *, surf_id: str = "INERT", name: Optional[str] = None, units: Optional[str] = None,
             up_axis: Optional[str] = None, translate: Optional[Sequence[float]] = None, scale: float = 1.0):
        """COLLADA ``triangles`` / ``polylist`` / ``polygons`` geometry with ``<matrix>`` node transforms.
        Units and up axis default to the file's ``<unit>`` and ``<up_axis>``."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"DAE file not found: {p}")
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"{p.name}: not valid COLLADA XML ({exc})") from None
        file_scale, file_up = 1.0, "Y"
        for el in root.iter():
            t = _local(el.tag)
            if t == "unit":
                file_scale = float(el.get("meter", 1.0))
            elif t == "up_axis":
                file_up = "Y" if (el.text or "Y_UP").strip().upper().startswith("Y") else "Z"
        geoms = {}
        for g in root.iter():
            if _local(g.tag) == "geometry" and g.get("id"):
                geoms[g.get("id")] = g
        verts: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, int, int]] = []

        def add_geometry(gel, m):
            for mesh in _children(gel, "mesh"):
                sources = {s.get("id"): s for s in _children(mesh, "source")}
                vmap = {}
                for v in _children(mesh, "vertices"):
                    for inp in _children(v, "input"):
                        if inp.get("semantic") == "POSITION":
                            vmap[v.get("id")] = inp.get("source")[1:]
                for prim in mesh:
                    kind = _local(prim.tag)
                    if kind not in ("triangles", "polylist", "polygons"):
                        continue
                    inputs = _children(prim, "input")
                    vin = next((i for i in inputs if i.get("semantic") == "VERTEX"), None)
                    if vin is None:
                        continue
                    stride = max(int(i.get("offset", 0)) for i in inputs) + 1
                    off = int(vin.get("offset", 0))
                    src_id = vmap.get(vin.get("source")[1:], vin.get("source")[1:])
                    src = sources[src_id]
                    acc = _children(src, "technique_common")[0][0]
                    n = int(acc.get("stride", 3))
                    pos = np.array(_floats(_children(src, "float_array")[0].text)).reshape(-1, n)[:, :3]
                    pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
                    base = len(verts)
                    verts.extend(tuple(map(float, q)) for q in pos)
                    if kind == "triangles":
                        idx = np.array([int(t) for t in " ".join(c.text or "" for c in _children(prim, "p")).split()])
                        tri = idx.reshape(-1, stride)[:, off].reshape(-1, 3)
                        faces.extend((int(a) + base, int(b) + base, int(c) + base) for a, b, c in tri)
                    elif kind == "polylist":
                        counts = [int(t) for t in _children(prim, "vcount")[0].text.split()]
                        idx = np.array([int(t) for t in _children(prim, "p")[0].text.split()]).reshape(-1, stride)[:, off]
                        k = 0
                        for c in counts:
                            poly = idx[k:k + c]
                            k += c
                            faces.extend((int(poly[0]) + base, int(poly[j]) + base, int(poly[j + 1]) + base)
                                         for j in range(1, c - 1))
                    else:
                        for pe in _children(prim, "p"):
                            poly = np.array([int(t) for t in pe.text.split()]).reshape(-1, stride)[:, off]
                            faces.extend((int(poly[0]) + base, int(poly[j]) + base, int(poly[j + 1]) + base)
                                         for j in range(1, len(poly) - 1))

        def visit(node, parent, depth=0):
            if depth > 64:
                return False
            m = parent.copy()
            for mat in _children(node, "matrix"):
                m = m @ np.array(_floats(mat.text)).reshape(4, 4)
            found = False
            for inst in _children(node, "instance_geometry"):
                gel = geoms.get((inst.get("url") or "#")[1:])
                if gel is not None:
                    add_geometry(gel, m)
                    found = True
            for child in _children(node, "node"):
                found = visit(child, m, depth + 1) or found
            return found

        placed = False
        for vs in root.iter():
            if _local(vs.tag) == "visual_scene":
                for node in _children(vs, "node"):
                    placed = visit(node, np.eye(4)) or placed
        if not placed:
            for gel in geoms.values():
                add_geometry(gel, np.eye(4))
        k = file_scale if units is None else 1.0
        return _finish(verts, faces, p, surf_id=surf_id, name=name, units=units or "m",
                       up_axis=up_axis or file_up, translate=translate, scale=scale * k)


IMPORTERS[".gltf"] = GltfImporter.load
IMPORTERS[".glb"] = GltfImporter.load
IMPORTERS[".dae"] = DaeImporter.load
