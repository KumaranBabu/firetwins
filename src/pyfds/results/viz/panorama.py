"""360° pictures (phase V13): the six cube faces seen from one point, stitched into an equirectangular image.

Pure numpy. ``FACES`` is the one table both the renderer (which way to point the camera for each face) and the
stitcher use, so they cannot disagree. World axes: X forward, Y left, Z up; the middle of the picture looks along +X, the
left edge of the picture is the direction behind the viewer (-X), and a quarter of the way in is +Y (to the left).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

Vec = Tuple[float, float, float]

#: name -> (direction the camera looks, up vector of the camera)
FACES: Dict[str, Tuple[Vec, Vec]] = {
    "+x": ((1, 0, 0), (0, 0, 1)), "-x": ((-1, 0, 0), (0, 0, 1)),
    "+y": ((0, 1, 0), (0, 0, 1)), "-y": ((0, -1, 0), (0, 0, 1)),
    "+z": ((0, 0, 1), (-1, 0, 0)), "-z": ((0, 0, -1), (1, 0, 0)),
}
ORDER = tuple(FACES)


def face_camera(face: str, position: Sequence[float]) -> Tuple[Vec, Vec, Vec]:
    """``(position, focal point, up)`` for rendering one face with a 90° square view."""
    d, up = FACES[face]
    p = np.asarray(position, dtype=float)
    return tuple(p), tuple(p + np.asarray(d, dtype=float)), up


def _basis(face: str):
    d, up = (np.asarray(v, dtype=float) for v in FACES[face])
    return d, up, np.cross(d, up)


def equirect(faces: Dict[str, np.ndarray], width: int, height: int = 0) -> np.ndarray:
    """Stitch six square face images (``{"+x": array(n, n, c)}``, row 0 = top) into a ``height x width`` panorama."""
    missing = [f for f in ORDER if f not in faces]
    if missing:
        raise ValueError(f"missing cube faces: {', '.join(missing)}")
    height = height or width // 2
    if width < 8 or height < 4:
        raise ValueError("panorama is too small")
    n = faces["+x"].shape[0]
    for f, img in faces.items():
        if img.shape[0] != n or img.shape[1] != n:
            raise ValueError("all cube faces must be the same square size")
    channels = faces["+x"].shape[2:]
    col = np.arange(width)
    row = np.arange(height)
    lon = np.pi - 2 * np.pi * col / (width - 1)
    lat = np.pi / 2 - np.pi * row / (height - 1)
    LON, LAT = np.meshgrid(lon, lat)
    d = np.stack([np.cos(LAT) * np.cos(LON), np.cos(LAT) * np.sin(LON), np.sin(LAT)], axis=-1)       # (h, w, 3)
    out = np.zeros((height, width) + channels, dtype=faces["+x"].dtype)
    ax = np.abs(d)
    major = np.argmax(ax, axis=-1)
    sign = np.take_along_axis(d, major[..., None], -1)[..., 0] >= 0
    for name in ORDER:
        axis = "xyz".index(name[1])
        mask = (major == axis) & (sign == (name[0] == "+"))
        if not mask.any():
            continue
        f, u, r = _basis(name)
        dm = d[mask]
        depth = dm @ f
        x = (dm @ r) / depth
        y = (dm @ u) / depth
        cx = np.clip(np.rint((x + 1) / 2 * (n - 1)).astype(int), 0, n - 1)
        cy = np.clip(np.rint((1 - y) / 2 * (n - 1)).astype(int), 0, n - 1)
        out[mask] = faces[name][cy, cx]
    return out


def cross_to_faces(img: np.ndarray) -> Dict[str, np.ndarray]:
    """Cut a single "cross" cubemap image into faces: 4 columns x 3 rows, top = +z, bottom = -z, middle = left (+y),
    front (+x), right (-y), back (-x), the way the cross is folded around a viewer looking along +X."""
    h, w = img.shape[:2]
    if w % 4 or h % 3 or w // 4 != h // 3:
        raise ValueError("a cubemap cross image must be 4 faces wide and 3 faces high (square faces)")
    n = w // 4

    def cell(r: int, c: int) -> np.ndarray:
        return img[r * n:(r + 1) * n, c * n:(c + 1) * n]

    return {"+z": cell(0, 1), "+y": cell(1, 0), "+x": cell(1, 1), "-y": cell(1, 2), "-x": cell(1, 3), "-z": cell(2, 1)}


def movie_size(width: int) -> Tuple[int, int]:
    """Frame size of a 360 movie: 2:1, both even."""
    if width < 64:
        raise ValueError("a 360 movie needs a width of at least 64")
    w = width - width % 4
    return w, w // 2
